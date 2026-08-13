import numpy as np
import pytest
from scipy.spatial.transform import Rotation

from nero_wrapper.placo_ik import IkSafetyError, PlacoDualNeroIk


def test_placo_backend_import_does_not_construct_solver() -> None:
    assert issubclass(IkSafetyError, RuntimeError)
    assert PlacoDualNeroIk.__name__ == "PlacoDualNeroIk"


def test_error_metric_uses_translation_and_shortest_rotation() -> None:
    actual = np.eye(4)
    target = np.eye(4)
    target[:3, 3] = [0.01, -0.02, 0.03]
    target[:3, :3] = Rotation.from_euler("z", 10, degrees=True).as_matrix()
    position, orientation = PlacoDualNeroIk._errors(actual, target)
    assert position == pytest.approx(np.linalg.norm([0.01, -0.02, 0.03]))
    assert orientation == pytest.approx(np.deg2rad(10.0))
