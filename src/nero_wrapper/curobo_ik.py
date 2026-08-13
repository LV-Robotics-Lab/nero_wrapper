from __future__ import annotations

import math
import tempfile
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from importlib import resources
from pathlib import Path

import numpy as np
import yaml
from scipy.spatial.transform import Rotation

from .dual_model import (
    ARM_NAMES,
    HARDWARE_TO_MODEL_JOINT_OFFSETS,
    LAB_DUAL_BENCH_BASE_TRANSFORMS,
    BaseTransform,
    build_dual_nero_urdf,
)
from .ik_geometry import step_towards


class IkSafetyError(RuntimeError):
    pass


class IkNoProgressError(RuntimeError):
    """A safe IK attempt produced no useful Cartesian motion this cycle."""


_MESH_VERIFIED_FIT_TOLERANCE_PAIRS = frozenset(
    {
        frozenset(("arm_a_base_link", "arm_a_link2")),
        frozenset(("arm_b_base_link", "arm_b_link2")),
    }
)

_SHALLOW_ESCAPE_APPROVED_PAIRS = frozenset(
    {
        frozenset(("arm_a_link5", "arm_a_tcp_link")),
        frozenset(("arm_b_link5", "arm_b_tcp_link")),
    }
)


def self_collision_pair_tolerance_m(
    first_link: str,
    second_link: str,
    mesh_fit_tolerance_m: float,
) -> float:
    """Return fitting tolerance only for mesh-verified base/link2 pairs."""

    if frozenset((first_link, second_link)) in _MESH_VERIFIED_FIT_TOLERANCE_PAIRS:
        return float(mesh_fit_tolerance_m)
    return 0.0


def self_collision_pair_escape_allowed(first_link: str, second_link: str) -> bool:
    """Allow only the captured same-arm link5/estimated-tool fit pair."""

    return (
        frozenset((first_link, second_link)) in _SHALLOW_ESCAPE_APPROVED_PAIRS
    )


def shallow_collision_escape_allowed(
    clearances_m: np.ndarray,
    approved_pair_mask: np.ndarray,
    max_initial_overlap_m: float,
    *,
    require_final_clearance: bool = False,
    minimum_progress_m: float = 1.0e-6,
    numerical_slack_m: float = 1.0e-6,
) -> bool:
    """Accept only non-deepening paths from a shallow approved overlap.

    ``clearances_m`` already includes any pair-local sphere fitting tolerance.
    Pairs that start collision-free must remain collision-free. Every approved
    initially-overlapping pair must never deepen. It must either measurably
    improve, or remain numerically stationary (which occurs when the overlap is
    on an inactive arm). Joint bounds and world collisions are checked
    separately. Recovery parking can additionally require complete clearance.
    """

    clearances = np.asarray(clearances_m, dtype=np.float64)
    approved = np.asarray(approved_pair_mask, dtype=bool)
    if clearances.ndim != 2 or clearances.shape[0] < 2:
        raise ValueError("collision escape needs a samples-by-pairs matrix")
    if approved.shape != (clearances.shape[1],):
        raise ValueError("approved collision escape mask has the wrong size")
    if (
        not math.isfinite(max_initial_overlap_m)
        or max_initial_overlap_m < 0.0
        or not math.isfinite(minimum_progress_m)
        or minimum_progress_m <= 0.0
        or not math.isfinite(numerical_slack_m)
        or numerical_slack_m < 0.0
    ):
        raise ValueError("collision escape thresholds must be finite and valid")
    if not np.all(np.isfinite(clearances)):
        return False

    initial = clearances[0]
    initially_overlapping = initial < 0.0
    if not np.any(initially_overlapping):
        return bool(np.all(clearances >= 0.0))
    if np.any(initially_overlapping & ~approved):
        return False
    if np.any(initial[initially_overlapping] < -max_initial_overlap_m):
        return False
    if np.any(clearances[:, ~initially_overlapping] < 0.0):
        return False

    escaping = clearances[:, initially_overlapping]
    initial_escaping = initial[initially_overlapping]
    if np.any(escaping < initial_escaping[None, :] - numerical_slack_m):
        return False
    if require_final_clearance and np.any(escaping[-1] < 0.0):
        return False
    made_progress = escaping[-1] >= initial_escaping + minimum_progress_m
    remained_stationary = np.max(
        np.abs(escaping - initial_escaping[None, :]), axis=0
    ) <= numerical_slack_m
    return bool(
        np.all(made_progress | remained_stationary)
    )


