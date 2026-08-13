"""Clear a latched NERO EMERGENCY_STOP so the arms can be armed again.

An arm that was disabled while raised sags to its mechanical rest and the
controller latches arm_status=1/EMERGENCY_STOP. Nothing in the normal arm() or
teleop path clears that, on purpose: the recovery frame (0x150 Byte0=2, the
SDK's reset()) exits joint damping, and this arm has no mechanical brakes, so
sending it to a RAISED arm makes it fall immediately.

This script exists to do that recovery deliberately rather than as a side effect
of arming. It refuses to run unless each arm already looks like it is resting,
and it never enables a motor -- run the joint4 move or teleop afterwards to arm.

    # 1. inspect: read status and joint angles, decide nothing
    python scripts/hardware/nero_clear_estop.py

    # 2. clear: send the damping-exit frame to arms that are resting
    python scripts/hardware/nero_clear_estop.py --execute --live-confirmation CLEAR_ESTOP
"""

from __future__ import annotations

import math
import time
from typing import Literal

import numpy as np
import tyro

from xrobotoolkit_teleop.hardware.interface.nero import (
    NERO_ARM_STATUS_EMERGENCY_STOP,
    NeroArmInterface,
    NeroSafetyError,
    _enum_value,
    status_error_flags,
)

LIVE_CONFIRMATION = "CLEAR_ESTOP"
ARM_ORDER = ("arm_a", "arm_b")

# A resting NERO has every joint near zero. joint4 is the one that matters: it
# is the elbow, it carries the forearm's weight, and it is what the startup pose
# raises to 90 degrees. If it is still lifted, exiting damping drops it.
RESTING_JOINT4_LIMIT_DEG = 15.0
RESTING_ANY_JOINT_LIMIT_DEG = 30.0


def _format_joints(joints) -> str:
    return "[" + ", ".join(f"{math.degrees(float(v)):7.2f}" for v in joints) + "] deg"


def _resting_blockers(arm_name: str, joints: np.ndarray) -> list[str]:
    """Reasons this arm does not look safe to exit damping from."""
    blockers = []
    joint4_deg = abs(math.degrees(float(joints[3])))
    if joint4_deg > RESTING_JOINT4_LIMIT_DEG:
        blockers.append(
            f"{arm_name}: joint4 (elbow) is at {math.degrees(float(joints[3])):.1f} deg, "
            f"more than {RESTING_JOINT4_LIMIT_DEG:.0f} deg from rest -- it will FALL"
        )
    worst = int(np.argmax(np.abs(joints)))
    worst_deg = abs(math.degrees(float(joints[worst])))
    if worst_deg > RESTING_ANY_JOINT_LIMIT_DEG:
        blockers.append(
            f"{arm_name}: joint{worst + 1} is at {math.degrees(float(joints[worst])):.1f} deg, "
            f"more than {RESTING_ANY_JOINT_LIMIT_DEG:.0f} deg from rest"
        )
    return blockers


