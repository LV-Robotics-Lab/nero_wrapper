from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from typing import Protocol


# NERO V112 encodes CPV position as signed 0.001-degree counts.  Keep this
# conversion in one place so duplicate detection agrees exactly with the CAN
# payload produced by pyAgxArm (``round(pos * scale)``).
CPV_POSITION_RESOLUTION_RAD = math.radians(0.001)


class CpvPositionArm(Protocol):
    def get_auto_set_motion_mode_enabled(self) -> bool: ...

    def set_auto_set_motion_mode_enabled(self, enabled: bool) -> None: ...

    def set_motion_mode(self, motion_mode: str) -> None: ...

    def move_cpv_pos(self, joint_index: int, pos: float) -> None: ...


class CpvVelocityArm(Protocol):
    def get_auto_set_motion_mode_enabled(self) -> bool: ...

    def set_auto_set_motion_mode_enabled(self, enabled: bool) -> None: ...

    def set_motion_mode(self, motion_mode: str) -> None: ...

    def move_cpv_vel(self, joint_index: int, vel: float) -> None: ...


class MoveJArm(Protocol):
    def get_auto_set_motion_mode_enabled(self) -> bool: ...

    def set_auto_set_motion_mode_enabled(self, enabled: bool) -> None: ...

    def set_motion_mode(self, motion_mode: str) -> None: ...

    def move_j(self, joints: list[float]) -> None: ...


def complete_joint_positions(
    names: Sequence[str],
    positions: Sequence[float],
    expected_names: Sequence[str],
) -> list[float]:
    """Return a complete ordered target or reject an unsafe partial update."""

    if len(names) != len(positions):
        raise ValueError("joint name/position arrays have different lengths")
    if len(set(names)) != len(names):
        raise ValueError("joint target contains duplicate names")
    unexpected = sorted(set(names) - set(expected_names))
    missing = [name for name in expected_names if name not in names]
    if unexpected or missing:
        details = []
        if missing:
            details.append("missing " + ", ".join(missing))
        if unexpected:
            details.append("unexpected " + ", ".join(unexpected))
        raise ValueError("incomplete joint target: " + "; ".join(details))
    by_name = dict(zip(names, positions))
    ordered = [float(by_name[name]) for name in expected_names]
    if not all(math.isfinite(value) for value in ordered):
        raise ValueError("joint target contains a non-finite value")
    return ordered


def complete_joint_velocities(
    names: Sequence[str],
    velocities: Sequence[float],
    expected_names: Sequence[str],
) -> list[float]:
    """Return a complete ordered velocity target or reject a partial update."""

    if len(names) != len(velocities):
        raise ValueError("joint name/velocity arrays have different lengths")
    if len(set(names)) != len(names):
        raise ValueError("joint velocity target contains duplicate names")
    unexpected = sorted(set(names) - set(expected_names))
    missing = [name for name in expected_names if name not in names]
    if unexpected or missing:
        details = []
        if missing:
            details.append("missing " + ", ".join(missing))
        if unexpected:
            details.append("unexpected " + ", ".join(unexpected))
        raise ValueError("incomplete joint velocity target: " + "; ".join(details))
    by_name = dict(zip(names, velocities))
    ordered = [float(by_name[name]) for name in expected_names]
    if not all(math.isfinite(value) for value in ordered):
        raise ValueError("joint velocity target contains a non-finite value")
    return ordered


def cpv_position_command_key(targets: Sequence[float]) -> tuple[int, ...]:
    """Return the seven encoded CPV position counts used on the CAN bus.

    Targets with the same key would generate identical NERO V112 position
    frames.  This lets the ROS driver avoid repeatedly enqueueing an unchanged
    hold target in firmware while preserving every command that can actually
    change a joint position.
    """

    ordered = [float(value) for value in targets]
    if len(ordered) != 7:
        raise ValueError("CPV position update must contain exactly seven joints")
    if not all(math.isfinite(value) for value in ordered):
        raise ValueError("CPV position target contains a non-finite value")
    return tuple(round(value / CPV_POSITION_RESOLUTION_RAD) for value in ordered)


def send_complete_cpv_positions(
    arm: CpvPositionArm,
    targets: Sequence[float],
    *,
    mode_active: bool,
) -> bool:
    """Batch one seven-joint CPV target with a single mode handover."""

    if len(targets) != 7:
        raise ValueError("CPV position update must contain exactly seven joints")
    automatic_mode = arm.get_auto_set_motion_mode_enabled()
    try:
        if not mode_active:
            arm.set_motion_mode("cpv")
        arm.set_auto_set_motion_mode_enabled(False)
        for joint_index, target in enumerate(targets, start=1):
            arm.move_cpv_pos(joint_index=joint_index, pos=float(target))
    finally:
        arm.set_auto_set_motion_mode_enabled(automatic_mode)
    return True


def send_complete_cpv_velocities(
    arm: CpvVelocityArm,
    targets: Sequence[float],
    *,
    mode_active: bool,
) -> bool:
    """Batch one overwriteable seven-joint CPV velocity reference."""

    ordered = [float(value) for value in targets]
    if len(ordered) != 7:
        raise ValueError("CPV velocity update must contain exactly seven joints")
    if not all(math.isfinite(value) for value in ordered):
        raise ValueError("CPV velocity target contains a non-finite value")

    automatic_mode = arm.get_auto_set_motion_mode_enabled()
    try:
        if not mode_active:
            arm.set_motion_mode("cpv")
        arm.set_auto_set_motion_mode_enabled(False)
        for joint_index, target in enumerate(ordered, start=1):
            arm.move_cpv_vel(joint_index=joint_index, vel=target)
    finally:
        arm.set_auto_set_motion_mode_enabled(automatic_mode)
    return True


def send_complete_move_j(
    arm: MoveJArm,
    targets: Sequence[float],
    *,
    mode_active: bool,
    confirm_mode: Callable[[], bool] | None = None,
) -> bool:
    """Send one complete firmware ``move_j`` target after a confirmed handover.

    NERO's mode command and its seven joint target frames are independent CAN
    messages.  Sending them back-to-back can let the target overtake the
    firmware's CPV-to-J transition.  The caller may therefore wait for MOVE_J
    feedback between the one-time mode command and the target.  Automatic mode
    selection stays disabled while ``move_j`` emits the target frames, so a
    retry does not restart the same handover.
    """

    ordered = [float(value) for value in targets]
    if len(ordered) != 7:
        raise ValueError("move_j update must contain exactly seven joints")
    if not all(math.isfinite(value) for value in ordered):
        raise ValueError("move_j target contains a non-finite value")

    automatic_mode = arm.get_auto_set_motion_mode_enabled()
    try:
        if not mode_active:
            arm.set_motion_mode("j")
            if confirm_mode is not None and not confirm_mode():
                raise TimeoutError(
                    "firmware did not confirm MOVE_J mode before target send"
                )
        arm.set_auto_set_motion_mode_enabled(False)
        arm.move_j(ordered)
    finally:
        arm.set_auto_set_motion_mode_enabled(automatic_mode)
    return True
