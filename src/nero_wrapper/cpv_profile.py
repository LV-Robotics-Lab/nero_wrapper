"""Inspect or deliberately stage persistent NERO CPV settings.

The vendor ``set_cpv_*`` calls write motor-controller Flash.  This module
therefore defaults to inspection, requires every motor to be disabled before a
write, skips unchanged values, performs an explicit read-back after every ACK,
and rolls back already-written fields if a later write fails.
"""

from __future__ import annotations

import argparse
import json
import math
import time
from contextlib import ExitStack
from dataclasses import dataclass
from typing import Any, Callable

from .sdk import NeroArm

JOINT_INDICES = tuple(range(1, 8))
WRITE_CONFIRMATION = "WRITE_NERO_CPV_FLASH"
ACCELERATION_WRITE_CONFIRMATION = "WRITE_NERO_ACCELERATION_FLASH"
POSITION_GAIN_WRITE_CONFIRMATION = "WRITE_NERO_CPV_PP_FLASH"
MIN_STAGED_ACCELERATION = 0.03
# pyAgxArm's NERO CPV API uses 2.0 rad/s^2 in its documented write example.
# The joint-limit protocol permits up to 5.0, but this combined CPV/joint tool
# stays bounded to the value documented for both layers.
MAX_STAGED_ACCELERATION = 2.00
MIN_STAGED_POSITION_GAIN = 0.01
# This field tool is intentionally bounded to the explicitly reviewed target.
# Raising it further requires a new measured response audit and code change.
MAX_STAGED_POSITION_GAIN = 10.00
READBACK_ABS_TOLERANCE = 0.0051
LIMIT_COMPARISON_TOLERANCE = 0.00051
READBACK_ATTEMPTS = 3
READBACK_RETRY_DELAY_S = 0.15
FLASH_SETTLE_DELAY_S = 1.0
JOINT_LIMIT_SETTLE_DELAY_S = 1.0
CPV_PARAMETER_QUANTUM = 0.01
MAX_WRITE_ATTEMPTS = 2
JOINT_LIMIT_ABS_TOLERANCE = 0.00051


@dataclass(frozen=True, slots=True)
class CpvMotionProfile:
    acc: tuple[float, ...]
    dcc: tuple[float, ...]
    cv: tuple[float, ...]

    def as_dict(self) -> dict[str, list[float]]:
        return {
            "acc": list(self.acc),
            "dcc": list(self.dcc),
            "cv": list(self.cv),
        }


@dataclass(frozen=True, slots=True)
class CpvLoopGains:
    pp: tuple[float, ...]
    kp: tuple[float, ...]
    ki: tuple[float, ...]

    def as_dict(self) -> dict[str, list[float]]:
        return {
            "pp": list(self.pp),
            "kp": list(self.kp),
            "ki": list(self.ki),
        }


def _read_finite_value(robot: Any, field: str, joint: int) -> float:
    getter = getattr(robot, f"get_cpv_{field}")
    value = None
    for attempt in range(READBACK_ATTEMPTS):
        value = getter(joint, timeout=1.0, min_interval=0.0)
        if value is not None and math.isfinite(float(value)):
            return float(value)
        if attempt + 1 < READBACK_ATTEMPTS:
            time.sleep(READBACK_RETRY_DELAY_S)
    raise TimeoutError(f"no finite CPV {field} read-back for joint {joint}")


def _read_values(robot: Any, field: str) -> tuple[float, ...]:
    values = []
    for joint in JOINT_INDICES:
        values.append(_read_finite_value(robot, field, joint))
    return tuple(values)


def read_motion_profile(robot: Any) -> CpvMotionProfile:
    return CpvMotionProfile(
        acc=_read_values(robot, "acc"),
        dcc=_read_values(robot, "dcc"),
        cv=_read_values(robot, "cv"),
    )


def read_loop_gains(robot: Any) -> CpvLoopGains:
    return CpvLoopGains(
        pp=_read_values(robot, "pp"),
        kp=_read_values(robot, "kp"),
        ki=_read_values(robot, "ki"),
    )


