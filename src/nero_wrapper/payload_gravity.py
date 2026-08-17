"""Payload-only gravity feed-forward with optional Pinocchio backend."""

from __future__ import annotations

import copy
import math
from collections.abc import Mapping, Sequence
from typing import Any

from .dual_model import ARM_NAMES, HARDWARE_TO_MODEL_JOINT_SIGNS


class PayloadGravityCompensator:
    """Subtract bare-arm gravity from the same model with a point payload.

    Pinocchio and NumPy are imported only when this class is constructed. The
    default wrapper remains dependency-free and read-only.
    """

    def __init__(
        self,
        urdf_path: str,
        *,
        mass_kg: float,
        com_xyz_m: Sequence[float],
        world_from_base_rotations: Mapping[str, Any],
        joint_offsets: Mapping[str, Sequence[float]],
        joint_signs: Mapping[str, Sequence[float]] = HARDWARE_TO_MODEL_JOINT_SIGNS,
        torque_scale: float = 1.0,
        max_abs_torque_nm: float = 6.0,
        max_torque_step_nm: float = 0.25,
        gravity_m_s2: float = 9.80665,
        pin_backend: Any | None = None,
    ) -> None:
        try:
            import numpy as np
        except ImportError as exc:
            raise RuntimeError("NumPy is required for payload gravity compensation") from exc
        if pin_backend is None:
            try:
                import pinocchio as pin
            except ImportError as exc:
                raise RuntimeError(
                    "Pinocchio is required for payload gravity compensation; "
                    "install nero_wrapper[payload-gravity]"
                ) from exc
        else:
            pin = pin_backend
        if set(world_from_base_rotations) != set(ARM_NAMES):
            raise ValueError("world_from_base_rotations must contain arm_a and arm_b")
        if set(joint_offsets) != set(ARM_NAMES):
            raise ValueError("joint_offsets must contain arm_a and arm_b")
        if set(joint_signs) != set(ARM_NAMES):
            raise ValueError("joint_signs must contain arm_a and arm_b")
        if not math.isfinite(mass_kg) or mass_kg <= 0.0:
            raise ValueError("payload mass_kg must be positive and finite")
        com = np.asarray(com_xyz_m, dtype=np.float64)
        if com.shape != (3,) or not np.all(np.isfinite(com)):
            raise ValueError("payload com_xyz_m must contain three finite values")
        for name, value in (
            ("torque_scale", torque_scale),
            ("max_abs_torque_nm", max_abs_torque_nm),
            ("max_torque_step_nm", max_torque_step_nm),
            ("gravity_m_s2", gravity_m_s2),
        ):
            if not math.isfinite(value) or value <= 0.0:
                raise ValueError(f"{name} must be positive and finite")

        self._np = np
        self._pin = pin
        self.mass_kg = float(mass_kg)
        self.com_xyz_m = com
        self.torque_scale = float(torque_scale)
        self.max_abs_torque_nm = float(max_abs_torque_nm)
        self.max_torque_step_nm = float(max_torque_step_nm)
        self.offsets: dict[str, Any] = {}
        self.signs: dict[str, Any] = {}
        self.models: dict[str, Any] = {}
        self.payload_models: dict[str, Any] = {}
        self.data: dict[str, Any] = {}
        self.payload_data: dict[str, Any] = {}
        self.last_torque = {
            arm: np.zeros(7, dtype=np.float64) for arm in ARM_NAMES
        }

        gravity_world = np.asarray([0.0, 0.0, -gravity_m_s2], dtype=np.float64)
        for arm in ARM_NAMES:
            rotation = np.asarray(world_from_base_rotations[arm], dtype=np.float64)
            if (
                rotation.shape != (3, 3)
                or not np.all(np.isfinite(rotation))
                or not np.allclose(rotation.T @ rotation, np.eye(3), atol=1e-6)
                or not math.isclose(float(np.linalg.det(rotation)), 1.0, abs_tol=1e-6)
            ):
                raise ValueError(f"{arm} world_from_base rotation must be rigid 3x3")
            offsets = np.asarray(joint_offsets[arm], dtype=np.float64)
            if offsets.shape != (7,) or not np.all(np.isfinite(offsets)):
                raise ValueError(f"{arm} joint offsets must contain seven finite values")
            signs = np.asarray(joint_signs[arm], dtype=np.float64)
            if signs.shape != (7,) or not np.all(np.isin(signs, (-1.0, 1.0))):
                raise ValueError(
                    f"{arm} joint signs must contain seven +1/-1 values"
                )
            self.offsets[arm] = offsets
            self.signs[arm] = signs

            bare_model = pin.buildModelFromUrdf(urdf_path)
            if bare_model.nq != 7 or bare_model.nv != 7:
                raise ValueError("payload gravity model requires a fixed-base 7-DOF URDF")
            payload_model = copy.deepcopy(bare_model)
            joint_id = payload_model.getJointId("joint7")
            if joint_id == 0:
                raise ValueError("payload gravity model could not find joint7")
            point_mass = pin.Inertia(
                self.mass_kg,
                np.zeros(3, dtype=np.float64),
                np.eye(3, dtype=np.float64) * 1e-8,
            )
            payload_model.appendBodyToJoint(
                joint_id,
                point_mass,
                pin.SE3(np.eye(3, dtype=np.float64), self.com_xyz_m),
            )
            gravity_base = rotation.T @ gravity_world
            bare_model.gravity.linear = gravity_base
            payload_model.gravity.linear = gravity_base
            self.models[arm] = bare_model
            self.payload_models[arm] = payload_model
            self.data[arm] = bare_model.createData()
            self.payload_data[arm] = payload_model.createData()

    def raw_torque(
        self,
        arm: str,
        measured_hardware_joints: Sequence[float],
    ) -> Any:
        if arm not in ARM_NAMES:
            raise ValueError(f"unknown arm {arm!r}")
        np = self._np
        hardware = np.asarray(measured_hardware_joints, dtype=np.float64)
        if hardware.shape != (7,) or not np.all(np.isfinite(hardware)):
            raise ValueError(f"{arm} joints must contain seven finite values")
        q_model = self.offsets[arm] + self.signs[arm] * hardware
        with_payload = self._pin.computeGeneralizedGravity(
            self.payload_models[arm], self.payload_data[arm], q_model
        )
        bare = self._pin.computeGeneralizedGravity(
            self.models[arm], self.data[arm], q_model
        )
        torque = np.asarray(with_payload - bare, dtype=np.float64)
        torque *= self.torque_scale
        # Virtual work gives tau_hardware = sign * tau_model for the reflected
        # J2 coordinate used by the installed hanging assembly.
        torque *= self.signs[arm]
        return np.clip(torque, -self.max_abs_torque_nm, self.max_abs_torque_nm)

    def torque(
        self,
        arm: str,
        measured_hardware_joints: Sequence[float],
    ) -> Any:
        requested = self.raw_torque(arm, measured_hardware_joints)
        previous = self.last_torque[arm]
        command = previous + self._np.clip(
            requested - previous,
            -self.max_torque_step_nm,
            self.max_torque_step_nm,
        )
        self.last_torque[arm] = command
        return command.copy()

    def reset(self, arm: str | None = None) -> None:
        arms = ARM_NAMES if arm is None else (arm,)
        for name in arms:
            if name not in ARM_NAMES:
                raise ValueError(f"unknown arm {name!r}")
            self.last_torque[name].fill(0.0)
