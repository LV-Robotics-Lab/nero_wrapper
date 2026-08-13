"""Raise NERO joint4 to a target angle over CAN, with an FK report.

Two stages, and the first one never touches a motor:

    # 1. dry run: connect read-only, report joints + FK for the planned pose
    python scripts/hardware/nero_move_joint4.py

    # 2. live: enable the motors and ramp joint4 in bounded steps
    python scripts/hardware/nero_move_joint4.py --execute --live-confirmation MOVE_NERO

After arriving, the arms stay enabled and hold the pose until Ctrl-C, so the
rig can be inspected or handed to another process without the elbow dropping.
Pass --no-hold to exit and disable immediately instead.

Motion goes through NeroArmInterface.move_to_pose, so the per-command joint
step bound, the joint-limit margin and the ctrl_mode/arm_status gating are the
same ones teleoperation uses. Only joint4 is commanded; the other six joints
are held at 0 rad, which is where the bench pose expects them.

FK is reported from three independent sources -- the official URDF through
placo, the SDK's modified-DH table, and the arm's own 0x2A2-0x2A4 flange-pose
feedback. They agree on healthy hardware; a mismatch means the joint feedback
or the model is wrong, so the script reports it instead of quietly moving.
"""

from __future__ import annotations

import math
import time
from typing import Literal

import numpy as np
import tyro

from xrobotoolkit_teleop.hardware.interface.nero import (
    NERO_JOINT_LIMITS,
    NeroArmInterface,
    NeroSafetyError,
    status_error_flags,
)
from xrobotoolkit_teleop.hardware.nero_fk import (
    NeroForwardKinematics,
    sdk_flange_pose,
)

LIVE_CONFIRMATION = "MOVE_NERO"
ARM_ORDER = ("arm_a", "arm_b")


def _format_joints(joints) -> str:
    return "[" + ", ".join(f"{math.degrees(float(v)):7.2f}" for v in joints) + "] deg"


def _format_pose(pose) -> str:
    values = np.asarray(pose, dtype=np.float64)
    return (
        f"xyz [{values[0]:+.4f} {values[1]:+.4f} {values[2]:+.4f}] m  "
        f"rpy [{math.degrees(values[3]):+7.2f} {math.degrees(values[4]):+7.2f} "
        f"{math.degrees(values[5]):+7.2f}] deg"
    )


def _report_fk(fk: NeroForwardKinematics, arm_name: str, joints, can_pose) -> None:
    """Print the three FK sources for one measured joint vector."""
    print(f"    joints         {_format_joints(joints)}")
    print(f"    URDF FK        {_format_pose(fk.flange_pose(arm_name, joints))}")
    print(f"    SDK MDH FK     {_format_pose(sdk_flange_pose(joints))}")
    if can_pose is not None:
        print(f"    CAN 0x2A2-4    {_format_pose(can_pose)}")
        print(f"    URDF vs CAN    {fk.compare_to_pose(arm_name, joints, can_pose).describe()}")
    print(f"    URDF vs SDK    {fk.compare_to_sdk(arm_name, joints).describe()}")


def _hold_until_interrupt(
    interfaces: list[NeroArmInterface],
    *,
    hold_rate_hz: float,
    status_period_s: float,
) -> None:
    """Keep the arms enabled at their arrival pose until Ctrl-C.

    Each cycle re-commands the pose that was latched on arrival rather than the
    currently measured pose. Re-commanding the measured pose would let the arm
    ratchet downward: this arm has no mechanical brakes, so any gravity sag
    between cycles would become the new target and accumulate. Steps stay inside
    the interface's per-command bound, so the loop corrects sag instead of
    following it, and it can never move faster than teleoperation would.
    """
    period = 1.0 / hold_rate_hz
    latched = {interface.arm_name: interface.read_state().joints.copy() for interface in interfaces}
    print(
        f"\nHOLDING at {hold_rate_hz:.0f} Hz. The arms stay enabled at this pose. "
        "Press Ctrl-C to disable and exit."
    )
    last_status = 0.0
    try:
        while True:
            tick = time.monotonic()
            for interface in interfaces:
                goal = latched[interface.arm_name]
                measured = interface.read_state().joints
                bound = interface.max_joint_step_rad * (1.0 - 1e-9)
                step = np.clip(goal - measured, -bound, bound)
                interface.command(measured + step)
            if status_period_s > 0.0 and tick - last_status >= status_period_s:
                last_status = tick
                for interface in interfaces:
                    state = interface.read_state()
                    drift = float(np.max(np.abs(state.joints - latched[interface.arm_name])))
                    print(
                        f"  holding {interface.arm_name}: {_format_joints(state.joints)} "
                        f"max drift {math.degrees(drift):.3f} deg"
                    )
            time.sleep(max(0.0, period - (time.monotonic() - tick)))
    except KeyboardInterrupt:
        print("\nCtrl-C received. Holding position, then disabling both arms...")