def main(
    arm_a_can: str = "can0",
    arm_b_can: str = "can1",
    arms: Literal["arm_a", "arm_b", "both"] = "both",
    firmware: Literal["auto", "default", "v111", "v112", "v120"] = "auto",
    execute: bool = False,
    force: bool = False,
    live_confirmation: str = "",
) -> None:
    """Report, and with --execute clear, a latched EMERGENCY_STOP.

    Args:
        arm_a_can: SocketCAN interface for arm A.
        arm_b_can: SocketCAN interface for arm B.
        arms: Which arm or arms to act on.
        firmware: pyAgxArm driver selector, or auto to detect per arm.
        execute: Send the damping-exit frame. Off by default.
        force: Skip the resting-pose check. Only with the arm physically supported.
        live_confirmation: Must equal CLEAR_ESTOP when --execute is set.
    """
    if arm_a_can == arm_b_can:
        raise SystemExit("arm_a_can and arm_b_can must differ; both NERO arms use the same CAN IDs")
    if execute and live_confirmation != LIVE_CONFIRMATION:
        raise SystemExit(
            "Clearing the emergency stop was not confirmed. Inspect first, then add "
            f"--live-confirmation {LIVE_CONFIRMATION}"
        )

    selected = ARM_ORDER if arms == "both" else (arms,)
    channels = {"arm_a": arm_a_can, "arm_b": arm_b_can}
    print("NERO emergency-stop recovery")
    print(f"mode: {'EXECUTE (0x150 damping exit)' if execute else 'INSPECT (read-only)'}\n")

    interfaces: dict[str, NeroArmInterface] = {}
    try:
        latched: list[str] = []
        blockers: list[str] = []
        for arm_name in selected:
            interface = NeroArmInterface(
                arm_name=arm_name,
                channel=channels[arm_name],
                firmware=firmware,
                # Clearing is not motion, and keeping this read-only guarantees
                # no code path here can enable a motor.
                execute=False,
            )
            interfaces[arm_name] = interface
            state = interface.connect()
            time.sleep(1.0)  # let the SDK rate estimator warm up
            print(f"  {interface.describe_status()}")
            print(f"    joints {_format_joints(state.joints)}")

            flags = status_error_flags(state.status)
            if flags:
                blockers.append(f"{arm_name}: status error flags {', '.join(flags)}")
            message = getattr(state.status, "msg", None)
            arm_status = _enum_value(getattr(message, "arm_status", None))
            if arm_status == NERO_ARM_STATUS_EMERGENCY_STOP:
                latched.append(arm_name)
                arm_blockers = _resting_blockers(arm_name, state.joints)
                for blocker in arm_blockers:
                    print(f"    UNSAFE: {blocker}")
                blockers.extend(arm_blockers)
            else:
                print("    not latched in EMERGENCY_STOP; nothing to clear")
            print()

        if not latched:
            print("No arm is latched in EMERGENCY_STOP. Nothing to do.")
            return
        print(f"latched in EMERGENCY_STOP: {', '.join(latched)}")

        if blockers and not force:
            print("\nREFUSING to clear -- the arm would drop:")
            for index, blocker in enumerate(blockers, 1):
                print(f"  {index}. {blocker}")
            print(
                "\nSupport the arm by hand or lower it before clearing. To override "
                "with the arm physically supported, add --force."
            )
            raise SystemExit(1)
        if blockers and force:
            print("\n--force set: clearing despite the checks above. The arm WILL drop if unsupported.")

        if not execute:
            print(
                "\nInspect complete. No frame was sent. To clear, re-run with: "
                f"--execute --live-confirmation {LIVE_CONFIRMATION}"
            )
            return

        for arm_name in latched:
            print(f"  clearing {arm_name} (0x150 Byte0=2, exit damping)...")
            interfaces[arm_name].clear_emergency_stop()
        time.sleep(0.5)

        print()
        remaining = []
        for arm_name in latched:
            interface = interfaces[arm_name]
            print(f"  {interface.describe_status()}")
            message = getattr(interface.read_state().status, "msg", None)
            if _enum_value(getattr(message, "arm_status", None)) == NERO_ARM_STATUS_EMERGENCY_STOP:
                remaining.append(arm_name)
        print()
        if remaining:
            print(f"Still latched: {', '.join(remaining)}.")
            print(
                "A physical emergency stop or safety-chain break cannot be cleared over CAN. "
                "Check the hardware stop, then power-cycle the controller with the arm supported."
            )
            raise SystemExit(1)
        print("EMERGENCY_STOP cleared. The motors are still disabled.")
        print("Arm them by running the joint4 move or teleop, which re-sends 0x471 as required.")
    except NeroSafetyError as exc:
        raise SystemExit(f"NERO safety stop: {exc}") from exc
    finally:
        for arm_name, interface in interfaces.items():
            try:
                interface.close(hold_if_armed=False, disable_if_armed=False)
            except Exception as exc:
                print(f"{arm_name} shutdown warning: {exc}")


if __name__ == "__main__":
    tyro.cli(main)
