import math

import numpy as np
import pytest
from scipy.spatial.transform import Rotation

from nero_wrapper.ik_geometry import step_towards


def test_step_towards_limits_translation_and_rotation() -> None:
    current = np.eye(4)
    target = np.eye(4)
    target[:3, 3] = [0.1, 0.0, 0.0]
    target[:3, :3] = Rotation.from_euler("z", 90, degrees=True).as_matrix()
    result = step_towards(current, target, 0.002, math.radians(1.0))
    assert np.linalg.norm(result[:3, 3]) == pytest.approx(0.002)
    assert Rotation.from_matrix(result[:3, :3]).magnitude() == pytest.approx(
        math.radians(1.0)
    )


def test_step_towards_rejects_nonfinite_limits_and_transforms() -> None:
    with pytest.raises(ValueError, match="finite and positive"):
        step_towards(np.eye(4), np.eye(4), math.nan, 1.0)
    invalid = np.eye(3)
    with pytest.raises(ValueError, match="4x4"):
        step_towards(invalid, np.eye(4), 1.0, 1.0)