def read_joint_acceleration_limits(robot: Any) -> tuple[float, ...]:
    values = []
    for joint in JOINT_INDICES:
        message = robot.get_joint_acc_limits(
            joint,
            timeout=1.0,
            min_interval=0.0,
        )
        value = None if message is None else message.msg.max_joint_acc
        if value is None or not math.isfinite(float(value)):
            raise TimeoutError(
                f"no finite joint acceleration limit for joint {joint}"
            )
        values.append(float(value))
    return tuple(values)


def motors_are_disabled(robot: Any) -> bool:
    states = tuple(robot.get_joints_enable_status_list())
    return len(states) == 7 and all(state is False for state in states)


def audit_responsive_acceleration_profiles(
    robots: dict[str, Any],
    value: float,
) -> dict[str, dict[str, object]]:
    """Read-only launch audit for the coupled joint/CPV acceleration state."""

    target = validate_staged_acceleration(value)
    if not robots:
        raise ValueError("at least one NERO arm is required")
    results: dict[str, dict[str, object]] = {}
    mismatches: list[str] = []
    for name, robot in robots.items():
        disabled = motors_are_disabled(robot)
        limits = read_joint_acceleration_limits(robot)
        profile = read_motion_profile(robot)
        results[name] = {
            "motors_disabled": disabled,
            "joint_acceleration_limits": list(limits),
            "profile": profile.as_dict(),
        }
        if not disabled:
            mismatches.append(f"{name}: motors are not all disabled")
        for joint, actual in zip(JOINT_INDICES, limits):
            if not math.isclose(
                actual,
                target,
                rel_tol=0.0,
                abs_tol=JOINT_LIMIT_ABS_TOLERANCE,
            ):
                mismatches.append(
                    f"{name}: joint {joint} acceleration limit "
                    f"{actual:.3f} != {target:.3f}"
                )
        for field in ("acc", "dcc"):
            for joint, actual in zip(JOINT_INDICES, getattr(profile, field)):
                if not math.isclose(
                    actual,
                    target,
                    rel_tol=0.0,
                    abs_tol=READBACK_ABS_TOLERANCE,
                ):
                    mismatches.append(
                        f"{name}: CPV {field} joint {joint} "
                        f"{actual:.3f} != {target:.3f}"
                    )
    if mismatches:
        raise RuntimeError(
            "responsive acceleration launch audit failed: "
            + "; ".join(mismatches)
        )
    return results


def audit_position_gain_profiles(
    robots: dict[str, Any],
    value: float,
) -> dict[str, dict[str, object]]:
    """Read-only launch audit for the persistent CPV position-loop gain."""

    target = validate_staged_position_gain(value)
    if not robots:
        raise ValueError("at least one NERO arm is required")
    results: dict[str, dict[str, object]] = {}
    mismatches: list[str] = []
    for name, robot in robots.items():
        disabled = motors_are_disabled(robot)
        values = _read_values(robot, "pp")
        results[name] = {
            "motors_disabled": disabled,
            "position_gains": list(values),
        }
        if not disabled:
            mismatches.append(f"{name}: motors are not all disabled")
        for joint, actual in zip(JOINT_INDICES, values):
            if not math.isclose(
                actual,
                target,
                rel_tol=0.0,
                abs_tol=READBACK_ABS_TOLERANCE,
            ):
                mismatches.append(
                    f"{name}: CPV pp joint {joint} "
                    f"{actual:.3f} != {target:.3f}"
                )
    if mismatches:
        raise RuntimeError(
            "position gain launch audit failed: " + "; ".join(mismatches)
        )
    return results


def validate_staged_acceleration(value: float) -> float:
    result = float(value)
    if (
        not math.isfinite(result)
        or result < MIN_STAGED_ACCELERATION
        or result > MAX_STAGED_ACCELERATION
    ):
        raise ValueError(
            "staged CPV acceleration must be between "
            f"{MIN_STAGED_ACCELERATION:.2f} and "
            f"{MAX_STAGED_ACCELERATION:.2f} rad/s^2"
        )
    return result


def validate_staged_position_gain(value: float) -> float:
    result = float(value)
    if (
        not math.isfinite(result)
        or result < MIN_STAGED_POSITION_GAIN
        or result > MAX_STAGED_POSITION_GAIN
    ):
        raise ValueError(
            "staged CPV position gain must be between "
            f"{MIN_STAGED_POSITION_GAIN:.2f} and "
            f"{MAX_STAGED_POSITION_GAIN:.2f}"
        )
    return result


