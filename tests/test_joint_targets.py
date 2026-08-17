from __future__ import annotations

import pytest

from nero_wrapper.joint_targets import (
    CPV_POSITION_RESOLUTION_RAD,
    complete_joint_positions,
    complete_joint_velocities,
    cpv_position_command_key,
    send_complete_cpv_positions,
    send_complete_cpv_velocities,
    send_complete_move_j,
)


EXPECTED = tuple(f"joint{index}" for index in range(1, 8))


def test_complete_joint_positions_reorders_a_full_named_target() -> None:
    names = tuple(reversed(EXPECTED))
    positions = tuple(float(index) for index in reversed(range(7)))

    assert complete_joint_positions(names, positions, EXPECTED) == [
        float(index) for index in range(7)
    ]


@pytest.mark.parametrize(
    ("names", "positions", "message"),
    [
        (EXPECTED[:-1], (0.0,) * 6, "missing joint7"),
        (EXPECTED, (0.0,) * 6, "different lengths"),
        (EXPECTED[:-1] + ("joint6",), (0.0,) * 7, "duplicate names"),
        (EXPECTED[:-1] + ("joint8",), (0.0,) * 7, "unexpected joint8"),
        (EXPECTED, (0.0,) * 6 + (float("nan"),), "non-finite"),
    ],
)
def test_complete_joint_positions_rejects_unsafe_updates(
    names: tuple[str, ...],
    positions: tuple[float, ...],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        complete_joint_positions(names, positions, EXPECTED)


def test_complete_joint_velocities_reorders_a_full_named_target() -> None:
    names = tuple(reversed(EXPECTED))
    velocities = tuple(float(index) for index in reversed(range(7)))

    assert complete_joint_velocities(names, velocities, EXPECTED) == [
        float(index) for index in range(7)
    ]


@pytest.mark.parametrize(
    ("names", "velocities", "message"),
    [
        (EXPECTED[:-1], (0.0,) * 6, "missing joint7"),
        (EXPECTED, (0.0,) * 6, "different lengths"),
        (EXPECTED[:-1] + ("joint6",), (0.0,) * 7, "duplicate names"),
        (EXPECTED[:-1] + ("joint8",), (0.0,) * 7, "unexpected joint8"),
        (EXPECTED, (0.0,) * 6 + (float("nan"),), "non-finite"),
    ],
)
def test_complete_joint_velocities_rejects_unsafe_updates(
    names: tuple[str, ...],
    velocities: tuple[float, ...],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        complete_joint_velocities(names, velocities, EXPECTED)


def test_cpv_position_command_key_matches_firmware_resolution() -> None:
    targets = [0.0] * 7
    baseline = cpv_position_command_key(targets)

    targets[3] = CPV_POSITION_RESOLUTION_RAD * 0.49
    assert cpv_position_command_key(targets) == baseline

    targets[3] = CPV_POSITION_RESOLUTION_RAD * 0.51
    changed = cpv_position_command_key(targets)
    assert changed != baseline
    assert changed[3] == 1


@pytest.mark.parametrize(
    ("targets", "message"),
    [
        ([0.0] * 6, "exactly seven"),
        ([0.0] * 6 + [float("inf")], "non-finite"),
    ],
)
def test_cpv_position_command_key_rejects_invalid_targets(
    targets: list[float],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        cpv_position_command_key(targets)


class FakeCpvArm:
    def __init__(self, *, fail_at_joint: int | None = None) -> None:
        self.automatic_mode = True
        self.fail_at_joint = fail_at_joint
        self.calls: list[tuple[object, ...]] = []

    def get_auto_set_motion_mode_enabled(self) -> bool:
        return self.automatic_mode

    def set_auto_set_motion_mode_enabled(self, enabled: bool) -> None:
        self.automatic_mode = enabled
        self.calls.append(("automatic", enabled))

    def set_motion_mode(self, motion_mode: str) -> None:
        self.calls.append(("mode", motion_mode))

    def move_cpv_pos(self, joint_index: int, pos: float) -> None:
        self.calls.append(("position", joint_index, pos))
        if joint_index == self.fail_at_joint:
            raise RuntimeError("injected CPV send failure")

    def move_cpv_vel(self, joint_index: int, vel: float) -> None:
        self.calls.append(("velocity", joint_index, vel))
        if joint_index == self.fail_at_joint:
            raise RuntimeError("injected CPV send failure")


def test_send_complete_cpv_positions_batches_one_mode_handover() -> None:
    arm = FakeCpvArm()

    active = send_complete_cpv_positions(
        arm,
        [0.1 * index for index in range(7)],
        mode_active=False,
    )

    assert active is True
    assert arm.calls[0] == ("mode", "cpv")
    assert arm.calls[1] == ("automatic", False)
    assert arm.calls[2:9] == [
        ("position", index + 1, 0.1 * index) for index in range(7)
    ]
    assert arm.calls[-1] == ("automatic", True)


def test_send_complete_cpv_positions_skips_redundant_mode_frame() -> None:
    arm = FakeCpvArm()

    send_complete_cpv_positions(arm, [0.0] * 7, mode_active=True)

    assert ("mode", "cpv") not in arm.calls


def test_send_complete_cpv_positions_restores_auto_mode_after_failure() -> None:
    arm = FakeCpvArm(fail_at_joint=4)

    with pytest.raises(RuntimeError, match="injected"):
        send_complete_cpv_positions(arm, [0.0] * 7, mode_active=False)

    assert arm.automatic_mode is True
    assert arm.calls[-1] == ("automatic", True)


def test_send_complete_cpv_velocities_batches_one_mode_handover() -> None:
    arm = FakeCpvArm()

    active = send_complete_cpv_velocities(
        arm,
        [0.1 * index for index in range(7)],
        mode_active=False,
    )

    assert active is True
    assert arm.calls[0] == ("mode", "cpv")
    assert arm.calls[1] == ("automatic", False)
    assert arm.calls[2:9] == [
        ("velocity", index + 1, 0.1 * index) for index in range(7)
    ]
    assert arm.calls[-1] == ("automatic", True)


def test_send_complete_cpv_velocities_skips_redundant_mode_frame() -> None:
    arm = FakeCpvArm()

    send_complete_cpv_velocities(arm, [0.0] * 7, mode_active=True)

    assert ("mode", "cpv") not in arm.calls


def test_send_complete_cpv_velocities_restores_auto_mode_after_failure() -> None:
    arm = FakeCpvArm(fail_at_joint=4)

    with pytest.raises(RuntimeError, match="injected"):
        send_complete_cpv_velocities(arm, [0.0] * 7, mode_active=False)

    assert arm.automatic_mode is True
    assert arm.calls[-1] == ("automatic", True)


class FakeMoveJArm(FakeCpvArm):
    def move_j(self, joints: list[float]) -> None:
        self.calls.append(("move_j", tuple(joints)))


def test_send_complete_move_j_confirms_handover_before_target() -> None:
    arm = FakeMoveJArm()

    active = send_complete_move_j(
        arm,
        [0.1 * index for index in range(7)],
        mode_active=False,
        confirm_mode=lambda: arm.calls.append(("confirmed",)) or True,
    )

    assert active is True
    assert arm.calls == [
        ("mode", "j"),
        ("confirmed",),
        ("automatic", False),
        ("move_j", tuple(0.1 * index for index in range(7))),
        ("automatic", True),
    ]


def test_send_complete_move_j_retry_skips_redundant_mode_frame() -> None:
    arm = FakeMoveJArm()

    send_complete_move_j(arm, [0.0] * 7, mode_active=True)

    assert ("mode", "j") not in arm.calls
    assert ("move_j", (0.0,) * 7) in arm.calls


def test_send_complete_move_j_does_not_send_target_before_mode_confirmation() -> None:
    arm = FakeMoveJArm()

    with pytest.raises(TimeoutError, match="did not confirm MOVE_J"):
        send_complete_move_j(
            arm,
            [0.0] * 7,
            mode_active=False,
            confirm_mode=lambda: False,
        )

    assert not any(call[0] == "move_j" for call in arm.calls)
    assert arm.automatic_mode is True
