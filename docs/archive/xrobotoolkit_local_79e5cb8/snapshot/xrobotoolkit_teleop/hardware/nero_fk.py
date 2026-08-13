"""Forward kinematics helpers for the NERO arms.

Two independent FK paths exist for this arm and both are useful:

* the official URDF loaded through placo (what IK, collision checks and the
  MuJoCo view all use), and
* the modified-DH table shipped inside pyAgxArm, which is also what the
  controller itself uses to produce the 0x2A2-0x2A4 flange-pose CAN feedback.

They agree to numerical zero in the arm's own ``base_link`` frame, so any
disagreement at runtime means the joint feedback, the calibration offsets or
the model file is wrong -- which is exactly the check
``NeroDualArmTeleopController.connect_and_validate`` gates live output on.

All joint values here are RAW HARDWARE radians (what CAN reports and what the
SDK expects), not the calibrated model coordinates.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Sequence

import numpy as np
from scipy.spatial.transform import Rotation

from xrobotoolkit_teleop.hardware.nero_model import (
    DEFAULT_NERO_URDF_PATH,
    BaseTransform,
    load_dual_nero_placo_model,
)

ARM_NAMES = ("arm_a", "arm_b")

# FK is compared per arm in that arm's own base frame, so the mounting
# transforms are irrelevant here. Keep both bases at identity (separated only
# so the two arms do not overlap in the shared model) and apply no joint zero
# offsets: this is the coordinate system the SDK reports in.
IDENTITY_BASE_TRANSFORMS: Dict[str, BaseTransform] = {
    "arm_a": BaseTransform((0.0, 0.0, 0.0), (0.0, 0.0, 0.0)),
    "arm_b": BaseTransform((1.0, 0.0, 0.0), (0.0, 0.0, 0.0)),
}


@dataclass(frozen=True)
class FkComparison:
    position_error_m: float
    rotation_error_rad: float

    def describe(self) -> str:
        return (
            f"position error {self.position_error_m * 1000.0:.3f} mm, "
            f"rotation error {math.degrees(self.rotation_error_rad):.3f} deg"
        )


def pose6_to_matrix(pose: Sequence[float]) -> np.ndarray:
    """Convert an ``[x, y, z, rx, ry, rz]`` pose (m, rad, xyz-euler) to 4x4."""
    values = np.asarray(pose, dtype=np.float64)
    if values.shape != (6,) or not np.all(np.isfinite(values)):
        raise ValueError("Flange pose must contain six finite values")
    result = np.eye(4)
    result[:3, :3] = Rotation.from_euler("xyz", values[3:]).as_matrix()
    result[:3, 3] = values[:3]
    return result


def matrix_to_pose6(matrix: np.ndarray) -> np.ndarray:
    """Inverse of :func:`pose6_to_matrix`."""
    transform = np.asarray(matrix, dtype=np.float64)
    if transform.shape != (4, 4):
        raise ValueError("Expected a 4x4 homogeneous transform")
    return np.concatenate(
        (transform[:3, 3], Rotation.from_matrix(transform[:3, :3]).as_euler("xyz"))
    )


def sdk_flange_pose(joints: Sequence[float], robot_model: str = "nero") -> np.ndarray:
    """FK from the SDK's modified-DH table, without touching the CAN bus.

    Useful offline: it needs pyAgxArm importable but no arm connected.
    """
    from pyAgxArm.utiles.mdh_kinematics import fk_from_mdh, get_mdh

    values = np.asarray(joints, dtype=np.float64)
    if values.shape != (7,) or not np.all(np.isfinite(values)):
        raise ValueError("NERO FK needs seven finite joint values")
    return np.asarray(fk_from_mdh(get_mdh(robot_model), values.tolist()), dtype=np.float64)


class NeroForwardKinematics:
    """URDF/placo FK for one or both arms, in raw hardware joint coordinates."""

    def __init__(
        self,
        urdf_path: str | Path = DEFAULT_NERO_URDF_PATH,
        base_transforms: Dict[str, BaseTransform] = IDENTITY_BASE_TRANSFORMS,
        joint_zero_offsets: Dict[str, Sequence[float]] | None = None,
    ) -> None:
        self.model = load_dual_nero_placo_model(
            urdf_path,
            base_transforms,
            joint_zero_offsets=(
                {arm: tuple(float(v) for v in values) for arm, values in joint_zero_offsets.items()}
                if joint_zero_offsets
                else None
            ),
        )

    def _apply(self, arm_name: str, joints: Sequence[float]) -> None:
        if arm_name not in ARM_NAMES:
            raise ValueError(f"Unknown arm {arm_name!r}")
        values = np.asarray(joints, dtype=np.float64)
        if values.shape != (7,) or not np.all(np.isfinite(values)):
            raise ValueError(f"{arm_name} FK needs seven finite joint values")
        for index, value in enumerate(values, 1):
            self.model.set_joint(f"{arm_name}_joint{index}", float(value))
        self.model.update_kinematics()

    def flange_matrix(self, arm_name: str, joints: Sequence[float]) -> np.ndarray:
        """4x4 pose of ``link7`` in that arm's ``base_link`` frame."""
        self._apply(arm_name, joints)
        return np.asarray(self.model.get_T_a_b(f"{arm_name}_base_link", f"{arm_name}_link7"))

    def flange_pose(self, arm_name: str, joints: Sequence[float]) -> np.ndarray:
        """``[x, y, z, rx, ry, rz]`` flange pose, matching the CAN feedback."""
        return matrix_to_pose6(self.flange_matrix(arm_name, joints))

    def link_matrix(self, arm_name: str, link: str, joints: Sequence[float]) -> np.ndarray:
        """4x4 pose of any prefixed link, e.g. ``link4``, in ``base_link``."""
        self._apply(arm_name, joints)
        return np.asarray(self.model.get_T_a_b(f"{arm_name}_base_link", f"{arm_name}_{link}"))

    def compare_to_pose(
        self, arm_name: str, joints: Sequence[float], reference_pose: Sequence[float]
    ) -> FkComparison:
        """Compare model FK against an SDK or CAN-reported flange pose."""
        model_flange = self.flange_matrix(arm_name, joints)
        reference = pose6_to_matrix(reference_pose)
        position_error = float(np.linalg.norm(model_flange[:3, 3] - reference[:3, 3]))
        rotation_error = float(
            Rotation.from_matrix(reference[:3, :3].T @ model_flange[:3, :3]).magnitude()
        )
        return FkComparison(position_error, rotation_error)

    def compare_to_sdk(self, arm_name: str, joints: Sequence[float]) -> FkComparison:
        """Offline URDF-vs-MDH identity check for a joint vector."""
        return self.compare_to_pose(arm_name, joints, sdk_flange_pose(joints))