def _write_and_verify(
    robot: Any,
    field: str,
    joint: int,
    value: float,
    *,
    command_correction: float = 0.0,
) -> float:
    """Write one value and return any learned firmware quantization correction."""

    setter: Callable[..., bool] = getattr(robot, f"set_cpv_{field}")
    target = round(float(value) / CPV_PARAMETER_QUANTUM) * CPV_PARAMETER_QUANTUM
    correction = (
        round(float(command_correction) / CPV_PARAMETER_QUANTUM)
        * CPV_PARAMETER_QUANTUM
    )
    readback = None
    for attempt in range(MAX_WRITE_ATTEMPTS):
        command = (
            round((target + correction) / CPV_PARAMETER_QUANTUM)
            * CPV_PARAMETER_QUANTUM
        )
        if not setter(joint, command, timeout=1.0):
            raise RuntimeError(
                f"CPV {field} joint {joint} did not ACK the Flash write"
            )
        # Firmware ACKs before its persistent value is reliably queryable.
        # Respect the vendor getter's documented one-second request spacing.
        time.sleep(FLASH_SETTLE_DELAY_S)
        try:
            readback = _read_finite_value(robot, field, joint)
        except TimeoutError as exc:
            raise RuntimeError(str(exc)) from exc
        if math.isclose(
            readback,
            target,
            rel_tol=0.0,
            abs_tol=READBACK_ABS_TOLERANCE,
        ):
            return correction
        error = target - readback
        # The installed NERO 1.121 firmware was observed to store one 0.01
        # unit below the requested CPV value.  Learn that bounded correction
        # from read-back instead of hard-coding it, then verify a second write.
        if attempt + 1 >= MAX_WRITE_ATTEMPTS or abs(error) > (
            CPV_PARAMETER_QUANTUM + READBACK_ABS_TOLERANCE
        ):
            break
        correction = (
            round((correction + error) / CPV_PARAMETER_QUANTUM)
            * CPV_PARAMETER_QUANTUM
        )
    raise RuntimeError(
        f"CPV {field} joint {joint} read-back {readback!r} "
        f"does not match {target:.3f}"
    )


def apply_staged_acceleration(
    robot: Any,
    value: float,
) -> tuple[CpvMotionProfile, CpvMotionProfile]:
    profiles = apply_staged_acceleration_profiles({"arm": robot}, value)
    return profiles["arm"]


def apply_staged_parameter(
    robot: Any,
    *,
    field: str,
    joint: int,
    value: float,
) -> tuple[float, float]:
    """Write one explicitly selected CPV acceleration field transactionally."""

    if field not in {"acc", "dcc"}:
        raise ValueError("field must be acc or dcc")
    if joint not in JOINT_INDICES:
        raise ValueError("joint must be between 1 and 7")
    target = validate_staged_acceleration(value)
    if not motors_are_disabled(robot):
        raise RuntimeError("all seven NERO motors must be confirmed disabled")
    before = _read_finite_value(robot, field, joint)
    if math.isclose(
        before,
        target,
        rel_tol=0.0,
        abs_tol=READBACK_ABS_TOLERANCE,
    ):
        return before, before
    correction = 0.0
    try:
        correction = _write_and_verify(robot, field, joint, target)
        after = _read_finite_value(robot, field, joint)
        if not math.isclose(
            after,
            target,
            rel_tol=0.0,
            abs_tol=READBACK_ABS_TOLERANCE,
        ):
            raise RuntimeError(
                f"CPV {field} joint {joint} final read-back {after!r} "
                f"does not match {target:.3f}"
            )
    except Exception as write_error:
        try:
            _write_and_verify(
                robot,
                field,
                joint,
                before,
                command_correction=correction,
            )
        except Exception as rollback_error:
            raise RuntimeError(
                f"single CPV staging failed: {write_error}; "
                f"rollback failed: {rollback_error}"
            ) from write_error
        raise RuntimeError(
            f"single CPV staging failed and was rolled back: {write_error}"
        ) from write_error
    return before, after