def main(
    arm_a_can: str = "can0",
    arm_b_can: str = "can1",
    arms: Literal["arm_a", "arm_b", "both"] = "both",
    joint4_deg: float = 90.0,
    firmware: Literal["auto", "default", "v111", "v112", "v120"] = "v112",
    speed_percent: int = 5,
    max_joint_step_deg: float = 0.75,
    timeout_s: float = 120.0,
    execute: bool = False,
    hold: bool = True,
    hold_rate_hz: float = 10.0,
    status_period_s: float = 2.0,
    live_confirmation: str = "",
) -> None:
    """Report FK and, with --execute, ramp joint4 to joint4_deg over CAN.

    Args:
        arm_a_can: SocketCAN interface for arm A.
        arm_b_can: SocketCAN interface for arm B.
        arms: Which arm or arms to move.
        joint4_deg: Hardware joint4 target in degrees (limit is -58..+123).
        firmware: pyAgxArm driver selector, or auto to detect per arm.
        speed_percent: SDK motion speed; the interface restricts this to 1..5.
        max_joint_step_deg: Largest joint change accepted in one CAN command.
        timeout_s: Per-arm ramp timeout.
        execute: Enable the motors and send motion. Off by default.
        hold: After arriving, keep the arms enabled and holding until Ctrl-C.
        hold_rate_hz: Rate of the position-hold refresh during the hold loop.
        status_period_s: How often the hold loop prints joint angles.
        live_confirmation: Must equal MOVE_NERO when --execute is set.
    """
    if arm_a_can == arm_b_can:
        raise SystemExit("arm_a_can and arm_b_can must differ; both NERO arms use the same CAN IDs")
    if execute and live_confirmation != LIVE_CONFIRMATION:
        raise SystemExit(
            "Live output was not confirmed. Re-run the dry run first, then add "
            f"--live-confirmation {LIVE_CONFIRMATION}"
        )
    target_rad = math.radians(joint4_deg)
    lower, upper = NERO_JOINT_LIMITS[3]
    if not lower < target_rad < upper:
        raise SystemExit(
            f"joint4_deg={joint4_deg} is outside the joint4 limit "
            f"[{math.degrees(lower):.1f}, {math.degrees(upper):.1f}] deg"
        )
    if joint4_deg == 0.0:
        print(
            "WARNING: joint4=0 is the straight-elbow wrist singularity "
            "(arm_status=3). Cartesian IK is ill-conditioned there."
        )
    if hold_rate_hz <= 0.0:
        raise SystemExit("hold_rate_hz must be positive")
    if status_period_s < 0.0:
        raise SystemExit("status_period_s must be non-negative")

    selected = ARM_ORDER if arms == "both" else (arms,)
    channels = {"arm_a": arm_a_can, "arm_b": arm_b_can}
    goal = np.zeros(7)
    goal[3] = target_rad

    print(f"NERO joint4 move: target {joint4_deg:.1f} deg on {', '.join(selected)}")
    print(f"mode: {'EXECUTE (motors will be enabled)' if execute else 'DRY RUN (read-only)'}")
    print("FK: URDF/placo vs SDK MDH vs CAN flange feedback, in each arm base_link frame\n")

    fk = NeroForwardKinematics()
    print("planned pose (offline FK, no hardware needed):")
    for arm_name in selected:
        print(f"  {arm_name}:")
        _report_fk(fk, arm_name, goal, None)
    print()

    interfaces: dict[str, NeroArmInterface] = {}
    failures: list[str] = []
    try:
        for arm_name in selected:
            interface = NeroArmInterface(
                arm_name=arm_name,
                channel=channels[arm_name],
                firmware=firmware,
                execute=execute,
                speed_percent=speed_percent,
                max_joint_step_rad=math.radians(max_joint_step_deg),
            )
            interfaces[arm_name] = interface
            state = interface.connect()
            print(f"  {interface.describe_status()}")
            flags = status_error_flags(state.status)
            if flags:
                raise NeroSafetyError(f"{arm_name} status error flags: {', '.join(flags)}")
            print(f"  {arm_name} measured now:")
            _report_fk(fk, arm_name, state.joints, interface.get_flange_pose())
            print()

        if not execute:
            print("Dry run complete. No motor was enabled and no motion was sent.")
            print(
                "To move, re-run with: --execute --live-confirmation "
                f"{LIVE_CONFIRMATION}"
            )
            return

        for arm_name in selected:
            interface = interfaces[arm_name]
            print(f"  arming {arm_name} (0x151 CAN control mode, 0x471 enable all joints)...")
            interface.arm()
            print(f"  ramping {arm_name} joint4 to {joint4_deg:.1f} deg...")
            measured = interface.move_to_pose(goal, timeout_s=timeout_s)
            print(f"  {arm_name} arrived:")
            _report_fk(fk, arm_name, measured, interface.get_flange_pose())
            interface.hold()
            print()
        print(f"Both stages done. joint4 is at {joint4_deg:.1f} deg and each arm is holding position.")
        if not hold:
            print("Exiting now; --no-hold was set, so the arms will be disabled on shutdown.")
            return
        _hold_until_interrupt(
            [interfaces[arm_name] for arm_name in selected],
            hold_rate_hz=hold_rate_hz,
            status_period_s=status_period_s,
        )
    except NeroSafetyError as exc:
        raise SystemExit(f"NERO safety stop: {exc}") from exc
    finally:
        for arm_name, interface in interfaces.items():
            try:
                interface.close(hold_if_armed=execute, disable_if_armed=True)
            except Exception as exc:  # keep closing the remaining arms
                failures.append(f"{arm_name}: {exc}")
        if failures:
            print("shutdown warnings: " + "; ".join(failures))


if __name__ == "__main__":
    tyro.cli(main)
