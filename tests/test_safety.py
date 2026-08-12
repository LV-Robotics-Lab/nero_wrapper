from __future__ import annotations

import pytest

from nero_wrapper import MotionGate, SafetyGateError, validate_joint_delta


def test_motion_gate_requires_explicit_execute() -> None:
    with pytest.raises(SafetyGateError, match="dry-run"):
        MotionGate().require_motion()


def test_motion_gate_reports_every_missing_confirmation() -> None:
    with pytest.raises(SafetyGateError) as error:
        MotionGate(execute=True).require_motion()

    message = str(error.value)
    assert "workspace clearance" in message
    assert "emergency-stop readiness" in message
    assert "exclusive control source" in message
    assert "RViz/feedback visibility" in message


def test_complete_motion_gate_passes() -> None:
    MotionGate(
        execute=True,
        clearance_confirmed=True,
        estop_ready=True,
        control_source_exclusive=True,
        visualization_confirmed=True,
    ).require_motion()


def test_joint_delta_is_bounded() -> None:
    assert validate_joint_delta(1.0, 2.0) == 1.0
    with pytest.raises(SafetyGateError, match="refusing"):
        validate_joint_delta(-2.1, 2.0)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_joint_delta_rejects_non_finite_values(value: float) -> None:
    with pytest.raises(SafetyGateError, match="finite"):
        validate_joint_delta(value, 2.0)

    with pytest.raises(ValueError, match="finite and positive"):
        validate_joint_delta(1.0, value)