def apply_staged_acceleration_profiles(
    robots: dict[str, Any],
    value: float,
) -> dict[str, tuple[CpvMotionProfile, CpvMotionProfile]]:
    """Apply one dual-arm transaction, rolling every touched field back."""

    target = validate_staged_acceleration(value)
    if not robots:
        raise ValueError("at least one NERO arm is required")
    for name, robot in robots.items():
        if not motors_are_disabled(robot):
            raise RuntimeError(
                f"{name}: all seven NERO motors must be confirmed disabled"
            )
    acceleration_limits = {
        name: read_joint_acceleration_limits(robot)
        for name, robot in robots.items()
    }
    for name, limits in acceleration_limits.items():
        for joint, limit in zip(JOINT_INDICES, limits):
            if target > limit + LIMIT_COMPARISON_TOLERANCE:
                raise RuntimeError(
                    f"{name}: requested CPV acceleration {target:.3f} rad/s^2 "
                    f"exceeds joint {joint} firmware acceleration limit "
                    f"{limit:.3f} rad/s^2; no CPV Flash fields were written"
                )
    before = {name: read_motion_profile(robot) for name, robot in robots.items()}
    written: list[tuple[str, str, int, float]] = []
    command_corrections: dict[tuple[str, str], float] = {}
    try:
        for name, robot in robots.items():
            for field in ("acc", "dcc"):
                original_values = getattr(before[name], field)
                for joint, original in zip(JOINT_INDICES, original_values):
                    if math.isclose(
                        original,
                        target,
                        rel_tol=0.0,
                        abs_tol=READBACK_ABS_TOLERANCE,
                    ):
                        continue
                    # Record the field before sending anything: an ACK followed
                    # by a failed read-back can still mean Flash changed.
                    written.append((name, field, joint, original))
                    key = (name, field)
                    command_corrections[key] = _write_and_verify(
                        robot,
                        field,
                        joint,
                        target,
                        command_correction=command_corrections.get(key, 0.0),
                    )
        after = {
            name: read_motion_profile(robot) for name, robot in robots.items()
        }
        for name, profile in after.items():
            if any(
                not math.isclose(
                    item,
                    target,
                    rel_tol=0.0,
                    abs_tol=READBACK_ABS_TOLERANCE,
                )
                for values in (profile.acc, profile.dcc)
                for item in values
            ):
                raise RuntimeError(
                    f"{name}: final CPV acceleration/deceleration audit failed"
                )
    except Exception as write_error:
        rollback_errors = []
        for name, field, joint, original in reversed(written):
            try:
                key = (name, field)
                command_corrections[key] = _write_and_verify(
                    robots[name],
                    field,
                    joint,
                    original,
                    command_correction=command_corrections.get(key, 0.0),
                )
            except Exception as rollback_error:  # pragma: no cover - hardware only
                rollback_errors.append(f"{name}: {rollback_error}")
        detail = (
            ""
            if not rollback_errors
            else "; rollback failures: " + "; ".join(rollback_errors)
        )
        raise RuntimeError(f"CPV staging failed: {write_error}{detail}") from write_error
    return {name: (before[name], after[name]) for name in robots}


def apply_staged_position_gain_profiles(
    robots: dict[str, Any],
    value: float,
) -> dict[str, tuple[tuple[float, ...], tuple[float, ...]]]:
    """Atomically stage CPV ``pp`` for every joint on every supplied arm."""

    target = validate_staged_position_gain(value)
    if not robots:
        raise ValueError("at least one NERO arm is required")
    for name, robot in robots.items():
        if not motors_are_disabled(robot):
            raise RuntimeError(
                f"{name}: all seven NERO motors must be confirmed disabled"
            )
    before = {
        name: _read_values(robot, "pp") for name, robot in robots.items()
    }
    # Baseline reads take multiple CAN round trips. Reconfirm the disable state
    # immediately before the first persistent write as a separate gate.
    for name, robot in robots.items():
        if not motors_are_disabled(robot):
            raise RuntimeError(
                f"{name}: a motor became enabled before the CPV pp write"
            )

    written: list[tuple[str, int, float]] = []
    command_corrections: dict[str, float] = {}
    try:
        for name, robot in robots.items():
            for joint, original in zip(JOINT_INDICES, before[name]):
                if math.isclose(
                    original,
                    target,
                    rel_tol=0.0,
                    abs_tol=READBACK_ABS_TOLERANCE,
                ):
                    continue
                # Record before sending: an ACK followed by a failed query can
                # still mean the controller committed the Flash value.
                written.append((name, joint, original))
                command_corrections[name] = _write_and_verify(
                    robot,
                    "pp",
                    joint,
                    target,
                    command_correction=command_corrections.get(name, 0.0),
                )
        after = {
            name: _read_values(robot, "pp") for name, robot in robots.items()
        }
        for name, values in after.items():
            if any(
                not math.isclose(
                    item,
                    target,
                    rel_tol=0.0,
                    abs_tol=READBACK_ABS_TOLERANCE,
                )
                for item in values
            ):
                raise RuntimeError(f"{name}: final CPV pp audit failed")
    except Exception as write_error:
        rollback_errors = []
        for name, joint, original in reversed(written):
            try:
                command_corrections[name] = _write_and_verify(
                    robots[name],
                    "pp",
                    joint,
                    original,
                    command_correction=command_corrections.get(name, 0.0),
                )
            except Exception as rollback_error:  # pragma: no cover - hardware only
                rollback_errors.append(f"{name}: J{joint}: {rollback_error}")
        detail = (
            ""
            if not rollback_errors
            else "; rollback failures: " + "; ".join(rollback_errors)
        )
        raise RuntimeError(
            f"CPV pp staging failed: {write_error}{detail}"
        ) from write_error
    return {name: (before[name], after[name]) for name in robots}


