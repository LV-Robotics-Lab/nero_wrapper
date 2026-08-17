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
    HARDWARE_TO_MODEL_JOINT_SIGNS,
    LAB_DUAL_BENCH_BASE_TRANSFORMS,
    BaseTransform,
    build_dual_nero_urdf,
)
from .ik_geometry import step_towards


class IkSafetyError(RuntimeError):
    pass


class IkNoProgressError(RuntimeError):
    """A safe IK attempt produced no useful Cartesian motion this cycle."""


class IkCollisionBlockedError(IkNoProgressError, IkSafetyError):
    """The requested local step was blocked, so holding and reversal are safe.

    This deliberately inherits from both public error categories.  Existing
    safety audits can still classify the event as a collision rejection, while
    the teleoperation loop catches it as a non-latching hold/retry condition.
    No joint command is returned for a blocked step.
    """


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

# Recovery parking is the only caller allowed to use this wider envelope.  The
# 2026-08-13 field start captured a 9.933 mm link5/estimated-tool sphere-model
# overlap.  A complete independent-arm progress grid showed that every affected
# pair was non-deepening and ended collision-free; 10.5 mm leaves 0.567 mm for
# feedback/numerical variation without weakening normal Cartesian validation.
_PARK_RECOVERY_MAX_INITIAL_OVERLAP_M = 0.0105


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


def cross_arm_pair_clearance_m(
    first_link: str,
    second_link: str,
    safety_margin_m: float,
) -> float:
    """Return an explicit surface clearance only for different-arm pairs."""

    arms = {
        link.split("_", 2)[1]
        for link in (first_link, second_link)
        if link.startswith("arm_a_") or link.startswith("arm_b_")
    }
    return float(safety_margin_m) if arms == {"a", "b"} else 0.0


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


def bounded_joint_candidate_by_groups(
    current: np.ndarray,
    candidate: np.ndarray,
    active_groups: Sequence[Sequence[int]],
    max_joint_step_rad: float,
) -> tuple[np.ndarray, tuple[float, ...]]:
    """Bound coordinated joint steps independently for each active arm/group."""

    current = np.asarray(current, dtype=np.float64)
    candidate = np.asarray(candidate, dtype=np.float64)
    if current.shape != candidate.shape or current.ndim != 1:
        raise ValueError("current and candidate must be equal one-dimensional arrays")
    if max_joint_step_rad <= 0.0:
        raise ValueError("max_joint_step_rad must be positive")

    result = current.copy()
    scales: list[float] = []
    used_indices: set[int] = set()
    groups = tuple(tuple(int(index) for index in group) for group in active_groups)
    if not groups or any(not group for group in groups):
        raise ValueError("at least one non-empty active group is required")
    for group in groups:
        if len(set(group)) != len(group):
            raise ValueError("active group contains duplicate joint indices")
        if any(index < 0 or index >= current.size for index in group):
            raise ValueError("active joint index is out of range")
        if used_indices.intersection(group):
            raise ValueError("active joint groups must not overlap")
        used_indices.update(group)
        active = np.asarray(group, dtype=int)
        delta = candidate[active] - current[active]
        largest = float(np.max(np.abs(delta)))
        scale = (
            1.0
            if largest <= max_joint_step_rad
            else max_joint_step_rad / largest
        )
        result[active] = current[active] + scale * delta
        scales.append(scale)
    return result, tuple(scales)


def normalized_joint_motion_rms(
    current: np.ndarray,
    candidate: np.ndarray,
    active_indices: Sequence[int],
    max_joint_step_rad: float,
) -> float:
    """Return active-joint RMS travel as a fraction of one allowed step."""

    current = np.asarray(current, dtype=np.float64)
    candidate = np.asarray(candidate, dtype=np.float64)
    if (
        current.shape != candidate.shape
        or current.ndim != 1
        or not np.all(np.isfinite(current))
        or not np.all(np.isfinite(candidate))
    ):
        raise ValueError(
            "current and candidate must be equal finite one-dimensional arrays"
        )
    if not math.isfinite(max_joint_step_rad) or max_joint_step_rad <= 0.0:
        raise ValueError("max_joint_step_rad must be positive and finite")
    active = np.asarray(tuple(active_indices), dtype=int)
    if active.size == 0:
        raise ValueError("at least one active joint is required")
    if np.any(active < 0) or np.any(active >= current.size):
        raise ValueError("active joint index is out of range")
    normalized = (candidate[active] - current[active]) / max_joint_step_rad
    return float(np.sqrt(np.mean(np.square(normalized))))


def candidate_ranking_score(
    pose_score: float,
    neutral_posture: float,
    joint_motion_rms: float,
    *,
    elbow_posture_weight: float,
    joint_motion_weight: float,
    solver_success: bool,
    seed_switch_penalty: float = 0.0,
    switching_seed: bool = False,
) -> float:
    """Score one bounded IK result with optional seed-choice hysteresis.

    The switch cost changes only the discrete candidate ordering.  It does not
    filter, delay, or integrate the Cartesian target, and a meaningfully better
    candidate can still replace the previous seed immediately.
    """

    values = (
        pose_score,
        neutral_posture,
        joint_motion_rms,
        elbow_posture_weight,
        joint_motion_weight,
        seed_switch_penalty,
    )
    if not all(math.isfinite(value) for value in values):
        raise ValueError("candidate score inputs must be finite")
    if pose_score < 0.0 or neutral_posture < 0.0 or joint_motion_rms < 0.0:
        raise ValueError("candidate score components must be non-negative")
    if not 0.0 <= elbow_posture_weight <= 1.0:
        raise ValueError("elbow posture weight must be between 0 and 1")
    if not 0.0 <= joint_motion_weight <= 1.0:
        raise ValueError("joint motion weight must be between 0 and 1")
    if seed_switch_penalty < 0.0:
        raise ValueError("seed switch penalty must be non-negative")
    return (
        pose_score
        + elbow_posture_weight * neutral_posture
        + joint_motion_weight * joint_motion_rms
        + (0.0 if solver_success else 0.02)
        + (seed_switch_penalty if switching_seed else 0.0)
    )


