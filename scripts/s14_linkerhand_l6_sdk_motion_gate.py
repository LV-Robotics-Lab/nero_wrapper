#!/usr/bin/env python3
"""S14 LinkerHand L6 SDK-backed gated first motion.

The script reuses the local linkerhand_wrapper API and L6 preset table, but avoids
the SDK demos and wrapper context managers because they can issue larger or
implicit motion commands.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
SDK_ROOT = REPO_ROOT / "upstream" / "linkerhand_wrapper"
LEGACY_SDK_ROOT = REPO_ROOT / "upstream" / ("linkerhand_" + "sdk")
if not SDK_ROOT.exists() and LEGACY_SDK_ROOT.exists():
    SDK_ROOT = LEGACY_SDK_ROOT
SDK_API_ROOT = SDK_ROOT / "LinkerHand"

for path in (SDK_ROOT, SDK_API_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

try:
    from linker_hand_api import LinkerHandApi  # type: ignore
    from linker_hand_l6 import JOINT_NAMES, PRESETS  # type: ignore
except ImportError as exc:
    raise SystemExit(
        "Failed to import local linkerhand_wrapper modules. "
        "Run this with .venv/nero-sdk/bin/python from the project root."
    ) from exc


def run_checked(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, check=False, text=True, capture_output=True)


def require_can_interface(can_iface: str, allow_arm_can: bool) -> None:
    if can_iface.startswith("can_arm_") and not allow_arm_can:
        raise SystemExit(
            f"Refusing to use {can_iface}. This motion gate is for the "
            "standalone hand CAN bus, not the NERO arm CAN interfaces."
        )

    result = run_checked(["ip", "-details", "link", "show", can_iface])
    if result.returncode != 0:
        print(result.stderr.strip(), file=sys.stderr)
        raise SystemExit(f"CAN interface {can_iface!r} does not exist.")

    if "state UP" not in result.stdout and "<NOARP,UP" not in result.stdout:
        raise SystemExit(
            f"CAN interface {can_iface!r} is not UP. Activate it first, e.g. "
            f"`sudo ip link set {can_iface} up type can bitrate 1000000`."
        )


def as_int_list(value: Any, width: int = 6) -> list[int]:
    if value is None:
        return []
    items = list(value)
    return [int(v) for v in items[:width]]


def close_sdk_bus(api: LinkerHandApi) -> None:
    hand = getattr(api, "hand", None)
    if hand is None:
        return
    setattr(hand, "running", False)
    receive_thread = getattr(hand, "receive_thread", None)
    if receive_thread is not None and receive_thread.is_alive():
        receive_thread.join(timeout=2.0)
    bus = getattr(hand, "bus", None)
    if bus is not None:
        try:
            bus.shutdown()
        except Exception:
            pass


def query_health(api: LinkerHandApi) -> tuple[list[int], list[int], list[int]]:
    api.get_temperature()
    time.sleep(0.08)
    temperature = as_int_list(getattr(api.hand, "x33", []))

    api.get_fault()
    time.sleep(0.08)
    fault = as_int_list(getattr(api.hand, "x35", []))

    api.get_current()
    time.sleep(0.08)
    current = as_int_list(getattr(api.hand, "x36", []))

    return temperature, fault, current


def clamp_byte(value: int) -> int:
    return max(0, min(255, int(value)))


def pose_for(args: argparse.Namespace) -> tuple[list[int], list[int] | None]:
    base = list(PRESETS[args.preset][args.side])
    if args.mode == "open-anchor":
        return base, None

    joint_index = JOINT_NAMES.index(args.joint)
    target = list(base)
    target[joint_index] = clamp_byte(target[joint_index] + args.delta)
    if target[joint_index] == base[joint_index]:
        raise SystemExit("Requested delta is clamped to no motion; choose a smaller/larger delta.")
    return base, target


def print_plan(args: argparse.Namespace, base: list[int], target: list[int] | None) -> None:
    print("S14 LinkerHand L6 SDK motion gate")
    print(f"execute={args.execute} side={args.side} can={args.can}")
    print(f"mode={args.mode} preset={args.preset} speed={args.speed} torque={args.torque}")
    print(f"base_pose={base}")
    if target is not None:
        print(f"joint={args.joint} delta={args.delta} target_pose={target}")
        print("sequence=target_pose_then_return_to_base_pose")
    else:
        print("sequence=send_base_pose_once")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="SDK-backed gated first motion for LinkerHand L6."
    )
    parser.add_argument("--can", default="can1", help="SocketCAN interface.")
    parser.add_argument("--side", choices=["left", "right"], default="left")
    parser.add_argument("--mode", choices=["open-anchor", "index-micro"], default="open-anchor")
    parser.add_argument("--preset", choices=sorted(PRESETS), default="open")
    parser.add_argument("--joint", choices=JOINT_NAMES, default="index")
    parser.add_argument("--delta", type=int, default=-10)
    parser.add_argument("--speed", type=int, default=30)
    parser.add_argument("--torque", type=int, default=None)
    parser.add_argument("--dwell", type=float, default=1.2)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--allow-arm-can", action="store_true")
    args = parser.parse_args()

    if not 10 <= args.speed <= 80:
        raise SystemExit("--speed must be in 10..80 for S14 first-motion gates.")
    if args.torque is not None and not 0 <= args.torque <= 120:
        raise SystemExit("--torque must be omitted or in 0..120 for S14 first-motion gates.")
    if abs(args.delta) > 20:
        raise SystemExit("--delta absolute value must be <= 20 for S14 first-motion gates.")

    require_can_interface(args.can, args.allow_arm_can)
    base, target = pose_for(args)
    print_plan(args, base, target)

    if not args.execute:
        print("Dry run only. Add --execute after the S14 safety gate is confirmed.")
        return 0

    api: LinkerHandApi | None = None
    try:
        api = LinkerHandApi(hand_type=args.side, hand_joint="L6", can=args.can)
        time.sleep(0.3)

        temperature, fault, current = query_health(api)
        print(f"pre_health temperature={temperature} fault={fault} current_raw={current}")
        if any(value != 0 for value in fault):
            print("REJECTED: nonzero fault before motion.")
            return 20

        speed = [args.speed] * 6
        print(f"setting_speed={speed}")
        api.set_joint_speed(speed)
        time.sleep(0.2)

        if args.torque is not None:
            torque = [args.torque] * 6
            print(f"setting_torque={torque}")
            api.set_torque(torque)
            time.sleep(0.2)

        if target is None:
            print(f"sending_pose={base}")
            api.finger_move(base)
            time.sleep(args.dwell)
        else:
            print(f"sending_target_pose={target}")
            api.finger_move(target)
            time.sleep(args.dwell)
            print(f"returning_to_base_pose={base}")
            api.finger_move(base)
            time.sleep(args.dwell)

        temperature, fault, current = query_health(api)
        print(f"post_health temperature={temperature} fault={fault} current_raw={current}")
        if any(value != 0 for value in fault):
            print("REJECTED: nonzero fault after motion.")
            return 21

        print("S14 SDK motion gate completed.")
        return 0
    finally:
        if api is not None:
            close_sdk_bus(api)


if __name__ == "__main__":
    raise SystemExit(main())