def _write_joint_limit_and_verify(
    robot: Any,
    joint: int,
    value: float,
) -> float:
    if not robot.set_joint_acc_limits(
        joint,
        max_joint_acc=value,
        timeout=2.0,
    ):
        raise RuntimeError(
            f"joint {joint} acceleration limit write/read-back failed"
        )
    time.sleep(JOINT_LIMIT_SETTLE_DELAY_S)
    message = robot.get_joint_acc_limits(
        joint,
        timeout=1.0,
        min_interval=0.0,
    )
    readback = None if message is None else message.msg.max_joint_acc
    if readback is None or not math.isclose(
        float(readback),
        value,
        rel_tol=0.0,
        abs_tol=JOINT_LIMIT_ABS_TOLERANCE,
    ):
        raise RuntimeError(
            f"joint {joint} acceleration limit read-back {readback!r} "
            f"does not match {value:.3f}"
        )
    return float(readback)


def _restore_cpv_acceleration_profiles(
    robots: dict[str, Any],
    profiles: dict[str, CpvMotionProfile],
) -> list[str]:
    """Best-effort exact CPV rollback after joint-limit writes.

    NERO 1.121 was observed to couple ``set_joint_acc_limits`` to the CPV
    acceleration/deceleration fields.  Restore the saved CPV values *after*
    restoring the joint limits so that a limit rollback cannot overwrite the
    original CPV profile a second time.
    """

    errors: list[str] = []
    command_corrections: dict[tuple[str, str], float] = {}
    for name, robot in robots.items():
        try:
            current = read_motion_profile(robot)
        except Exception:
            current = None
        for field in ("acc", "dcc"):
            original_values = getattr(profiles[name], field)
            current_values = (
                None if current is None else getattr(current, field)
            )
            for joint, original in zip(JOINT_INDICES, original_values):
                if current_values is not None and math.isclose(
                    current_values[joint - 1],
                    original,
                    rel_tol=0.0,
                    abs_tol=READBACK_ABS_TOLERANCE,
                ):
                    continue
                key = (name, field)
                try:
                    command_corrections[key] = _write_and_verify(
                        robot,
                        field,
                        joint,
                        original,
                        command_correction=command_corrections.get(key, 0.0),
                    )
                except Exception as exc:  # pragma: no cover - hardware only
                    errors.append(f"{name}: CPV {field} J{joint}: {exc}")
        try:
            restored = read_motion_profile(robot)
            for field in ("acc", "dcc"):
                if any(
                    not math.isclose(
                        actual,
                        original,
                        rel_tol=0.0,
                        abs_tol=READBACK_ABS_TOLERANCE,
                    )
                    for actual, original in zip(
                        getattr(restored, field),
                        getattr(profiles[name], field),
                    )
                ):
                    errors.append(f"{name}: final CPV {field} rollback audit failed")
        except Exception as exc:  # pragma: no cover - hardware only
            errors.append(f"{name}: final CPV rollback audit: {exc}")
    return errors