def balanced_elbow_seed_patterns(
    active_elbow_count: int,
    num_seeds: int = 5,
) -> tuple[tuple[float, ...], ...]:
    """Return stable per-arm labels for the deterministic elbow seeds."""

    if active_elbow_count < 1:
        raise ValueError("at least one active elbow is required")
    if num_seeds < 1:
        raise ValueError("num_seeds must be positive")
    if active_elbow_count == 1:
        patterns = ((0.0,), (1.0,), (-1.0,), (2.0,), (-2.0,))
    elif active_elbow_count == 2:
        patterns = (
            (0.0, 0.0),
            (1.0, 1.0),
            (-1.0, -1.0),
            (1.0, -1.0),
            (-1.0, 1.0),
        )
    else:
        patterns = (tuple(0.0 for _ in range(active_elbow_count)),)
        for level in range(1, num_seeds):
            magnitude = float((level + 1) // 2)
            direction = 1.0 if level % 2 else -1.0
            patterns += (
                tuple(direction * magnitude for _ in range(active_elbow_count)),
            )
    return tuple(patterns[min(index, len(patterns) - 1)] for index in range(num_seeds))


def balanced_elbow_seed_configs(
    current: np.ndarray,
    active_elbow_indices: Sequence[int],
    lower_bounds: np.ndarray,
    upper_bounds: np.ndarray,
    seed_offset_rad: float,
    num_seeds: int = 5,
) -> np.ndarray:
    """Build deterministic local seeds on both sides of the current J2 state.

    The installed arms use a negative hardware-to-model J2 sign. Searching
    symmetrically in model coordinates therefore avoids embedding either an
    inward or outward hardware bias in the solver branch selection.
    """

    current = np.asarray(current, dtype=np.float64)
    lower = np.asarray(lower_bounds, dtype=np.float64)
    upper = np.asarray(upper_bounds, dtype=np.float64)
    if (
        current.ndim != 1
        or lower.shape != current.shape
        or upper.shape != current.shape
        or not np.all(np.isfinite(current))
        or not np.all(np.isfinite(lower))
        or not np.all(np.isfinite(upper))
    ):
        raise ValueError("seed state and joint bounds must be equal finite vectors")
    if not math.isfinite(seed_offset_rad) or seed_offset_rad <= 0.0:
        raise ValueError("elbow seed offset must be positive and finite")
    if num_seeds < 1:
        raise ValueError("num_seeds must be positive")
    elbow_indices = tuple(int(index) for index in active_elbow_indices)
    if len(set(elbow_indices)) != len(elbow_indices):
        raise ValueError("active elbow indices must be unique")
    if any(index < 0 or index >= current.size for index in elbow_indices):
        raise ValueError("active elbow index is out of range")

    patterns = balanced_elbow_seed_patterns(len(elbow_indices), num_seeds)

    seeds = np.repeat(current[None, :], num_seeds, axis=0)
    for seed_index in range(1, num_seeds):
        pattern = patterns[seed_index]
        for elbow_index, multiplier in zip(elbow_indices, pattern):
            seeds[seed_index, elbow_index] += multiplier * seed_offset_rad
    return np.clip(seeds, lower[None, :], upper[None, :])


def limit_elbow_step(
    current: np.ndarray,
    candidate: np.ndarray,
    active_elbow_indices: Sequence[int],
    max_step_rad: float,
) -> np.ndarray:
    """Apply the same per-cycle J2 bound in both physical directions."""

    current = np.asarray(current, dtype=np.float64)
    candidate = np.asarray(candidate, dtype=np.float64)
    if current.shape != candidate.shape or current.ndim != 1:
        raise ValueError("current and candidate must be equal vectors")
    if not math.isfinite(max_step_rad) or max_step_rad <= 0.0:
        raise ValueError("max elbow step must be positive and finite")
    result = candidate.copy()
    for raw_index in active_elbow_indices:
        index = int(raw_index)
        if index < 0 or index >= current.size:
            raise ValueError("active elbow index is out of range")
        result[index] = float(
            np.clip(
                result[index],
                current[index] - max_step_rad,
                current[index] + max_step_rad,
            )
        )
    return result


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
        joint_signs: Mapping[str, Sequence[float]] = HARDWARE_TO_MODEL_JOINT_SIGNS,
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
        num_seeds: int = 5,
        max_iterations: int = 8,
        elbow_seed_offset_rad: float = math.radians(10.0),
        max_elbow_step_rad: float = math.radians(1.0),
        elbow_posture_weight: float = 0.10,
        joint_motion_weight: float = 0.20,
        seed_switch_penalty: float = 0.20,
        cross_arm_safety_margin_m: float = 0.010,
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
        if num_seeds != 5:
            raise ValueError("dual-NERO IK currently requires exactly five seeds")
        if (
            not isinstance(max_iterations, int)
            or isinstance(max_iterations, bool)
            or not 4 <= max_iterations <= 50
        ):
            raise ValueError("IK maximum iterations must be an integer from 4 to 50")
        if (
            not math.isfinite(elbow_seed_offset_rad)
            or elbow_seed_offset_rad <= 0.0
            or elbow_seed_offset_rad > math.radians(30.0)
        ):
            raise ValueError("elbow seed offset must be in (0, 30deg]")
        if (
            not math.isfinite(max_elbow_step_rad)
            or max_elbow_step_rad <= 0.0
            or max_elbow_step_rad > max_joint_step_rad
        ):
            raise ValueError(
                "maximum elbow step must be positive and no larger "
                "than the joint step"
            )
        if (
            not math.isfinite(elbow_posture_weight)
            or elbow_posture_weight < 0.0
            or elbow_posture_weight > 1.0
        ):
            raise ValueError("elbow posture weight must be between 0 and 1")
        if (
            not math.isfinite(joint_motion_weight)
            or joint_motion_weight < 0.0
            or joint_motion_weight > 1.0
        ):
            raise ValueError("joint motion weight must be between 0 and 1")
        if (
            not math.isfinite(seed_switch_penalty)
            or seed_switch_penalty < 0.0
            or seed_switch_penalty > 2.0
        ):
            raise ValueError("seed switch penalty must be between 0 and 2")
        if (
            not math.isfinite(cross_arm_safety_margin_m)
            or cross_arm_safety_margin_m < 0.0
            or cross_arm_safety_margin_m > 0.030
        ):
            raise ValueError("cross-arm safety margin must be between 0 and 30mm")
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
            or collision_escape_max_initial_overlap_m > 0.003
        ):
            raise ValueError(
                "collision escape maximum overlap must be between 0 and 3mm"
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
        # The Cartesian process already has independent ROS workers for input,
        # feedback and clutch edges.  Letting PyTorch create ten host workers
        # for these small GPU launches caused 60--300 ms scheduling bursts in
        # the 2026-08-14 Shadow trace.  One host worker leaves CUDA parallelism
        # untouched and makes launch/synchronization latency deterministic.
        torch.set_num_threads(1)
        try:
            torch.set_num_interop_threads(1)
        except RuntimeError:
            # PyTorch only permits changing this setting before its first
            # inter-op launch.  A library embedding the wrapper may have
            # initialized it already; in that case retain the existing safe
            # setting instead of preventing construction.
            pass
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
        self.signs = {
            arm: np.asarray(joint_signs[arm], dtype=np.float64)
            for arm in ARM_NAMES
        }
        for arm in ARM_NAMES:
            if self.offsets[arm].shape != (7,) or not np.all(
                np.isfinite(self.offsets[arm])
            ):
                raise ValueError(
                    f"{arm} joint offset must contain seven finite values"
                )
            if self.signs[arm].shape != (7,) or not np.all(
                np.isin(self.signs[arm], (-1.0, 1.0))
            ):
                raise ValueError(
                    f"{arm} joint signs must contain seven +1/-1 values"
                )
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
            default_model_positions.append(
                self.offsets[arm] + self.signs[arm] * hardware_position
            )
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
        self.num_seeds = int(num_seeds)
        self.max_iterations = int(max_iterations)
        self.elbow_seed_offset_rad = float(elbow_seed_offset_rad)
        self.max_elbow_step_rad = float(max_elbow_step_rad)
        self.elbow_posture_weight = float(elbow_posture_weight)
        self.joint_motion_weight = float(joint_motion_weight)
        self.seed_switch_penalty = float(seed_switch_penalty)
        self.cross_arm_safety_margin_m = float(cross_arm_safety_margin_m)
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
        self._collision_interpolation_alphas = torch.linspace(
            0.0,
            1.0,
            self.collision_interpolation_steps,
            dtype=torch.float32,
            device=self.device,
        )

        robot_config, temporary_urdf = self._robot_config(
            urdf_path,
            base_transforms,
            joint_offsets,
            joint_signs,
            tcp_offsets,
            tool_collision_model_path,
        )
        try:
            def solver_configuration(seed_count: int):
                return SeedIKSolverCfg.create(
                    robot=robot_config,
                    num_seeds=seed_count,
                    max_iterations=self.max_iterations,
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

            # The one-seed graph is the normal local-continuity path.  The
            # original five-seed graph remains resident as a deterministic
            # fallback for collision, convergence and branch misses.
            self.fast_solver = SeedIKSolver(solver_configuration(1))
            self.solver = SeedIKSolver(solver_configuration(self.num_seeds))
            self._joint_lower_model = (
                self.solver.action_min.detach().cpu().numpy().astype(np.float64)
            )
            self._joint_upper_model = (
                self.solver.action_max.detach().cpu().numpy().astype(np.float64)
            )
            checker_config = RobotCollisionCheckerCfg.load_from_config(
                robot_config=robot_config,
                self_collision_activation_distance=0.0,
            )
            self.collision_checker = RobotCollisionChecker(checker_config)
            self._collision_pair_tolerances = self._build_collision_pair_tolerances()
            self._collision_pair_required_clearances = (
                self._build_collision_pair_required_clearances()
            )
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
        self.command_reference_hardware: dict[str, np.ndarray] | None = None
        self.model_q: np.ndarray | None = None
        self.tcp_world: dict[str, np.ndarray] = {}
        self.last_solve_diagnostics: dict[str, object] = {}
        self.solve_attempt_sequence = 0
        self.last_solve_outcome = "never"
        self.last_solve_result: IkResult | None = None
        self.command_reference_fk_reuse_count = 0
        self.command_reference_fk_compute_count = 0
        self._last_selected_seed_rank: dict[tuple[str, ...], int] = {}
        self._last_selected_seed_direction: dict[str, float] = {}
        self.require_cartesian_progress = True
        self.warmup_seconds = self._warm_up()

    def configure_elbow_policy(
        self,
        *,
        elbow_seed_offset_rad: float,
        max_elbow_step_rad: float,
        elbow_posture_weight: float,
    ) -> None:
        """Apply audited runtime posture settings after ROS parameter loading."""

        if (
            not math.isfinite(elbow_seed_offset_rad)
            or elbow_seed_offset_rad <= 0.0
            or elbow_seed_offset_rad > math.radians(30.0)
        ):
            raise ValueError("elbow seed offset must be in (0, 30deg]")
        if (
            not math.isfinite(max_elbow_step_rad)
            or max_elbow_step_rad <= 0.0
            or max_elbow_step_rad > self.max_joint_step_rad
        ):
            raise ValueError(
                "maximum elbow step must be positive and no larger "
                "than the joint step"
            )
        if (
            not math.isfinite(elbow_posture_weight)
            or elbow_posture_weight < 0.0
            or elbow_posture_weight > 1.0
        ):
            raise ValueError("elbow posture weight must be between 0 and 1")
        self.elbow_seed_offset_rad = float(elbow_seed_offset_rad)
        self.max_elbow_step_rad = float(max_elbow_step_rad)
        self.elbow_posture_weight = float(elbow_posture_weight)

    def configure_cross_arm_margin(self, safety_margin_m: float) -> None:
        if (
            not math.isfinite(safety_margin_m)
            or safety_margin_m < 0.0
            or safety_margin_m > 0.030
        ):
            raise ValueError("cross-arm safety margin must be between 0 and 30mm")
        self.cross_arm_safety_margin_m = float(safety_margin_m)
        self._collision_pair_required_clearances = (
            self._build_collision_pair_required_clearances()
        )

    def configure_candidate_scoring(self, *, joint_motion_weight: float) -> None:
        """Prefer shorter bounded joint solutions without filtering targets."""

        if (
            not math.isfinite(joint_motion_weight)
            or joint_motion_weight < 0.0
            or joint_motion_weight > 1.0
        ):
            raise ValueError("joint motion weight must be between 0 and 1")
        self.joint_motion_weight = float(joint_motion_weight)

    def configure_seed_hysteresis(self, *, switch_penalty: float) -> None:
        """Keep a stable seed unless another candidate is materially better."""

        if (
            not math.isfinite(switch_penalty)
            or switch_penalty < 0.0
            or switch_penalty > 2.0
        ):
            raise ValueError("seed switch penalty must be between 0 and 2")
        self.seed_switch_penalty = float(switch_penalty)

    def reset_seed_continuity(self, arms: set[str] | None = None) -> None:
        """Forget seed-direction history at a clutch/session boundary."""

        reset_arms = set(ARM_NAMES) if arms is None else set(arms)
        if not reset_arms.issubset(ARM_NAMES):
            raise ValueError("seed continuity arms must be arm_a and/or arm_b")
        for arm in reset_arms:
            self._last_selected_seed_direction.pop(arm, None)
        self._last_selected_seed_rank = {
            key: rank
            for key, rank in self._last_selected_seed_rank.items()
            if reset_arms.isdisjoint(key)
        }

    def _joint_step_max_by_arm_deg(
        self,
        current: np.ndarray,
        candidate: np.ndarray,
        arms: Sequence[str],
    ) -> dict[str, float]:
        """Report each arm's step using the model's existing arm slices."""

        current_values = np.asarray(current, dtype=np.float64)
        candidate_values = np.asarray(candidate, dtype=np.float64)
        if (
            current_values.shape != candidate_values.shape
            or current_values.ndim != 1
            or not np.all(np.isfinite(current_values))
            or not np.all(np.isfinite(candidate_values))
        ):
            raise ValueError(
                "current and candidate must be equal finite joint vectors"
            )
        result: dict[str, float] = {}
        for arm in arms:
            if arm not in ARM_NAMES:
                raise ValueError(f"unknown arm {arm!r}")
            arm_slice = self.arm_slices[arm]
            result[arm] = round(
                math.degrees(
                    float(
                        np.max(
                            np.abs(
                                candidate_values[arm_slice]
                                - current_values[arm_slice]
                            )
                        )
                    )
                ),
                3,
            )
        return result

    def configure_progress_policy(
        self, *, require_cartesian_progress: bool
    ) -> None:
        """Select whether a collision-safe local step may slightly regress.

        Strict progress is useful for offline convergence checks, but on a
        continuously moving teleoperation target it can turn harmless solver
        noise into repeated command holds.  Disabling it still ranks candidates
        by Cartesian residual and preserves joint bounds and collision checks.
        """

        if not isinstance(require_cartesian_progress, bool):
            raise ValueError("require_cartesian_progress must be true or false")
        self.require_cartesian_progress = require_cartesian_progress

    def _active_elbow_indices(self, active_arms: set[str]) -> tuple[int, ...]:
        return tuple(
            self.arm_slices[arm].start + 1
            for arm in ARM_NAMES
            if arm in active_arms
        )

    def _seed_configs(
        self,
        current: np.ndarray,
        active_arms: set[str],
    ) -> np.ndarray:
        return balanced_elbow_seed_configs(
            current,
            self._active_elbow_indices(active_arms),
            self._joint_lower_model,
            self._joint_upper_model,
            self.elbow_seed_offset_rad,
            self.num_seeds,
        )

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
        joint_signs: Mapping[str, Sequence[float]],
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
            joint_signs=joint_signs,
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
        # One invocation is sufficient: GraphExecutor itself performs three
        # capture warm-ups and one replay. Repeated zero-pose solves can leave
        # the LM implementation on a redundant null-space solution even though
        # the TCP error is zero, which makes the first live solve choose a
        # different joint branch. Warm every steady-state shape exactly once.
        fast_result = self.fast_solver.solve_single(
            goal_tool_poses=goal,
            current_state=joint_state,
            seed_config=self._tensor(default_model).view(1, 1, -1),
            return_seeds=1,
        )
        self._kinematic_transforms_batch(default_model[None, :])
        # Idle FK validation packs raw-driver and calibrated states into two
        # rows. Warm that distinct allocation shape before the first feedback
        # pair; otherwise startup records one isolated ~20 ms control tick.
        self._kinematic_transforms_batch(
            np.repeat(default_model[None, :], 2, axis=0)
        )
        rejections = self._interpolated_candidate_rejections(
            default_model,
            default_model[None, :],
        )
        if rejections != [None]:
            raise RuntimeError(
                "cuRobo default dual-NERO interpolation warm-up is invalid"
            )
        result = self.solver.solve_single(
            goal_tool_poses=goal,
            current_state=joint_state,
            seed_config=self._tensor(
                self._seed_configs(default_model, set(ARM_NAMES))
            ).view(1, self.num_seeds, -1),
            return_seeds=1,
        )
        self.torch.cuda.synchronize(self.device)
        if (
            fast_result is None
            or not bool(fast_result.success.item())
            or not bool(result.success.item())
        ):
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
        values = np.asarray(model_q, dtype=np.float64)
        if values.shape != (14,) or not np.all(np.isfinite(values)):
            raise IkSafetyError("model joints must contain fourteen finite values")
        return self._kinematic_transforms_batch(values[None, :])[0]

    def _kinematic_transforms_batch(
        self, model_q: np.ndarray
    ) -> list[dict[str, np.ndarray]]:
        """Compute all candidate TCP transforms in one GPU kinematics call."""

        values = np.asarray(model_q, dtype=np.float64)
        if (
            values.ndim != 2
            or values.shape[1] != 14
            or values.shape[0] < 1
            or not np.all(np.isfinite(values))
        ):
            raise IkSafetyError(
                "batched model joints must be a non-empty finite Nx14 matrix"
            )
        state = self.solver.compute_kinematics(
            self.JointState.from_position(
                self._tensor(values),
                joint_names=self.joint_names,
            )
        )
        poses = state.tool_poses.to_dict()
        result = [dict() for _ in range(values.shape[0])]
        # One packed device-to-host transfer avoids four implicit CUDA
        # synchronizations (position/quaternion for each arm) on every solve.
        packed = self.torch.cat(
            tuple(
                self.torch.cat(
                    (
                        poses[f"{arm}_tcp_link"].position,
                        poses[f"{arm}_tcp_link"].quaternion,
                    ),
                    dim=-1,
                )
                for arm in ARM_NAMES
            ),
            dim=-1,
        ).detach().cpu().numpy().astype(np.float64)
        for index, row in enumerate(packed):
            for arm_index, arm in enumerate(ARM_NAMES):
                offset = arm_index * 7
                result[index][arm] = self._pose_transform(
                    row[offset : offset + 3],
                    row[offset + 3 : offset + 7],
                )
        return result

    def _pack_model(self, measured_hardware: Mapping[str, Sequence[float]]) -> np.ndarray:
        measured = []
        for arm in ARM_NAMES:
            values = np.asarray(measured_hardware[arm], dtype=np.float64)
            if values.shape != (7,) or not np.all(np.isfinite(values)):
                raise IkSafetyError(
                    f"{arm} joint feedback must contain seven finite values"
                )
            measured.append(self.offsets[arm] + self.signs[arm] * values)
        return np.concatenate(measured)

    def _model_to_hardware(self, arm: str, model_values: np.ndarray) -> np.ndarray:
        """Convert one model-space joint vector back to hardware coordinates."""

        values = np.asarray(model_values, dtype=np.float64)
        if values.shape != (7,) or not np.all(np.isfinite(values)):
            raise IkSafetyError(
                f"{arm} model joints must contain seven finite values"
            )
        # Every sign is +/-1, so the inverse affine transform uses the same
        # sign vector: q_hardware = sign * (q_model - offset).
        return self.signs[arm] * (values - self.offsets[arm])

    def sync(self, measured_hardware: Mapping[str, Sequence[float]]) -> None:
        model_q = self._pack_model(measured_hardware)
        self.measured_hardware = {
            arm: np.asarray(measured_hardware[arm], dtype=np.float64).copy()
            for arm in ARM_NAMES
        }
        self.command_reference_hardware = {
            arm: values.copy() for arm, values in self.measured_hardware.items()
        }
        self.model_q = model_q
        self.tcp_world = self._kinematic_transforms(model_q)

    def update_measured_feedback(
        self,
        measured_hardware: Mapping[str, Sequence[float]],
        *,
        compute_tcp: bool = False,
    ) -> dict[str, np.ndarray] | None:
        """Refresh physical joints without destroying the cached command state.

        Active Execute uses measured joints as the collision-path origin and
        command-lead boundary.  Those checks do not require replacing the local
        IK seed or recomputing its FK every frame.  A fresh measured TCP is
        requested only on a clutch edge, where it is needed for anchoring.
        """

        measured_model_q = self._pack_model(measured_hardware)
        self.measured_hardware = {
            arm: np.asarray(measured_hardware[arm], dtype=np.float64).copy()
            for arm in ARM_NAMES
        }
        if not compute_tcp:
            return None
        return self._kinematic_transforms(measured_model_q)

    def sync_command_reference(
        self,
        command_hardware: Mapping[str, Sequence[float]],
    ) -> None:
        """Move only the local IK reference, preserving physical feedback.

        Execute mode uses this after :meth:`sync` captured the current encoder
        state. The solver can then continue from its last accepted command while
        measured feedback remains available as an independent safety state.
        """

        if self.measured_hardware is None:
            raise IkSafetyError(
                "command reference cannot be set before physical synchronization"
            )
        model_q = self._pack_model(command_hardware)
        self.command_reference_hardware = {
            arm: np.asarray(command_hardware[arm], dtype=np.float64).copy()
            for arm in ARM_NAMES
        }
        if (
            self.model_q is not None
            and self.tcp_world
            and np.allclose(model_q, self.model_q, rtol=0.0, atol=1.0e-12)
        ):
            self.command_reference_fk_reuse_count = (
                getattr(self, "command_reference_fk_reuse_count", 0) + 1
            )
            return
        self.command_reference_fk_compute_count = (
            getattr(self, "command_reference_fk_compute_count", 0) + 1
        )
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
            arm: self._model_to_hardware(
                arm, bounded[self.arm_slices[arm]]
            )
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
            or recovery_escape_max_initial_overlap_m
            > _PARK_RECOVERY_MAX_INITIAL_OVERLAP_M
        ):
            raise ValueError(
                "park recovery escape maximum overlap must be between 0 and "
                f"{_PARK_RECOVERY_MAX_INITIAL_OVERLAP_M * 1000.0:.2f}mm"
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
                trajectory[:, first : first + 1, :],
                escape_max_initial_overlap_m=(
                    recovery_escape_max_initial_overlap_m
                ),
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
        *,
        synchronize_hardware: Mapping[str, Sequence[float]] | None = None,
    ) -> dict[str, tuple[float, float]]:
        # The vendor SDK publishes TCP FK in its raw hardware joint coordinate
        # convention. The physical hanging calibration is a separate mapping
        # used by the collision/control model
        # (model = offset + sign * hardware).
        # Compare like-for-like here, then restore the calibrated model below.
        # Runtime validation independently pins the accepted J2/J3 offsets, so
        # this raw SDK identity check cannot silently authorize another mapping.
        raw_q = []
        for arm in ARM_NAMES:
            values = np.asarray(measured_hardware[arm], dtype=np.float64)
            if values.shape != (7,) or not np.all(np.isfinite(values)):
                raise IkSafetyError(
                    f"{arm} joint feedback must contain seven finite values"
                )
            raw_q.append(values)
        synchronized = (
            measured_hardware
            if synchronize_hardware is None
            else synchronize_hardware
        )
        synchronized_model_q = self._pack_model(synchronized)
        # Check the vendor's raw-coordinate FK and compute the latest calibrated
        # control state in one two-row CUDA FK call.  Previously this method
        # restored one calibrated state and the ROS node immediately computed
        # it again for the latest feedback, yielding three FK launches/tick.
        raw_world, synchronized_world = self._kinematic_transforms_batch(
            np.stack((np.concatenate(raw_q), synchronized_model_q))
        )
        self.measured_hardware = {
            arm: np.asarray(synchronized[arm], dtype=np.float64).copy()
            for arm in ARM_NAMES
        }
        self.command_reference_hardware = {
            arm: values.copy() for arm, values in self.measured_hardware.items()
        }
        self.model_q = synchronized_model_q
        self.tcp_world = {
            arm: synchronized_world[arm].copy() for arm in ARM_NAMES
        }
        return {
            arm: self._errors(
                np.linalg.inv(self.base_world[arm]) @ raw_world[arm],
                np.asarray(driver_tcp_local[arm], dtype=np.float64),
            )
            for arm in driver_tcp_local
        }

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
        packed = self._tensor(
            np.concatenate(
                (transform[:3, 3].astype(np.float32), quaternion_wxyz)
            )
        ).view(1, 7)
        return self.Pose(position=packed[:, :3], quaternion=packed[:, 3:])

    def _validate_interpolated_step(
        self, current: np.ndarray, candidate: np.ndarray
    ) -> None:
        rejection = self._interpolated_candidate_rejections(
            current, np.asarray(candidate, dtype=np.float64)[None, :]
        )[0]
        if rejection is not None:
            raise IkSafetyError(rejection)

    def _interpolated_candidate_rejections(
        self,
        current: np.ndarray,
        candidates: np.ndarray,
    ) -> list[str | None]:
        """Batch-check candidate paths and explain only the rejected rows."""

        current_values = np.asarray(current, dtype=np.float64)
        candidate_values = np.asarray(candidates, dtype=np.float64)
        if current_values.shape != (14,) or not np.all(np.isfinite(current_values)):
            raise ValueError("current model joints must contain fourteen finite values")
        if (
            candidate_values.ndim != 2
            or candidate_values.shape[0] < 1
            or candidate_values.shape[1] != 14
            or not np.all(np.isfinite(candidate_values))
        ):
            raise ValueError("candidate model joints must be a finite Nx14 matrix")
        current_tensor = self._tensor(current_values)
        delta_tensor = self._tensor(candidate_values - current_values[None, :])
        trajectories = current_tensor.view(1, 1, -1) + (
            self._collision_interpolation_alphas.view(1, -1, 1)
            * delta_tensor.view(-1, 1, 14)
        )
        valid = self._configuration_valid(trajectories).detach().cpu().numpy()
        rejections: list[str | None] = [None] * candidate_values.shape[0]
        for candidate_index, samples_valid in enumerate(valid):
            if bool(np.all(samples_valid)):
                continue
            trajectory = trajectories[candidate_index : candidate_index + 1]
            if self._trajectory_escape_allowed(trajectory):
                continue
            first = int(np.flatnonzero(~samples_valid)[0])
            reason = self._invalid_configuration_reason(
                trajectory[:, first : first + 1, :]
            )
            rejections[candidate_index] = (
                f"cuRobo rejected interpolation sample {first + 1}/"
                f"{self.collision_interpolation_steps}: {reason}"
            )
        return rejections

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

    def _build_collision_pair_required_clearances(self):
        checker = self.collision_checker
        kinematics_config = checker.kinematics.config.kinematics_config
        collision_config = checker.kinematics.config.self_collision_config
        pairs = collision_config.collision_pairs.to(dtype=self.torch.long)
        sphere_to_link = kinematics_config.link_sphere_idx_map
        link_names = {
            value: key
            for key, value in kinematics_config.link_name_to_idx_map.items()
        }
        clearances = []
        for pair in pairs:
            first_link = link_names[int(sphere_to_link[int(pair[0].item())].item())]
            second_link = link_names[int(sphere_to_link[int(pair[1].item())].item())]
            clearances.append(
                cross_arm_pair_clearance_m(
                    first_link,
                    second_link,
                    self.cross_arm_safety_margin_m,
                )
            )
        return self.torch.as_tensor(
            clearances, dtype=self.torch.float32, device=self.device
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
        same-arm pairs, joint bounds, and any future world collision constraint
        retain cuRobo's strict zero-penetration rule. Different-arm pairs keep
        the configured positive surface clearance.
        """

        checker = self.collision_checker
        checker.setup_batch_tensors(q.shape[0], q.shape[1])
        state = checker.get_kinematics(q)
        valid = self.torch.all(checker.get_bound(q) <= 0.0, dim=-1)
        gaps = self._self_collision_gaps(state.robot_spheres)
        valid = valid & self.torch.all(
            gaps
            >= (
                self._collision_pair_required_clearances
                - self._collision_pair_tolerances
            ).view(1, 1, -1),
            dim=-1,
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
            - self._collision_pair_required_clearances.view(1, 1, -1)
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

    def _invalid_configuration_reason(
        self,
        q_sample,
        *,
        escape_max_initial_overlap_m: float | None = None,
    ) -> str:
        """Explain a cuRobo validation failure without weakening its checks."""
        checker = self.collision_checker
        checker.setup_batch_tensors(q_sample.shape[0], q_sample.shape[1])
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
        threshold_clearance = (
            gaps
            + self._collision_pair_tolerances
            - self._collision_pair_required_clearances
        )
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
            required_clearance_mm = (
                float(
                    self._collision_pair_required_clearances[pair_index].item()
                )
                * 1000.0
            )
            escape_suffix = ""
            if self._collision_pair_escape_mask[pair_index]:
                escape_allowance_m = (
                    self.collision_escape_max_initial_overlap_m
                    if escape_max_initial_overlap_m is None
                    else float(escape_max_initial_overlap_m)
                )
                escape_kind = (
                    "park recovery"
                    if escape_max_initial_overlap_m is not None
                    else "Cartesian"
                )
                escape_suffix = (
                    f", non-deepening {escape_kind} escape allowance "
                    f"{escape_allowance_m * 1000.0:.2f}mm"
                )
            return (
                f"self/cross-arm collision {first_link} <-> {second_link}, "
                f"sphere gap {gap_mm:.2f}mm "
                f"(required clearance {required_clearance_mm:.2f}mm, "
                f"mesh-fit tolerance {fit_tolerance_mm:.2f}mm"
                f"{escape_suffix})"
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
        *,
        collision_start_hardware: Mapping[str, Sequence[float]] | None = None,
        max_command_lead_rad: float | None = None,
    ) -> IkResult:
        """Try the warm one-seed graph, then fall back to all five seeds."""

        self.solve_attempt_sequence += 1
        fast_started = time.monotonic()
        fallback_reason: str | None = None
        try:
            result = self._solve_attempt(
                targets_world,
                active_arms,
                collision_start_hardware=collision_start_hardware,
                max_command_lead_rad=max_command_lead_rad,
                use_fast_path=True,
            )
        except (IkNoProgressError, IkCollisionBlockedError) as exc:
            fallback_reason = type(exc).__name__
        except IkSafetyError:
            if self.last_solve_outcome != "solver_error":
                raise
            fallback_reason = "fast_solver_error"
        else:
            # A finite, bounded and collision-checked candidate is useful even
            # when cuRobo's convergence flag is false.  In streaming teleop the
            # target intentionally moves every tick, so forcing a five-seed
            # retry on that flag adds a long tail and can switch IK branches.
            # _solve_attempt raises when no safe/progressing candidate exists;
            # only those hard failures should leave the one-seed fast path.
            self.last_solve_diagnostics.update(
                {
                    "fast_path_used": True,
                    "fast_path_fallback": False,
                    "fast_path_attempt_ms": round(
                        (time.monotonic() - fast_started) * 1000.0, 3
                    ),
                    "full_seed_count_available": self.num_seeds,
                }
            )
            return result

        fast_elapsed_ms = (time.monotonic() - fast_started) * 1000.0
        result = self._solve_attempt(
            targets_world,
            active_arms,
            collision_start_hardware=collision_start_hardware,
            max_command_lead_rad=max_command_lead_rad,
            use_fast_path=False,
        )
        total_elapsed_ms = (time.monotonic() - fast_started) * 1000.0
        full_path_elapsed_ms = max(0.0, total_elapsed_ms - fast_elapsed_ms)
        self.last_solve_diagnostics.update(
            {
                "fast_path_used": False,
                "fast_path_fallback": True,
                "fast_path_fallback_reason": fallback_reason,
                "fast_path_attempt_ms": round(fast_elapsed_ms, 3),
                "full_path_attempt_ms": round(full_path_elapsed_ms, 3),
                "solve_time_ms": round(total_elapsed_ms, 3),
                "full_seed_count_available": self.num_seeds,
            }
        )
        return result

    def _solve_attempt(
        self,
        targets_world: Mapping[str, np.ndarray],
        active_arms: set[str],
        *,
        collision_start_hardware: Mapping[str, Sequence[float]] | None = None,
        max_command_lead_rad: float | None = None,
        use_fast_path: bool,
    ) -> IkResult:
        started = time.monotonic()
        self.last_solve_outcome = "running"
        self.last_solve_result = None
        if (
            self.measured_hardware is None
            or self.command_reference_hardware is None
            or self.model_q is None
        ):
            self.last_solve_outcome = "invalid_state"
            raise IkSafetyError("IK cannot run before joint feedback is synchronized")
        if not active_arms or not active_arms.issubset(ARM_NAMES):
            self.last_solve_outcome = "invalid_request"
            raise ValueError("active_arms must be a non-empty subset of arm_a/arm_b")
        if max_command_lead_rad is not None and (
            not math.isfinite(max_command_lead_rad)
            or max_command_lead_rad <= 0.0
        ):
            self.last_solve_outcome = "invalid_request"
            raise ValueError("max_command_lead_rad must be positive and finite")
        if (collision_start_hardware is None) != (max_command_lead_rad is None):
            self.last_solve_outcome = "invalid_request"
            raise ValueError(
                "collision_start_hardware and max_command_lead_rad must be "
                "provided together"
            )

        # ``self.model_q`` is the continuous command-space IK reference.  The
        # optional collision start remains the latest physical encoder state.
        # Keeping these states separate prevents a slow inner position loop
        # from dragging the local solver backwards on every frame, while every
        # command that can reach hardware is still bounded and collision-
        # checked from the measured configuration below.
        if collision_start_hardware is None:
            collision_start_model_q = self.model_q
            collision_start_by_arm = {
                arm: values.copy()
                for arm, values in self.measured_hardware.items()
            }
        else:
            if set(collision_start_hardware) != set(ARM_NAMES):
                self.last_solve_outcome = "invalid_request"
                raise ValueError(
                    "collision_start_hardware must contain arm_a and arm_b"
                )
            collision_start_model_q = self._pack_model(collision_start_hardware)
            collision_start_by_arm = {
                arm: np.asarray(
                    collision_start_hardware[arm], dtype=np.float64
                ).copy()
                for arm in ARM_NAMES
            }

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
        active_indices = [
            index
            for arm in ARM_NAMES
            if arm in active_arms
            for index in range(
                self.arm_slices[arm].start, self.arm_slices[arm].stop
            )
        ]
        active_joint_groups = [
            tuple(range(self.arm_slices[arm].start, self.arm_slices[arm].stop))
            for arm in ARM_NAMES
            if arm in active_arms
        ]
        active_elbows = self._active_elbow_indices(active_arms)
        active_arm_key = tuple(arm for arm in ARM_NAMES if arm in active_arms)
        previous_selected_rank = self._last_selected_seed_rank.get(active_arm_key)
        previous_seed_directions = {
            arm: self._last_selected_seed_direction.get(arm)
            for arm in active_arm_key
        }
        attempt_seed_count = 1 if use_fast_path else self.num_seeds
        if use_fast_path:
            seed_patterns = (
                tuple(
                    0.0 if previous_seed_directions[arm] is None
                    else float(previous_seed_directions[arm])
                    for arm in active_arm_key
                ),
            )
            seed_configs = self.model_q[None, :]
            solver = self.fast_solver
        else:
            seed_patterns = balanced_elbow_seed_patterns(
                len(active_arm_key),
                attempt_seed_count,
            )
            seed_configs = self._seed_configs(self.model_q, active_arms)
            solver = self.solver
        try:
            result = solver.solve_single(
                goal_tool_poses=goal,
                current_state=self._joint_state(self.model_q),
                seed_config=self._tensor(seed_configs).view(
                    1, attempt_seed_count, -1
                ),
                return_seeds=attempt_seed_count,
            )
        except RuntimeError as exc:
            self.last_solve_outcome = "solver_error"
            raise IkSafetyError(f"cuRobo IK solver failed: {exc}") from exc

        candidate_tensor = result.js_solution.position[0]
        success_tensor = result.success[0].reshape(-1, 1).to(
            dtype=candidate_tensor.dtype
        )
        packed_solver_result = (
            self.torch.cat((candidate_tensor, success_tensor), dim=-1)
            .detach()
            .cpu()
            .numpy()
        )
        candidates = packed_solver_result[:, :14].astype(np.float64)
        successes = packed_solver_result[:, 14] > 0.5
        solver_finished = time.monotonic()
        if candidates.shape != (attempt_seed_count, 14):
            self.last_solve_outcome = "invalid_result"
            raise IkSafetyError(
                "cuRobo IK returned an unexpected multi-seed joint shape "
                f"{candidates.shape}"
            )

        feasible: list[
            tuple[
                float,
                int,
                bool,
                np.ndarray,
                dict[str, np.ndarray],
                dict[str, float],
                dict[str, float],
                dict[str, np.ndarray],
            ]
        ] = []
        collision_rejections: list[str] = []
        no_progress_rejections: list[str] = []
        finite_candidates = 0
        safe_candidates = 0
        progressing_candidates = 0
        collision_candidates_checked = 0
        posture_scale = math.radians(10.0)

        bounded_candidates: list[tuple[int, np.ndarray]] = []
        for rank, candidate in enumerate(candidates):
            if not np.all(np.isfinite(candidate)):
                continue
            finite_candidates += 1
            bounded, _ = bounded_joint_candidate_by_groups(
                self.model_q,
                candidate,
                active_joint_groups,
                self.max_joint_step_rad,
            )
            bounded = limit_elbow_step(
                self.model_q,
                bounded,
                active_elbows,
                self.max_elbow_step_rad,
            )
            if max_command_lead_rad is not None:
                # This second bound is relative to physical feedback, not the
                # command reference. It is the final target-lead envelope and
                # also restores inactive arms exactly to their measured state.
                bounded, _ = bounded_joint_candidate_by_groups(
                    collision_start_model_q,
                    bounded,
                    active_joint_groups,
                    max_command_lead_rad,
                )
            bounded_candidates.append((rank, bounded))

        candidate_tcp_world = (
            self._kinematic_transforms_batch(
                np.stack([bounded for _rank, bounded in bounded_candidates])
            )
            if bounded_candidates
            else []
        )
        candidate_fk_finished = time.monotonic()
        non_progress_bounded: list[tuple[int, np.ndarray]] = []

        for (rank, bounded), tcp_world in zip(
            bounded_candidates, candidate_tcp_world
        ):
            commands: dict[str, np.ndarray] = {}
            position_errors: dict[str, float] = {}
            orientation_errors: dict[str, float] = {}
            progressing = True
            progress_details = []
            for arm in ARM_NAMES:
                arm_slice = self.arm_slices[arm]
                commands[arm] = self._model_to_hardware(
                    arm, bounded[arm_slice]
                )
                target = (
                    np.asarray(targets_world[arm], dtype=np.float64)
                    if arm in active_arms
                    else tcp_world[arm]
                )
                position_errors[arm], orientation_errors[arm] = self._errors(
                    tcp_world[arm], target
                )
                if arm in active_arms and (
                    before_errors[arm][0] > 1e-5
                    or before_errors[arm][1] > 1e-4
                ) and not self._made_progress(
                    *before_errors[arm],
                    position_errors[arm],
                    orientation_errors[arm],
                ):
                    progressing = False
                    progress_details.append(
                        f"{arm} {before_errors[arm][0]:.6f}m -> "
                        f"{position_errors[arm]:.6f}m"
                    )
            if not progressing:
                no_progress_rejections.append(
                    f"seed {rank + 1}: " + ", ".join(progress_details)
                )
                non_progress_bounded.append((rank, bounded))
                if self.require_cartesian_progress:
                    continue
            else:
                progressing_candidates += 1

            pose_score = sum(
                position_errors[arm] / 0.01
                + orientation_errors[arm] / 0.10
                for arm in active_arms
            )
            neutral_posture = 0.0
            for arm in active_arms:
                elbow = self.arm_slices[arm].start + 1
                centered_j2 = bounded[elbow] - self.offsets[arm][1]
                neutral_posture += abs(centered_j2) / posture_scale
            joint_motion_rms = normalized_joint_motion_rms(
                self.model_q,
                bounded,
                active_indices,
                self.max_joint_step_rad,
            )
            # A failed convergence flag can still contain a useful local step.
            # Candidate motion is scored only after the pose/progress gates and
            # before collision validation: it chooses a less jerky safe branch
            # without delaying or filtering the newest Cartesian target.
            seed_pattern = seed_patterns[rank]
            seed_direction_switches = sum(
                previous_seed_directions[arm] is not None
                and direction != previous_seed_directions[arm]
                for arm, direction in zip(active_arm_key, seed_pattern)
            )
            score = candidate_ranking_score(
                pose_score,
                neutral_posture,
                joint_motion_rms,
                elbow_posture_weight=self.elbow_posture_weight,
                joint_motion_weight=self.joint_motion_weight,
                solver_success=bool(successes[rank]),
                seed_switch_penalty=(
                    self.seed_switch_penalty * seed_direction_switches
                ),
                switching_seed=seed_direction_switches > 0,
            )
            feasible.append(
                (
                    score,
                    rank,
                    bool(successes[rank]),
                    bounded,
                    tcp_world,
                    position_errors,
                    orientation_errors,
                    commands,
                )
            )

        scoring_finished = time.monotonic()

        def collision_safe(
            items: list[tuple[int, np.ndarray]],
        ) -> list[tuple[int, np.ndarray]]:
            nonlocal collision_candidates_checked, safe_candidates
            if not items:
                return []
            rejections = self._interpolated_candidate_rejections(
                collision_start_model_q,
                np.stack([bounded for _rank, bounded in items]),
            )
            collision_candidates_checked += len(items)
            safe_items = []
            for (rank, bounded), rejection in zip(items, rejections):
                if rejection is not None:
                    collision_rejections.append(
                        f"seed {rank + 1}: {rejection}"
                    )
                    continue
                safe_candidates += 1
                safe_items.append((rank, bounded))
            return safe_items

        # FK and deterministic score do not weaken safety, so rank candidates
        # before the expensive interpolated collision pass.  Validate the best
        # candidate first and stop when it is safe.  If it is blocked, validate
        # every remaining progressing candidate as one batch.  This selects the
        # exact same minimum-score safe result as validating all five up front,
        # while the common all-safe case checks only one complete path.
        ordered_feasible = sorted(feasible, key=lambda item: (item[0], item[1]))
        selected = None
        if ordered_feasible:
            best = ordered_feasible[0]
            if collision_safe([(best[1], best[3])]):
                selected = best
            else:
                remaining_safe_ranks = {
                    rank
                    for rank, _bounded in collision_safe(
                        [(item[1], item[3]) for item in ordered_feasible[1:]]
                    )
                }
                selected = next(
                    (
                        item
                        for item in ordered_feasible[1:]
                        if item[1] in remaining_safe_ranks
                    ),
                    None,
                )

        if selected is None:
            if not ordered_feasible:
                # Preserve the original failure classification: a safe but
                # non-progressing result is an IK retry, whereas all colliding
                # results are a collision block.
                collision_safe(bounded_candidates)
            elif non_progress_bounded:
                collision_safe(non_progress_bounded)

        collision_finished = time.monotonic()
        phase_diagnostics = {
            "solver_ms": round((solver_finished - started) * 1000.0, 3),
            "collision_validation_ms": round(
                (collision_finished - scoring_finished) * 1000.0,
                3,
            ),
            "candidate_fk_ms": round(
                (candidate_fk_finished - solver_finished) * 1000.0,
                3,
            ),
            "candidate_scoring_ms": round(
                (scoring_finished - candidate_fk_finished) * 1000.0,
                3,
            ),
        }

        if selected is None:
            elapsed_ms = (time.monotonic() - started) * 1000.0
            self.last_solve_diagnostics = {
                "solve_time_ms": round(elapsed_ms, 3),
                **phase_diagnostics,
                "seed_count": attempt_seed_count,
                "finite_candidates": finite_candidates,
                "safe_candidates": safe_candidates,
                "collision_candidates_checked": collision_candidates_checked,
                "collision_short_circuit": False,
                "progressing_candidates": progressing_candidates,
                "require_cartesian_progress": self.require_cartesian_progress,
                "selected_rank": None,
                "previous_selected_rank": (
                    None
                    if previous_selected_rank is None
                    else previous_selected_rank + 1
                ),
                "seed_rank_switched": False,
                "seed_switch_penalty": self.seed_switch_penalty,
                "seed_continuity_scope": "per_arm_direction",
                "previous_seed_directions": previous_seed_directions,
                "command_reference_active": (
                    collision_start_hardware is not None
                ),
                "max_command_lead_deg": (
                    None
                    if max_command_lead_rad is None
                    else round(math.degrees(max_command_lead_rad), 3)
                ),
            }
            if safe_candidates == 0 and collision_rejections:
                current_tensor = self._tensor(
                    collision_start_model_q
                ).view(1, 1, -1)
                current_valid = bool(
                    self._configuration_valid(current_tensor).item()
                )
                if not current_valid:
                    self.last_solve_outcome = "safety_rejected"
                    raise IkSafetyError(
                        "current measured/simulated configuration is unsafe: "
                        + self._invalid_configuration_reason(current_tensor)
                    )
                self.last_solve_outcome = "collision_blocked"
                raise IkCollisionBlockedError(
                    f"cuRobo rejected all {finite_candidates} finite IK "
                    f"candidates; {collision_rejections[0]}"
                )
            detail = (
                no_progress_rejections[0]
                if no_progress_rejections
                else "all candidates were non-finite"
            )
            self.last_solve_outcome = "no_progress"
            raise IkNoProgressError(
                f"cuRobo multi-seed step made no Cartesian progress; {detail}"
            )

        (
            _score,
            selected_rank,
            selected_success,
            bounded,
            tcp_world,
            position_errors,
            orientation_errors,
            commands,
        ) = selected
        seed_rank_switched = (
            previous_selected_rank is not None
            and selected_rank != previous_selected_rank
        )
        self._last_selected_seed_rank[active_arm_key] = selected_rank
        selected_seed_pattern = seed_patterns[selected_rank]
        seed_direction_switches = sum(
            previous_seed_directions[arm] is not None
            and direction != previous_seed_directions[arm]
            for arm, direction in zip(active_arm_key, selected_seed_pattern)
        )
        for arm, direction in zip(active_arm_key, selected_seed_pattern):
            self._last_selected_seed_direction[arm] = direction
        selected_active = np.asarray(tuple(active_indices), dtype=int)
        selected_joint_motion_rms = normalized_joint_motion_rms(
            self.model_q,
            bounded,
            active_indices,
            self.max_joint_step_rad,
        )
        selected_joint_step_max = float(
            np.max(np.abs(bounded[selected_active] - self.model_q[selected_active]))
        )
        selected_joint_step_max_by_arm_deg = self._joint_step_max_by_arm_deg(
            self.model_q,
            bounded,
            active_arm_key,
        )
        elapsed_ms = (time.monotonic() - started) * 1000.0
        self.last_solve_diagnostics = {
            "solve_time_ms": round(elapsed_ms, 3),
            **phase_diagnostics,
            "seed_count": attempt_seed_count,
            "finite_candidates": finite_candidates,
            "safe_candidates": safe_candidates,
            "collision_candidates_checked": collision_candidates_checked,
            "collision_short_circuit": (
                collision_candidates_checked < finite_candidates
            ),
            "progressing_candidates": progressing_candidates,
            "require_cartesian_progress": self.require_cartesian_progress,
            "selected_rank": selected_rank + 1,
            "previous_selected_rank": (
                None
                if previous_selected_rank is None
                else previous_selected_rank + 1
            ),
            "seed_rank_switched": seed_rank_switched,
            "seed_switch_penalty": self.seed_switch_penalty,
            "seed_continuity_scope": "per_arm_direction",
            "seed_direction_switches": seed_direction_switches,
            "selected_seed_directions": {
                arm: direction
                for arm, direction in zip(active_arm_key, selected_seed_pattern)
            },
            "previous_seed_directions": previous_seed_directions,
            "selected_solver_success": selected_success,
            "joint_motion_weight": self.joint_motion_weight,
            "selected_joint_motion_rms_fraction": round(
                selected_joint_motion_rms,
                6,
            ),
            "selected_joint_step_max_deg": round(
                math.degrees(selected_joint_step_max),
                3,
            ),
            "selected_joint_step_max_by_arm_deg": (
                selected_joint_step_max_by_arm_deg
            ),
            "selected_j2_command_deg": {
                arm: round(math.degrees(float(commands[arm][1])), 3)
                for arm in ARM_NAMES
            },
            "selected_j2_delta_deg": {
                arm: round(
                    math.degrees(
                        float(
                            commands[arm][1]
                            - self.command_reference_hardware[arm][1]
                        )
                    ),
                    3,
                )
                for arm in ARM_NAMES
            },
            "selected_j2_feedback_delta_deg": {
                arm: round(
                    math.degrees(
                        float(
                            commands[arm][1]
                            - collision_start_by_arm[arm][1]
                        )
                    ),
                    3,
                )
                for arm in ARM_NAMES
            },
            "command_reference_active": collision_start_hardware is not None,
            "max_command_lead_deg": (
                None
                if max_command_lead_rad is None
                else round(math.degrees(max_command_lead_rad), 3)
            ),
            "command_reference_fk_reused_total": (
                self.command_reference_fk_reuse_count
            ),
            "command_reference_fk_computed_total": (
                self.command_reference_fk_compute_count
            ),
        }
        # Preserve the already-computed selected FK as next frame's local IK
        # seed.  Execute updates physical feedback separately, so the common
        # path no longer recomputes this exact FK before every solve.
        self.model_q = bounded.copy()
        self.command_reference_hardware = {
            arm: commands[arm].copy() for arm in ARM_NAMES
        }
        self.tcp_world = {arm: tcp_world[arm].copy() for arm in ARM_NAMES}
        solve_result = IkResult(
            joint_commands=commands,
            tcp_world=tcp_world,
            position_errors_m=position_errors,
            orientation_errors_rad=orientation_errors,
        )
        self.last_solve_result = solve_result
        self.last_solve_outcome = "success"
        return solve_result
