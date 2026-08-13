"""Read-only NERO preflight check for the XRoboToolkit teleop path.

This script never enables a motor and never sends motion. It connects to each
CAN channel, reports the controller state that gates live teleoperation, and
tells you exactly what to fix before running teleop_dual_nero_hardware.py.

    python scripts/hardware/nero_preflight.py
    python scripts/hardware/nero_preflight.py --arm-a-can can0 --arm-b-can can1
"""

from __future__ import annotations

import time

import tyro

from xrobotoolkit_teleop.hardware.interface.nero import (
    NERO_CTRL_MODE_CAN,
    NERO_ARM_STATUS_NORMAL,
    NeroArmInterface,
    NeroSafetyError,
    _ctrl_mode_help,
    _enum_value,
)


def _check_arm(arm_name: str, channel: str, firmware: str, timeout_s: float) -> list[str]:
    """Connect read-only and return the list of blockers for this arm."""
    blockers: list[str] = []
    interface = NeroArmInterface(
        arm_name=arm_name,
        channel=channel,
        firmware=firmware,
        execute=False,  # read-only: arm() can never be called from here
    )
    try:
        interface.connect(timeout_s=timeout_s)
    except Exception as exc:
        print(f"  {arm_name} [{channel}]: NOT REACHABLE -- {type(exc).__name__}: {exc}")
        return [f"{arm_name}: no CAN feedback on {channel} ({exc})"]

    try:
        # connect() returns on the first complete frame, before the SDK's rate
        # estimator has produced a nonzero hz. Settle briefly so the reported
        # feedback rate reflects the real stream instead of the warm-up zero.
        time.sleep(1.0)
        print(f"  {interface.describe_status()}")
        if interface.detected_firmware_version is not None:
            print(
                f"    firmware {interface.detected_firmware_version} "
                f"-> driver {interface.resolved_firmware}"
            )

        state = interface.read_state()
        message = getattr(state.status, "msg", None)
        ctrl_mode = _enum_value(getattr(message, "ctrl_mode", None))
        arm_status = _enum_value(getattr(message, "arm_status", None))

        if ctrl_mode != NERO_CTRL_MODE_CAN:
            # Not a blocker: the official enable() re-sends the 0x151 mode frame
            # and claims CAN control itself. Report it so the operator knows the
            # handover is expected, but do not stop the run.
            print(
                f"    note: ctrl_mode is not CAN_CTRL yet "
                f"({_ctrl_mode_help(getattr(message, 'ctrl_mode', None))}); "
                "arming will claim CAN control via the 0x151 mode frame"
            )
        enable_bits = interface.joint_enable_bits()
        if not any(enable_bits):
            # Expected before arming; note it but do not call it a blocker.
            print("    note: all 7 joints disabled (normal before arming)")
        elif not all(enable_bits):
            stuck = [f"joint{i}" for i, bit in enumerate(enable_bits, 1) if not bit]
            blockers.append(f"{arm_name}: partially enabled, still clear: {', '.join(stuck)}")
        if arm_status not in (NERO_ARM_STATUS_NORMAL, 0x1, 0x6):
            blockers.append(
                f"{arm_name}: arm_status needs operator attention before teleop"
            )
        if state.feedback_hz <= 0.0:
            blockers.append(f"{arm_name}: joint feedback stream is 0 Hz")
    except NeroSafetyError as exc:
        blockers.append(f"{arm_name}: {exc}")
        print(f"    {exc}")
    finally:
        interface.close(hold_if_armed=False, disable_if_armed=False)
    return blockers


def main(
    arm_a_can: str = "can0",
    arm_b_can: str = "can1",
    firmware: str = "auto",
    timeout_s: float = 3.0,
) -> None:
    """Report whether both NERO arms are ready for XRoboToolkit teleoperation.

    Args:
        arm_a_can: SocketCAN channel for arm A.
        arm_b_can: SocketCAN channel for arm B.
        firmware: Driver selector, or "auto" to detect from the reported version.
        timeout_s: Per-arm connection timeout.
    """
    print("NERO preflight (read-only: no enable, no motion)\n")
    blockers: list[str] = []
    for arm_name, channel in (("arm_a", arm_a_can), ("arm_b", arm_b_can)):
        blockers.extend(_check_arm(arm_name, channel, firmware, timeout_s))

    print()
    if not blockers:
        print("READY: both arms have live feedback and no error flags.")
        print("Arming will claim CAN control, enable the motors, and hold position.")
        return
    print("NOT READY -- resolve these before running teleop:")
    for index, blocker in enumerate(blockers, 1):
        print(f"  {index}. {blocker}")
    raise SystemExit(1)


if __name__ == "__main__":
    tyro.cli(main)