def apply_responsive_acceleration_profiles(
    robots: dict[str, Any],
    value: float,
) -> dict[str, dict[str, object]]:
    """Atomically raise joint ceilings, then matching CPV acc/dcc values."""

    target = validate_staged_acceleration(value)
    if not robots:
        raise ValueError("at least one NERO arm is required")
    for name, robot in robots.items():
        if not motors_are_disabled(robot):
            raise RuntimeError(
                f"{name}: all seven NERO motors must be confirmed disabled"
            )
    before_limits = {
        name: read_joint_acceleration_limits(robot)
        for name, robot in robots.items()
    }
    # Capture this before the first joint-limit write.  Firmware 1.121 can
    # update CPV acc/dcc as a side effect of that write.
    before_cpv = {
        name: read_motion_profile(robot) for name, robot in robots.items()
    }
    limit_writes: list[tuple[str, int, float]] = []
    try:
        for name, robot in robots.items():
            for joint, original in zip(JOINT_INDICES, before_limits[name]):
                if math.isclose(
                    original,
                    target,
                    rel_tol=0.0,
                    abs_tol=JOINT_LIMIT_ABS_TOLERANCE,
                ):
                    continue
                # Record before sending because a failed verification can still
                # follow a controller-side persistent change.
                limit_writes.append((name, joint, original))
                _write_joint_limit_and_verify(robot, joint, target)
        after_limits = {
            name: read_joint_acceleration_limits(robot)
            for name, robot in robots.items()
        }
        for name, values in after_limits.items():
            if any(
                not math.isclose(
                    item,
                    target,
                    rel_tol=0.0,
                    abs_tol=JOINT_LIMIT_ABS_TOLERANCE,
                )
                for item in values
            ):
                raise RuntimeError(
                    f"{name}: final joint acceleration limit audit failed"
                )
        cpv_profiles = apply_staged_acceleration_profiles(robots, target)
    except Exception as write_error:
        rollback_errors = []
        for name, joint, original in reversed(limit_writes):
            try:
                _write_joint_limit_and_verify(
                    robots[name],
                    joint,
                    original,
                )
            except Exception as rollback_error:  # pragma: no cover - hardware only
                rollback_errors.append(f"{name}: {rollback_error}")
        rollback_errors.extend(
            _restore_cpv_acceleration_profiles(robots, before_cpv)
        )
        detail = (
            ""
            if not rollback_errors
            else "; rollback failures: " + "; ".join(rollback_errors)
        )
        raise RuntimeError(
            f"responsive acceleration staging failed: {write_error}{detail}"
        ) from write_error
    return {
        name: {
            "joint_limits_before": list(before_limits[name]),
            "joint_limits_after": list(after_limits[name]),
            "cpv_before": before_cpv[name].as_dict(),
            "cpv_after": cpv_profiles[name][1].as_dict(),
        }
        for name in robots
    }


def _inspect_arm(name: str) -> dict[str, object]:
    with NeroArm(name) as arm:
        return {
            "arm": name,
            "channel": arm.endpoint.channel,
            "motors_disabled": motors_are_disabled(arm.raw),
            "joint_acceleration_limits": list(
                read_joint_acceleration_limits(arm.raw)
            ),
            "profile": read_motion_profile(arm.raw).as_dict(),
            "loop_gains": read_loop_gains(arm.raw).as_dict(),
        }


def _apply_both(value: float) -> list[dict[str, object]]:
    with ExitStack() as stack:
        arms = {
            name: stack.enter_context(NeroArm(name))
            for name in ("arm_a", "arm_b")
        }
        profiles = apply_staged_acceleration_profiles(
            {name: arm.raw for name, arm in arms.items()},
            value,
        )
        return [
            {
                "arm": name,
                "channel": arms[name].endpoint.channel,
                "before": profiles[name][0].as_dict(),
                "after": profiles[name][1].as_dict(),
            }
            for name in ("arm_a", "arm_b")
        ]


def _apply_one(
    arm_name: str,
    field: str,
    joint: int,
    value: float,
) -> dict[str, object]:
    with NeroArm(arm_name) as arm:
        before, after = apply_staged_parameter(
            arm.raw,
            field=field,
            joint=joint,
            value=value,
        )
        return {
            "arm": arm_name,
            "channel": arm.endpoint.channel,
            "field": field,
            "joint": joint,
            "before": before,
            "after": after,
        }