def load_tool_collision_spheres(path: str | Path) -> list[dict[str, object]]:
    """Load validated xyz/radius spheres expressed in the configured TCP frame."""

    model_path = Path(path).expanduser().resolve()
    if not model_path.is_file():
        raise FileNotFoundError(f"TacClaw collision model not found: {model_path}")
    with model_path.open("r", encoding="utf-8") as stream:
        document = yaml.safe_load(stream)
    try:
        frame = document["collision_model"]["frame"]
        raw_spheres = document["collision_model"]["collision_spheres"]
    except (KeyError, TypeError) as exc:
        raise ValueError(
            "TacClaw collision model needs collision_model.frame and collision_spheres"
        ) from exc
    if frame != "tcp_link":
        raise ValueError("TacClaw collision spheres must be expressed in tcp_link")
    if not isinstance(raw_spheres, list) or not raw_spheres:
        raise ValueError("TacClaw collision model must contain at least one sphere")
    spheres = []
    for index, raw in enumerate(raw_spheres):
        try:
            center = np.asarray(raw["center"], dtype=np.float64)
            radius = float(raw["radius"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"TacClaw collision sphere {index} is invalid") from exc
        if center.shape != (3,) or not np.all(np.isfinite(center)):
            raise ValueError(
                f"TacClaw collision sphere {index} center needs three finite values"
            )
        if not math.isfinite(radius) or radius <= 0.0:
            raise ValueError(
                f"TacClaw collision sphere {index} radius must be positive and finite"
            )
        spheres.append(
            {
                "center": [float(value) for value in center],
                "radius": radius,
            }
        )
    return spheres


@dataclass(frozen=True)
class IkResult:
    joint_commands: dict[str, np.ndarray]
    tcp_world: dict[str, np.ndarray]
    position_errors_m: dict[str, float]
    orientation_errors_rad: dict[str, float]


def bounded_joint_candidate(
    current: np.ndarray,
    candidate: np.ndarray,
    active_indices: Sequence[int],
    max_joint_step_rad: float,
) -> tuple[np.ndarray, float]:
    """Freeze inactive joints and scale a coordinated IK step to its bound."""
    current = np.asarray(current, dtype=np.float64)
    candidate = np.asarray(candidate, dtype=np.float64)
    if current.shape != candidate.shape or current.ndim != 1:
        raise ValueError("current and candidate must be equal one-dimensional arrays")
    if max_joint_step_rad <= 0.0:
        raise ValueError("max_joint_step_rad must be positive")
    active = np.asarray(tuple(active_indices), dtype=int)
    if active.size == 0:
        raise ValueError("at least one active joint is required")
    if np.any(active < 0) or np.any(active >= current.size):
        raise ValueError("active joint index is out of range")

    delta = np.zeros_like(current)
    delta[active] = candidate[active] - current[active]
    largest = float(np.max(np.abs(delta[active])))
    scale = 1.0 if largest <= max_joint_step_rad else max_joint_step_rad / largest
    return current + scale * delta, scale


class CuroboDualNeroIk:
    """Deterministic cuRobo local IK with bounded, GPU collision-checked steps.

    The solver tracks both TCP frames in one 14-DOF model.  cuRobo's local
    Levenberg-Marquardt solver supplies the Cartesian step; a separate cuRobo
    collision checker validates the complete interpolated step, including
    cross-arm collisions and joint limits.
    """

    def __init__(
        self,
        urdf_path: str | Path,
        *,
        base_transforms: Mapping[str, BaseTransform] = LAB_DUAL_BENCH_BASE_TRANSFORMS,
        joint_offsets: Mapping[str, Sequence[float]] = HARDWARE_TO_MODEL_JOINT_OFFSETS,
        tcp_offsets: Mapping[str, BaseTransform] | None = None,
        tool_collision_model_path: str | Path | None = None,
        default_hardware_position: Mapping[str, Sequence[float]] | None = None,
        control_rate_hz: float = 20.0,
        max_joint_step_rad: float = math.radians(1.0),
        max_cartesian_step_m: float = 0.005,
        max_orientation_step_rad: float = math.radians(2.0),
        orientation_weight: float = 1.0,
        collision_interpolation_steps: int = 5,
        self_collision_mesh_fit_tolerance_m: float = 0.0002,
        collision_escape_max_initial_overlap_m: float = 0.0005,
    ) -> None:
        if (
            control_rate_hz <= 0.0
            or max_joint_step_rad <= 0.0
            or max_cartesian_step_m <= 0.0
            or max_orientation_step_rad <= 0.0
        ):
            raise ValueError("IK rate and step limits must be positive")
        if collision_interpolation_steps < 2:
            raise ValueError("collision interpolation needs at least two samples")
        if not math.isfinite(orientation_weight) or orientation_weight <= 0.0:
            raise ValueError("orientation_weight must be positive and finite")
        if (
            not math.isfinite(self_collision_mesh_fit_tolerance_m)
            or self_collision_mesh_fit_tolerance_m < 0.0
            or self_collision_mesh_fit_tolerance_m > 0.006
        ):
            raise ValueError(
                "self-collision mesh-fit tolerance must be between 0 and 6mm"
            )
        if (
            not math.isfinite(collision_escape_max_initial_overlap_m)
            or collision_escape_max_initial_overlap_m < 0.0
            or collision_escape_max_initial_overlap_m > 0.001
        ):
            raise ValueError(
                "collision escape maximum overlap must be between 0 and 1mm"
            )

        try:
            import torch
            from curobo._src.solver.seed_ik.seed_ik_solver import SeedIKSolver
            from curobo._src.solver.seed_ik.seed_ik_solver_cfg import SeedIKSolverCfg
            from curobo.collision_checking import (
                RobotCollisionChecker,
                RobotCollisionCheckerCfg,
            )
            from curobo.types import GoalToolPose, JointState, Pose
        except ImportError as exc:
            raise RuntimeError(
                "cuRobo is not installed in the active Python environment"
            ) from exc
        if not torch.cuda.is_available():
            raise RuntimeError("cuRobo requires a visible CUDA GPU")
        major, minor = torch.cuda.get_device_capability(0)
        if major < 7:
            raise RuntimeError(
                f"cuRobo requires compute capability 7.0 or newer, got {major}.{minor}"
            )

        self.torch = torch
        self.GoalToolPose = GoalToolPose
        self.JointState = JointState
        self.Pose = Pose
        self.offsets = {
            arm: np.asarray(joint_offsets[arm], dtype=np.float64)
            for arm in ARM_NAMES
        }
        for arm in ARM_NAMES:
            if self.offsets[arm].shape != (7,):
                raise ValueError(f"{arm} joint offset must contain seven values")
        default_hardware_position = default_hardware_position or {
            arm: np.zeros(7, dtype=np.float64) for arm in ARM_NAMES
        }
        default_model_positions = []
        for arm in ARM_NAMES:
            hardware_position = np.asarray(
                default_hardware_position[arm], dtype=np.float64
            )
            if hardware_position.shape != (7,) or not np.all(
                np.isfinite(hardware_position)
            ):
                raise ValueError(
                    f"default_hardware_position[{arm}] must contain seven finite values"
                )
            default_model_positions.append(hardware_position + self.offsets[arm])
        self.default_model_position = np.concatenate(default_model_positions)
        self.base_world = {
            arm: self._transform_from_xyz_rpy(
                base_transforms[arm].xyz, base_transforms[arm].rpy
            )
            for arm in ARM_NAMES
        }
        self.max_joint_step_rad = float(max_joint_step_rad)
        self.max_cartesian_step_m = float(max_cartesian_step_m)
        self.max_orientation_step_rad = float(max_orientation_step_rad)
        self.orientation_weight = float(orientation_weight)
        self.collision_interpolation_steps = int(collision_interpolation_steps)
        self.self_collision_mesh_fit_tolerance_m = float(
            self_collision_mesh_fit_tolerance_m
        )
        self.collision_escape_max_initial_overlap_m = float(
            collision_escape_max_initial_overlap_m
        )
        self.joint_names = [
            f"{arm}_joint{index}"
            for arm in ARM_NAMES
            for index in range(1, 8)
        ]
        self.arm_slices = {
            arm: slice(index * 7, (index + 1) * 7)
            for index, arm in enumerate(ARM_NAMES)
        }
        self.tool_frames = [f"{arm}_tcp_link" for arm in ARM_NAMES]
        self.device = torch.device("cuda:0")

        robot_config, temporary_urdf = self._robot_config(
            urdf_path,
            base_transforms,
            joint_offsets,
            tcp_offsets,
            tool_collision_model_path,
        )
        try:
            solver_config = SeedIKSolverCfg.create(
                robot=robot_config,
                num_seeds=1,
                max_iterations=20,
                inner_iterations=4,
                position_tolerance=0.0005,
                orientation_tolerance=0.01,
                convergence_position_tolerance=1e-5,
                convergence_orientation_tolerance=1e-5,
                joint_limit_weight=1.0,
                lambda_initial=1.0,
                lambda_factor=2.0,
                lambda_max=1e10,
                lambda_min=1e-5,
                rho_min=1e-5,
                start_cspace_dist_weight=1.0,
                position_weight=1.0,
                orientation_weight=self.orientation_weight,
                velocity_weight=0.0,
                acceleration_weight=0.0,
                use_cuda_graph=True,
            )
            self.solver = SeedIKSolver(solver_config)
            checker_config = RobotCollisionCheckerCfg.load_from_config(
                robot_config=robot_config,
                self_collision_activation_distance=0.0,
            )
            self.collision_checker = RobotCollisionChecker(checker_config)
            self._collision_pair_tolerances = self._build_collision_pair_tolerances()
            self._collision_pair_escape_mask = self._build_collision_pair_escape_mask()
        finally:
            Path(temporary_urdf).unlink(missing_ok=True)

        expected_names = self.joint_names
        if list(self.solver.joint_names) != expected_names:
            raise RuntimeError(
                "cuRobo joint order does not match the NERO command order: "
                f"{self.solver.joint_names}"
            )
        if list(self.solver.tool_frames) != self.tool_frames:
            raise RuntimeError(
                "cuRobo tool-frame order does not match the dual NERO model"
            )

        self.measured_hardware: dict[str, np.ndarray] | None = None
        self.model_q: np.ndarray | None = None
        self.tcp_world: dict[str, np.ndarray] = {}
        self.warmup_seconds = self._warm_up()

    @staticmethod
    def _transform_from_xyz_rpy(
        xyz: Sequence[float], rpy: Sequence[float]
    ) -> np.ndarray:
        result = np.eye(4, dtype=np.float64)
        result[:3, :3] = Rotation.from_euler("xyz", rpy).as_matrix()
        result[:3, 3] = np.asarray(xyz, dtype=np.float64)
        return result

    def _robot_config(
        self,
        urdf_path: str | Path,
        base_transforms: Mapping[str, BaseTransform],
        joint_offsets: Mapping[str, Sequence[float]],
        tcp_offsets: Mapping[str, BaseTransform] | None,
        tool_collision_model_path: str | Path | None,
    ) -> tuple[dict, str]:
        collision_resource = resources.files(__package__).joinpath(
            "data/nero_curobo_collision.yaml"
        )
        with collision_resource.open("r", encoding="utf-8") as stream:
            collision = yaml.safe_load(stream)["collision_model"]
        mesh_link_names = list(collision["collision_link_names"])
        if tool_collision_model_path:
            tool_spheres = load_tool_collision_spheres(tool_collision_model_path)
            for arm in ARM_NAMES:
                tool_link = f"{arm}_tcp_link"
                collision["collision_link_names"].append(tool_link)
                collision["collision_spheres"][tool_link] = tool_spheres
                # The mounted tool occupies the flange envelope and is rigidly
                # adjacent to link7. NERO's fitted link6 sphere also protrudes
                # into that mounting envelope, just as link6/link7 are already
                # an ignored adjacent pair. Keep all earlier links and the
                # opposite arm strict.
                for adjacent_link in (f"{arm}_link6", f"{arm}_link7"):
                    collision["self_collision_ignore"].setdefault(
                        adjacent_link, []
                    ).append(tool_link)
                collision["self_collision_buffer"][tool_link] = 0.0

        urdf_content = build_dual_nero_urdf(
            urdf_path,
            base_transforms=base_transforms,
            joint_offsets=joint_offsets,
            tcp_offsets=tcp_offsets,
        )
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".urdf", encoding="utf-8", delete=False
        ) as stream:
            stream.write(urdf_content)
            generated_urdf = stream.name

        default_joint_position = self.default_model_position.tolist()
        dof = len(self.joint_names)
        kinematics = {
            "urdf_path": generated_urdf,
            "asset_root_path": "/",
            "base_link": "lab_world",
            "tool_frames": self.tool_frames,
            "collision_link_names": collision["collision_link_names"],
            "collision_spheres": collision["collision_spheres"],
            "self_collision_ignore": collision["self_collision_ignore"],
            "self_collision_buffer": collision["self_collision_buffer"],
            # tcp_link has sphere geometry supplied by the measured tool model,
            # not an URDF mesh. Keep mesh checking on the original NERO links.
            "mesh_link_names": mesh_link_names,
            "cspace": {
                "joint_names": self.joint_names,
                "default_joint_position": default_joint_position,
                "null_space_weight": [1.0] * dof,
                "cspace_distance_weight": [1.0] * dof,
                "max_acceleration": [10.0] * dof,
                "max_jerk": [500.0] * dof,
            },
        }
        return {"robot_cfg": {"kinematics": kinematics}}, generated_urdf

    def _warm_up(self) -> float:
        started = time.monotonic()
        default_model = self.default_model_position
        joint_state = self._joint_state(default_model)
        poses = self.solver.compute_kinematics(joint_state).tool_poses.to_dict()
        goal = self.GoalToolPose.from_poses(
            poses, ordered_tool_frames=self.tool_frames, num_goalset=1
        )
        result = self.solver.solve_single(
            goal_tool_poses=goal,
            current_state=joint_state,
            return_seeds=1,
        )
        self.torch.cuda.synchronize(self.device)
        if not bool(result.success.item()):
            raise RuntimeError("cuRobo CUDA warm-up IK failed")
        valid = self._configuration_valid(
            self._tensor(default_model).view(1, 1, -1)
        )
        if not bool(valid.item()):
            reason = self._invalid_configuration_reason(
                self._tensor(default_model).view(1, 1, -1)
            )
            raise RuntimeError(
                f"cuRobo default dual-NERO model is invalid: {reason}"
            )
        return time.monotonic() - started

    def _tensor(self, values: np.ndarray):
        return self.torch.as_tensor(
            values, dtype=self.torch.float32, device=self.device
        )

    def _joint_state(self, model_q: np.ndarray):
        return self.JointState.from_position(
            self._tensor(model_q).view(1, -1),
            joint_names=self.joint_names,
        )

    @staticmethod
    def _pose_transform(position: np.ndarray, quaternion_wxyz: np.ndarray) -> np.ndarray:
        result = np.eye(4, dtype=np.float64)
        result[:3, 3] = position
        result[:3, :3] = Rotation.from_quat(
            [
                quaternion_wxyz[1],
                quaternion_wxyz[2],
                quaternion_wxyz[3],
                quaternion_wxyz[0],
            ]
        ).as_matrix()
        return result

    def _kinematic_transforms(self, model_q: np.ndarray) -> dict[str, np.ndarray]:
        state = self.solver.compute_kinematics(self._joint_state(model_q))
        poses = state.tool_poses.to_dict()
        result = {}
        for arm in ARM_NAMES:
            pose = poses[f"{arm}_tcp_link"]
            position = pose.position[0].detach().cpu().numpy().astype(np.float64)
            quaternion = pose.quaternion[0].detach().cpu().numpy().astype(np.float64)
            result[arm] = self._pose_transform(position, quaternion)
        return result

    def _pack_model(self, measured_hardware: Mapping[str, Sequence[float]]) -> np.ndarray:
        measured = []
        for arm in ARM_NAMES:
            values = np.asarray(measured_hardware[arm], dtype=np.float64)
            if values.shape != (7,) or not np.all(np.isfinite(values)):
                raise IkSafetyError(
                    f"{arm} joint feedback must contain seven finite values"
                )
            measured.append(values + self.offsets[arm])
        return np.concatenate(measured)

    def sync(self, measured_hardware: Mapping[str, Sequence[float]]) -> None:
        model_q = self._pack_model(measured_hardware)
        self.measured_hardware = {
            arm: np.asarray(measured_hardware[arm], dtype=np.float64).copy()
            for arm in ARM_NAMES
        }
        self.model_q = model_q
        self.tcp_world = self._kinematic_transforms(model_q)

    def current_tcp_world(self, arm: str) -> np.ndarray:
        if arm not in self.tcp_world:
            raise IkSafetyError("IK cannot report TCP before joint synchronization")
        return self.tcp_world[arm].copy()

    def bounded_joint_step(
        self,
        measured_hardware: Mapping[str, Sequence[float]],
        targets_hardware: Mapping[str, Sequence[float]],
    ) -> dict[str, np.ndarray]:
        """Return one coordinated, collision-checked step to fixed joint targets."""
        current = self._pack_model(measured_hardware)
        target = self._pack_model(targets_hardware)
        bounded, _ = bounded_joint_candidate(
            current,
            target,
            range(current.size),
            self.max_joint_step_rad,
        )
        self._validate_interpolated_step(current, bounded)
        return {
            arm: bounded[self.arm_slices[arm]] - self.offsets[arm]
            for arm in ARM_NAMES
        }

    def validate_independent_joint_path(
        self,
        measured_hardware: Mapping[str, Sequence[float]],
        targets_hardware: Mapping[str, Sequence[float]],
        max_sample_step_rad: float = math.radians(2.0),
        *,
        recovery_escape_max_initial_overlap_m: float | None = None,
    ) -> tuple[int, int]:
        """Validate a fixed dual-arm move even if the two arms progress unevenly.

        A pair of firmware ``move_j`` commands starts within one ROS callback
        interval, but the two controllers are not clock-synchronised.  Checking
        only the diagonal (both arms at the same interpolation fraction) can
        therefore miss a dual-arm collision.  This method checks the Cartesian
        product of both arms' progress fractions, as well as joint bounds, and
        returns the number of samples used for each arm.
        """
        if not math.isfinite(max_sample_step_rad) or max_sample_step_rad <= 0.0:
            raise ValueError("max_sample_step_rad must be positive and finite")
        if recovery_escape_max_initial_overlap_m is not None and (
            not math.isfinite(recovery_escape_max_initial_overlap_m)
            or recovery_escape_max_initial_overlap_m < 0.0
            or recovery_escape_max_initial_overlap_m > 0.007
        ):
            raise ValueError(
                "park recovery escape maximum overlap must be between 0 and 7mm"
            )
        current = self._pack_model(measured_hardware)
        target = self._pack_model(targets_hardware)
        delta = target - current
        sample_counts = []
        for arm in ARM_NAMES:
            arm_delta = delta[self.arm_slices[arm]]
            sample_counts.append(
                max(
                    2,
                    int(
                        math.ceil(
                            float(np.max(np.abs(arm_delta)))
                            / max_sample_step_rad
                        )
                    )
                    + 1,
                )
            )

        alpha_a = self.torch.linspace(
            0.0,
            1.0,
            sample_counts[0],
            dtype=self.torch.float32,
            device=self.device,
        )
        alpha_b = self.torch.linspace(
            0.0,
            1.0,
            sample_counts[1],
            dtype=self.torch.float32,
            device=self.device,
        )
        progress_a, progress_b = self.torch.meshgrid(
            alpha_a, alpha_b, indexing="ij"
        )
        sample_total = sample_counts[0] * sample_counts[1]
        trajectory = self._tensor(current).view(1, 1, -1).repeat(
            1, sample_total, 1
        )
        delta_tensor = self._tensor(delta)
        trajectory[:, :, self.arm_slices["arm_a"]] += (
            progress_a.reshape(1, -1, 1)
            * delta_tensor[self.arm_slices["arm_a"]].view(1, 1, -1)
        )
        trajectory[:, :, self.arm_slices["arm_b"]] += (
            progress_b.reshape(1, -1, 1)
            * delta_tensor[self.arm_slices["arm_b"]].view(1, 1, -1)
        )
        valid = self._configuration_valid(trajectory)[0]
        if not bool(self.torch.all(valid).item()) and not self._trajectory_escape_allowed(
            trajectory,
            max_initial_overlap_m=recovery_escape_max_initial_overlap_m,
            require_final_clearance=(
                recovery_escape_max_initial_overlap_m is not None
            ),
        ):
            first = int(self.torch.nonzero(~valid, as_tuple=False)[0, 0].item())
            index_a, index_b = divmod(first, sample_counts[1])
            reason = self._invalid_configuration_reason(
                trajectory[:, first : first + 1, :]
            )
            raise IkSafetyError(
                "cuRobo rejected fixed joint path at "
                f"arm_a progress {index_a + 1}/{sample_counts[0]}, "
                f"arm_b progress {index_b + 1}/{sample_counts[1]}: {reason}"
            )
        return sample_counts[0], sample_counts[1]

    @staticmethod
    def _errors(actual: np.ndarray, target: np.ndarray) -> tuple[float, float]:
        position = float(np.linalg.norm(actual[:3, 3] - target[:3, 3]))
        orientation = float(
            Rotation.from_matrix(target[:3, :3] @ actual[:3, :3].T).magnitude()
        )
        return position, orientation

    def validate_driver_fk(
        self,
        measured_hardware: Mapping[str, Sequence[float]],
        driver_tcp_local: Mapping[str, np.ndarray],
    ) -> dict[str, tuple[float, float]]:
        # Cross-check the exact hardware->model conversion used by sync/solve.
        # The former implementation intentionally evaluated raw joint values,
        # so a bad configured offset could pass this guard while IK used a pose
        # hundreds of millimetres away from the real arm.
        model_q = self._pack_model(measured_hardware)
        try:
            model_world = self._kinematic_transforms(model_q)
            return {
                arm: self._errors(
                    np.linalg.inv(self.base_world[arm]) @ model_world[arm],
                    np.asarray(driver_tcp_local[arm], dtype=np.float64),
                )
                for arm in driver_tcp_local
            }
        finally:
            self.sync(measured_hardware)

    def _goal_pose(self, transform: np.ndarray):
        quaternion_xyzw = Rotation.from_matrix(transform[:3, :3]).as_quat()
        quaternion_wxyz = np.asarray(
            [
                quaternion_xyzw[3],
                quaternion_xyzw[0],
                quaternion_xyzw[1],
                quaternion_xyzw[2],
            ],
            dtype=np.float32,
        )
        return self.Pose(
            position=self._tensor(transform[:3, 3].astype(np.float32)).view(1, 3),
            quaternion=self._tensor(quaternion_wxyz).view(1, 4),
        )

    def _validate_interpolated_step(
        self, current: np.ndarray, candidate: np.ndarray
    ) -> None:
        alphas = self.torch.linspace(
            0.0,
            1.0,
            self.collision_interpolation_steps,
            dtype=self.torch.float32,
            device=self.device,
        )
        current_tensor = self._tensor(current)
        delta_tensor = self._tensor(candidate - current)
        trajectory = current_tensor.view(1, 1, -1) + (
            alphas.view(1, -1, 1) * delta_tensor.view(1, 1, -1)
        )
        valid = self._configuration_valid(trajectory)[0]
        if not bool(self.torch.all(valid).item()) and not self._trajectory_escape_allowed(
            trajectory
        ):
            first = int(self.torch.nonzero(~valid, as_tuple=False)[0, 0].item())
            reason = self._invalid_configuration_reason(
                trajectory[:, first : first + 1, :]
            )
            raise IkSafetyError(
                f"cuRobo rejected interpolation sample {first + 1}/"
                f"{self.collision_interpolation_steps}: {reason}"
            )

    def _build_collision_pair_tolerances(self):
        checker = self.collision_checker
        kinematics_config = checker.kinematics.config.kinematics_config
        collision_config = checker.kinematics.config.self_collision_config
        pairs = collision_config.collision_pairs.to(dtype=self.torch.long)
        sphere_to_link = kinematics_config.link_sphere_idx_map
        link_names = {
            value: key
            for key, value in kinematics_config.link_name_to_idx_map.items()
        }
        tolerances = []
        for pair in pairs:
            first_link = link_names[int(sphere_to_link[int(pair[0].item())].item())]
            second_link = link_names[int(sphere_to_link[int(pair[1].item())].item())]
            tolerances.append(
                self_collision_pair_tolerance_m(
                    first_link,
                    second_link,
                    self.self_collision_mesh_fit_tolerance_m,
                )
            )
        return self.torch.as_tensor(
            tolerances, dtype=self.torch.float32, device=self.device
        )

    def _build_collision_pair_escape_mask(self) -> np.ndarray:
        checker = self.collision_checker
        kinematics_config = checker.kinematics.config.kinematics_config
        collision_config = checker.kinematics.config.self_collision_config
        pairs = collision_config.collision_pairs.to(dtype=self.torch.long)
        sphere_to_link = kinematics_config.link_sphere_idx_map
        link_names = {
            value: key
            for key, value in kinematics_config.link_name_to_idx_map.items()
        }
        return np.asarray(
            [
                self_collision_pair_escape_allowed(
                    link_names[
                        int(sphere_to_link[int(pair[0].item())].item())
                    ],
                    link_names[
                        int(sphere_to_link[int(pair[1].item())].item())
                    ],
                )
                for pair in pairs
            ],
            dtype=bool,
        )

    def _self_collision_gaps(self, robot_spheres):
        collision_config = (
            self.collision_checker.kinematics.config.self_collision_config
        )
        pairs = collision_config.collision_pairs.to(dtype=self.torch.long)
        first_spheres = robot_spheres[..., pairs[:, 0], :]
        second_spheres = robot_spheres[..., pairs[:, 1], :]
        padding = collision_config.sphere_padding
        return (
            self.torch.linalg.vector_norm(
                first_spheres[..., :3] - second_spheres[..., :3], dim=-1
            )
            - first_spheres[..., 3]
            - second_spheres[..., 3]
            - padding[pairs[:, 0]]
            - padding[pairs[:, 1]]
        )

    def _configuration_valid(self, q):
        """Validate bounds and collisions with one measured sphere-fit margin.

        Only the same-arm base/link2 pairs receive the small margin. All other
        self/cross-arm pairs, joint bounds, and any future world collision
        constraint retain cuRobo's strict zero-penetration rule.
        """

        checker = self.collision_checker
        checker.setup_batch_tensors(q.shape[0], q.shape[1])
        state = checker.get_kinematics(q)
        valid = self.torch.all(checker.get_bound(q) <= 0.0, dim=-1)
        gaps = self._self_collision_gaps(state.robot_spheres)
        valid = valid & self.torch.all(
            gaps >= -self._collision_pair_tolerances.view(1, 1, -1), dim=-1
        )
        if checker.collision_constraint is not None:
            world_cost = checker.get_collision_constraint(state)
            valid = valid & (self.torch.sum(world_cost, dim=-1) == 0.0)
        return valid

    def _trajectory_escape_allowed(
        self,
        q,
        *,
        max_initial_overlap_m: float | None = None,
        require_final_clearance: bool = False,
    ) -> bool:
        """Permit only monotonic escape from a shallow approved sphere overlap."""

        if q.shape[0] != 1 or q.shape[1] < 2:
            return False
        checker = self.collision_checker
        checker.setup_batch_tensors(q.shape[0], q.shape[1])
        if not bool(self.torch.all(checker.get_bound(q) <= 0.0).item()):
            return False
        state = checker.get_kinematics(q)
        clearances = (
            self._self_collision_gaps(state.robot_spheres)
            + self._collision_pair_tolerances.view(1, 1, -1)
        )
        if checker.collision_constraint is not None:
            world_cost = checker.get_collision_constraint(state)
            if not bool((self.torch.sum(world_cost, dim=-1) == 0.0).all().item()):
                return False
        return shallow_collision_escape_allowed(
            clearances[0].detach().cpu().numpy(),
            self._collision_pair_escape_mask,
            (
                self.collision_escape_max_initial_overlap_m
                if max_initial_overlap_m is None
                else float(max_initial_overlap_m)
            ),
            require_final_clearance=require_final_clearance,
        )

    def _invalid_configuration_reason(self, q_sample) -> str:
        """Explain a cuRobo validation failure without weakening its checks."""
        checker = self.collision_checker
        bound_cost = checker.get_bound(q_sample)[0, 0]
        bound_indices = self.torch.nonzero(
            bound_cost > 0.0, as_tuple=False
        ).flatten()
        if bound_indices.numel() > 0:
            index = int(bound_indices[0].item())
            limits = checker.kinematics.get_joint_limits().position
            value = float(q_sample[0, 0, index].item())
            lower = float(limits[0, index].item())
            upper = float(limits[1, index].item())
            return (
                f"joint limit {self.joint_names[index]}={math.degrees(value):.2f}deg "
                f"outside [{math.degrees(lower):.2f}, {math.degrees(upper):.2f}]deg"
            )

        state = checker.get_kinematics(q_sample)
        gaps = self._self_collision_gaps(state.robot_spheres)[0, 0]
        threshold_clearance = gaps + self._collision_pair_tolerances
        if bool(self.torch.any(threshold_clearance < 0.0).item()):
            kinematics_config = checker.kinematics.config.kinematics_config
            collision_config = checker.kinematics.config.self_collision_config
            pairs = collision_config.collision_pairs.to(dtype=self.torch.long)
            pair_index = int(self.torch.argmin(threshold_clearance).item())
            first_index = int(pairs[pair_index, 0].item())
            second_index = int(pairs[pair_index, 1].item())
            sphere_to_link = kinematics_config.link_sphere_idx_map
            link_names = {
                value: key
                for key, value in kinematics_config.link_name_to_idx_map.items()
            }
            first_link = link_names[int(sphere_to_link[first_index].item())]
            second_link = link_names[int(sphere_to_link[second_index].item())]
            gap_mm = float(gaps[pair_index].item()) * 1000.0
            fit_tolerance_mm = (
                float(self._collision_pair_tolerances[pair_index].item()) * 1000.0
            )
            return (
                f"self/cross-arm collision {first_link} <-> {second_link}, "
                f"sphere gap {gap_mm:.2f}mm "
                f"(mesh-fit tolerance {fit_tolerance_mm:.2f}mm)"
            )

        return "unknown joint-limit or collision constraint"

    @staticmethod
    def _made_progress(
        before_position: float,
        before_orientation: float,
        after_position: float,
        after_orientation: float,
    ) -> bool:
        orientation_gate = math.radians(1.0)
        if before_position > 1e-4 and before_orientation < orientation_gate:
            return after_position < before_position - 1e-8
        if before_orientation > orientation_gate and before_position <= 1e-4:
            return after_orientation < before_orientation - 1e-8
        before_score = before_position / 0.01 + before_orientation / 0.1
        after_score = after_position / 0.01 + after_orientation / 0.1
        return after_score < before_score - 1e-8

    def solve(
        self,
        targets_world: Mapping[str, np.ndarray],
        active_arms: set[str],
    ) -> IkResult:
        if self.measured_hardware is None or self.model_q is None:
            raise IkSafetyError("IK cannot run before joint feedback is synchronized")
        if not active_arms or not active_arms.issubset(ARM_NAMES):
            raise ValueError("active_arms must be a non-empty subset of arm_a/arm_b")

        before_errors = {}
        goal_poses = {}
        for arm in ARM_NAMES:
            current = self.current_tcp_world(arm)
            full_target = (
                np.asarray(targets_world[arm], dtype=np.float64)
                if arm in active_arms
                else current
            )
            if full_target.shape != (4, 4) or not np.all(np.isfinite(full_target)):
                raise IkSafetyError(f"{arm} target must be a finite 4x4 transform")
            before_errors[arm] = self._errors(current, full_target)
            # SeedIK is a local LM solver.  Asking it to solve a far-away
            # teleoperation target (the captured logs reached 0.42 m) can
            # produce a joint direction that gets worse after the mandatory
            # per-cycle joint bound is applied.  Give cuRobo a nearby Cartesian
            # waypoint while retaining the full target for progress scoring.
            waypoint = (
                step_towards(
                    current,
                    full_target,
                    self.max_cartesian_step_m,
                    self.max_orientation_step_rad,
                )
                if arm in active_arms
                else current
            )
            goal_poses[f"{arm}_tcp_link"] = self._goal_pose(waypoint)

        goal = self.GoalToolPose.from_poses(
            goal_poses,
            ordered_tool_frames=self.tool_frames,
            num_goalset=1,
        )
        try:
            result = self.solver.solve_single(
                goal_tool_poses=goal,
                current_state=self._joint_state(self.model_q),
                return_seeds=1,
            )
        except RuntimeError as exc:
            raise IkSafetyError(f"cuRobo IK solver failed: {exc}") from exc

        candidate = (
            result.js_solution.position[0, 0]
            .detach()
            .cpu()
            .numpy()
            .astype(np.float64)
        )
        if candidate.shape != (14,) or not np.all(np.isfinite(candidate)):
            raise IkSafetyError("cuRobo IK produced non-finite joints")
        active_indices = [
            index
            for arm in ARM_NAMES
            if arm in active_arms
            for index in range(
                self.arm_slices[arm].start, self.arm_slices[arm].stop
            )
        ]
        bounded, _ = bounded_joint_candidate(
            self.model_q,
            candidate,
            active_indices,
            self.max_joint_step_rad,
        )
        self._validate_interpolated_step(self.model_q, bounded)
        tcp_world = self._kinematic_transforms(bounded)

        commands = {}
        position_errors = {}
        orientation_errors = {}
        for arm in ARM_NAMES:
            arm_slice = self.arm_slices[arm]
            commands[arm] = bounded[arm_slice] - self.offsets[arm]
            target = (
                np.asarray(targets_world[arm], dtype=np.float64)
                if arm in active_arms
                else tcp_world[arm]
            )
            position_errors[arm], orientation_errors[arm] = self._errors(
                tcp_world[arm], target
            )
            if arm in active_arms and not self._made_progress(
                *before_errors[arm],
                position_errors[arm],
                orientation_errors[arm],
            ) and (
                before_errors[arm][0] > 1e-5
                or before_errors[arm][1] > 1e-4
            ):
                # No unsafe command has been published: this is a transient
                # local-solver miss, not a collision or hardware safety fault.
                # The caller holds the last safe command and retries next tick.
                raise IkNoProgressError(
                    f"{arm} cuRobo step did not reduce Cartesian residual "
                    f"({before_errors[arm][0]:.6f}m -> "
                    f"{position_errors[arm]:.6f}m)"
                )

        return IkResult(
            joint_commands=commands,
            tcp_world=tcp_world,
            position_errors_m=position_errors,
            orientation_errors_rad=orientation_errors,
        )
