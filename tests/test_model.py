import math

import pytest

from nero_wrapper.model import (
    NERO_JOINT_LIMITS_RAD,
    NERO_JOINT_NAMES,
    validate_joint_positions,
)


def test_joint_metadata_has_seven_ordered_intervals() -> None:
    assert NERO_JOINT_NAMES == tuple(f"joint{index}" for index in range(1, 8))
    assert len(NERO_JOINT_LIMITS_RAD) == 7
    assert all(lower < upper for lower, upper in NERO_JOINT_LIMITS_RAD)


def test_joint_validation_accepts_zero_and_preserves_tuple() -> None:
    assert validate_joint_positions([0.0] * 7) == (0.0,) * 7


@pytest.mark.parametrize("values", [[0.0] * 6, [0.0] * 8, [0.0] * 6 + [math.nan]])
def test_joint_validation_rejects_malformed_vectors(values) -> None:
    with pytest.raises(ValueError):
        validate_joint_positions(values)


def test_joint_validation_applies_only_inward_margin() -> None:
    lower = NERO_JOINT_LIMITS_RAD[0][0]
    with pytest.raises(ValueError, match="joint1"):
        validate_joint_positions([lower] + [0.0] * 6, margin_rad=0.01)
    with pytest.raises(ValueError, match="non-negative"):
        validate_joint_positions([0.0] * 7, margin_rad=-0.01)