def _apply_responsive_both(value: float) -> list[dict[str, object]]:
    with ExitStack() as stack:
        arms = {
            name: stack.enter_context(NeroArm(name))
            for name in ("arm_a", "arm_b")
        }
        profiles = apply_responsive_acceleration_profiles(
            {name: arm.raw for name, arm in arms.items()},
            value,
        )
        return [
            {
                "arm": name,
                "channel": arms[name].endpoint.channel,
                **profiles[name],
            }
            for name in ("arm_a", "arm_b")
        ]


def _apply_position_gain_both(value: float) -> list[dict[str, object]]:
    with ExitStack() as stack:
        arms = {
            name: stack.enter_context(NeroArm(name))
            for name in ("arm_a", "arm_b")
        }
        gains = apply_staged_position_gain_profiles(
            {name: arm.raw for name, arm in arms.items()},
            value,
        )
        return [
            {
                "arm": name,
                "channel": arms[name].endpoint.channel,
                "pp_before": list(gains[name][0]),
                "pp_after": list(gains[name][1]),
            }
            for name in ("arm_a", "arm_b")
        ]


def _verify_responsive_both(
    value: float,
    position_gain: float | None = None,
) -> list[dict[str, object]]:
    with ExitStack() as stack:
        arms = {
            name: stack.enter_context(NeroArm(name))
            for name in ("arm_a", "arm_b")
        }
        results = audit_responsive_acceleration_profiles(
            {name: arm.raw for name, arm in arms.items()},
            value,
        )
        position_results = (
            {}
            if position_gain is None
            else audit_position_gain_profiles(
                {name: arm.raw for name, arm in arms.items()},
                position_gain,
            )
        )
        return [
            {
                "arm": name,
                "channel": arms[name].endpoint.channel,
                **results[name],
                **(
                    {}
                    if position_gain is None
                    else {
                        "position_gains": position_results[name][
                            "position_gains"
                        ]
                    }
                ),
            }
            for name in ("arm_a", "arm_b")
        ]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("inspect")
    verify_parser = subparsers.add_parser("verify")
    verify_parser.add_argument("--acceleration", type=float, required=True)
    verify_parser.add_argument("--position-gain", type=float)
    apply_parser = subparsers.add_parser("apply")
    apply_parser.add_argument("--acceleration", type=float, required=True)
    apply_parser.add_argument("--confirmation", default="")
    repair_parser = subparsers.add_parser("repair")
    repair_parser.add_argument("--arm", choices=("arm_a", "arm_b"), required=True)
    repair_parser.add_argument("--field", choices=("acc", "dcc"), required=True)
    repair_parser.add_argument("--joint", type=int, choices=JOINT_INDICES, required=True)
    repair_parser.add_argument("--value", type=float, required=True)
    repair_parser.add_argument("--confirmation", default="")
    responsive_parser = subparsers.add_parser("responsive")
    responsive_parser.add_argument("--acceleration", type=float, required=True)
    responsive_parser.add_argument("--confirmation", default="")
    pp_parser = subparsers.add_parser("pp-stage")
    pp_parser.add_argument("--position-gain", type=float, required=True)
    pp_parser.add_argument("--confirmation", default="")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    required_confirmation = {
        "apply": WRITE_CONFIRMATION,
        "repair": WRITE_CONFIRMATION,
        "responsive": ACCELERATION_WRITE_CONFIRMATION,
        "pp-stage": POSITION_GAIN_WRITE_CONFIRMATION,
    }.get(args.command)
    if (
        required_confirmation is not None
        and args.confirmation != required_confirmation
    ):
        raise SystemExit(
            "persistent CPV Flash write requires --confirmation "
            f"{required_confirmation}"
        )
    if args.command == "inspect":
        results = [_inspect_arm(name) for name in ("arm_a", "arm_b")]
    elif args.command == "verify":
        results = _verify_responsive_both(
            args.acceleration,
            args.position_gain,
        )
    elif args.command == "apply":
        results = _apply_both(args.acceleration)
    elif args.command == "repair":
        results = [
            _apply_one(args.arm, args.field, args.joint, args.value)
        ]
    elif args.command == "responsive":
        results = _apply_responsive_both(args.acceleration)
    else:
        results = _apply_position_gain_both(args.position_gain)
    print(json.dumps({"cpv": results}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
