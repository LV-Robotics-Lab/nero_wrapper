from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy.spatial.transform import Rotation

from .dual_model import (
    ARM_NAMES,
    HARDWARE_TO_MODEL_JOINT_OFFSETS,
    HARDWARE_TO_MODEL_JOINT_SIGNS,
    LAB_DUAL_BENCH_BASE_TRANSFORMS,
    BaseTransform,
    load_dual_nero_model,
)


class IkSafetyError(RuntimeError):
    pass


@dataclass(frozen=True)
class IkResult:
    joint_commands: dict[str, np.ndarray]
    tcp_world: dict[str, np.ndarray]
    position_errors_m: dict[str, float]
    orientation_errors_rad: dict[str, float]


class PlacoDualNeroIk:
    """One bounded, collision-checked dual-NERO IK step."""

    def __init__(
        self,
        urdf_path: str | Path,
        *,
        base_transforms: Mapping[str, BaseTransform] = LAB_DUAL_BENCH_BASE_TRANSFORMS,
        joint_offsets: Mapping[str, Sequence[float]] = HARDWARE_TO_MODEL_JOINT_OFFSETS,
        joint_signs: Mapping[str, Sequence[float]] = HARDWARE_TO_MODEL_JOINT_SIGNS,
        tcp_offsets: Mapping[str, BaseTransform] | None = None,
        control_rate_hz: float = 20.0,
        max_joint_step_rad: float = math.radians(0.5),
    ) -> None:
        import placo

        if control_rate_hz <= 0.0 or max_joint_step_rad <= 0.0:
            raise ValueError("IK rate and maximum joint step must be positive")
        self.model = load_dual_nero_model(
            urdf_path,
            base_transforms=base_transforms,
            joint_offsets=joint_offsets,
            joint_signs=joint_signs,
            tcp_offsets=tcp_offsets,
        )
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
        self.max_joint_step_rad = float(max_joint_step_rad)
        self.solver = placo.KinematicsSolver(self.model)
        self.solver.dt = 1.0 / float(control_rate_hz)
        self.solver.mask_fbase(True)
        self.solver.enable_joint_limits(True)
        self.solver.enable_velocity_limits(True)
        self.solver.add_regularization_task(1e-5)
        self.model.set_velocity_limits(
            0.8 * self.max_joint_step_rad * float(control_rate_hz)
        )

        self.q_indices = {
            arm: np.asarray(
                [
                    self.model.get_joint_offset(f"{arm}_joint{index}")
                    for index in range(1, 8)
                ],
                dtype=int,
            )
            for arm in ARM_NAMES
        }
        self.position_tasks = {}
        self.orientation_tasks = {}
        for arm in ARM_NAMES:
            link = f"{arm}_tcp_link"
            transform = np.asarray(self.model.get_T_world_frame(link))
            position_task = self.solver.add_position_task(
                link, transform[:3, 3].copy()
            )
            position_task.configure(f"{arm}_position", "soft", 1.0)
            orientation_task = self.solver.add_orientation_task(
                link, transform[:3, :3].copy()
            )
            orientation_task.configure(f"{arm}_orientation", "soft", 0.08)
            self.position_tasks[arm] = position_task
            self.orientation_tasks[arm] = orientation_task

        self.posture_task = self.solver.add_joints_task()
        self.posture_task.configure("measured_posture", "soft", 1e-3)
        self.measured_hardware: dict[str, np.ndarray] | None = None

    def _collisions(self) -> list[tuple[str, str]]:
        return [
            (collision.bodyA, collision.bodyB)
            for collision in self.model.self_collisions(False)
        ]

    def sync(self, measured_hardware: Mapping[str, Sequence[float]]) -> None:
        measured = {}
        for arm in ARM_NAMES:
            values = np.asarray(measured_hardware[arm], dtype=np.float64)
            if values.shape != (7,) or not np.all(np.isfinite(values)):
                raise IkSafetyError(f"{arm} joint feedback must contain seven finite values")
            measured[arm] = values.copy()
            model_values = self.offsets[arm] + self.signs[arm] * values
            self.model.state.q[self.q_indices[arm]] = model_values
            for index, value in enumerate(model_values, 1):
                self.posture_task.set_joint(f"{arm}_joint{index}", float(value))
        self.model.update_kinematics()
        self.measured_hardware = measured

    def current_tcp_world(self, arm: str) -> np.ndarray:
        return np.asarray(
            self.model.get_T_world_frame(f"{arm}_tcp_link"),
            dtype=np.float64,
        ).copy()

    def validate_driver_fk(
        self,
        measured_hardware: Mapping[str, Sequence[float]],
        driver_tcp_local: Mapping[str, np.ndarray],
    ) -> dict[str, tuple[float, float]]:
        """Cross-check the same converted model state used by IK against the driver."""
        measured = {
            arm: np.asarray(measured_hardware[arm], dtype=np.float64)
            for arm in ARM_NAMES
        }
        try:
            for arm in ARM_NAMES:
                if measured[arm].shape != (7,) or not np.all(np.isfinite(measured[arm])):
                    raise IkSafetyError(f"{arm} FK needs seven finite joints")
            self.sync(measured)
            errors = {}
            for arm in ARM_NAMES:
                model_local = np.asarray(
                    self.model.get_T_a_b(
                        f"{arm}_base_link", f"{arm}_tcp_link"
                    ),
                    dtype=np.float64,
                )
                errors[arm] = self._errors(
                    model_local, np.asarray(driver_tcp_local[arm], dtype=np.float64)
                )
            return errors
        finally:
            self.sync(measured)

    @staticmethod
    def _errors(actual: np.ndarray, target: np.ndarray) -> tuple[float, float]:
        position = float(np.linalg.norm(actual[:3, 3] - target[:3, 3]))
        orientation = float(
            Rotation.from_matrix(
                target[:3, :3] @ actual[:3, :3].T
            ).magnitude()
        )
        return position, orientation

    def solve(
        self,
        targets_world: Mapping[str, np.ndarray],
        active_arms: set[str],
    ) -> IkResult:
        if self.measured_hardware is None:
            raise IkSafetyError("IK cannot run before joint feedback is synchronized")
        if not active_arms or not active_arms.issubset(ARM_NAMES):
            raise ValueError("active_arms must be a non-empty subset of arm_a/arm_b")

        before_errors = {}
        for arm in ARM_NAMES:
            current = self.current_tcp_world(arm)
            target = (
                np.asarray(targets_world[arm], dtype=np.float64)
                if arm in active_arms
                else current
            )
            if target.shape != (4, 4) or not np.all(np.isfinite(target)):
                raise IkSafetyError(f"{arm} target must be a finite 4x4 transform")
            self.position_tasks[arm].target_world = target[:3, 3].copy()
            self.orientation_tasks[arm].R_world_frame = target[:3, :3].copy()
            before_errors[arm] = self._errors(current, target)

        try:
            self.solver.solve(True)
        except RuntimeError as exc:
            raise IkSafetyError(f"IK solver failed: {exc}") from exc
        self.model.update_kinematics()

        collisions = self._collisions()
        if collisions:
            raise IkSafetyError(f"IK candidate collision: {collisions}")

        commands = {}
        tcp_world = {}
        position_errors = {}
        orientation_errors = {}
        for arm in ARM_NAMES:
            model_candidate = self.model.state.q[self.q_indices[arm]].copy()
            hardware_candidate = self.signs[arm] * (
                model_candidate - self.offsets[arm]
            )
            if not np.all(np.isfinite(hardware_candidate)):
                raise IkSafetyError(f"{arm} IK produced non-finite joints")
            step = float(
                np.max(
                    np.abs(hardware_candidate - self.measured_hardware[arm])
                )
            )
            if step > self.max_joint_step_rad + 1e-6:
                raise IkSafetyError(
                    f"{arm} IK step {math.degrees(step):.3f}deg exceeds "
                    f"{math.degrees(self.max_joint_step_rad):.3f}deg"
                )
            commands[arm] = hardware_candidate
            tcp_world[arm] = self.current_tcp_world(arm)
            target = (
                np.asarray(targets_world[arm])
                if arm in active_arms
                else tcp_world[arm]
            )
            position_errors[arm], orientation_errors[arm] = self._errors(
                tcp_world[arm], target
            )
            if arm in active_arms:
                before_position, before_orientation = before_errors[arm]
                if (
                    before_position > 1e-4
                    and position_errors[arm] >= before_position - 1e-8
                    and before_orientation < math.radians(1.0)
                ):
                    raise IkSafetyError(
                        f"{arm} IK did not reduce position residual "
                        f"({before_position:.6f}m -> {position_errors[arm]:.6f}m)"
                    )

        return IkResult(
            joint_commands=commands,
            tcp_world=tcp_world,
            position_errors_m=position_errors,
            orientation_errors_rad=orientation_errors,
        )
