from __future__ import annotations

import math

import numpy as np
from scipy.spatial.transform import Rotation


def _transform(value: np.ndarray, name: str) -> np.ndarray:
    matrix = np.asarray(value, dtype=np.float64)
    if matrix.shape != (4, 4) or not np.all(np.isfinite(matrix)):
        raise ValueError(f"{name} must be a finite 4x4 transform")
    if not np.allclose(matrix[3], [0.0, 0.0, 0.0, 1.0], atol=1e-9):
        raise ValueError(f"{name} must be homogeneous")
    return matrix


def step_towards(
    current: np.ndarray,
    target: np.ndarray,
    max_translation_step_m: float,
    max_rotation_step_rad: float,
) -> np.ndarray:
    """Bound a robot-backend Cartesian increment in translation and SO(3)."""

    if (
        not math.isfinite(max_translation_step_m)
        or not math.isfinite(max_rotation_step_rad)
        or max_translation_step_m <= 0.0
        or max_rotation_step_rad <= 0.0
    ):
        raise ValueError("Cartesian step limits must be finite and positive")
    current_matrix = _transform(current, "current")
    target_matrix = _transform(target, "target")
    result = current_matrix.copy()

    delta = target_matrix[:3, 3] - current_matrix[:3, 3]
    distance = float(np.linalg.norm(delta))
    if distance > max_translation_step_m:
        delta *= max_translation_step_m / distance
    result[:3, 3] = current_matrix[:3, 3] + delta

    rotation_delta = Rotation.from_matrix(
        target_matrix[:3, :3] @ current_matrix[:3, :3].T
    )
    rotvec = rotation_delta.as_rotvec()
    angle = float(np.linalg.norm(rotvec))
    if angle > max_rotation_step_rad:
        rotvec *= max_rotation_step_rad / angle
    result[:3, :3] = (
        Rotation.from_rotvec(rotvec).as_matrix() @ current_matrix[:3, :3]
    )
    return result
