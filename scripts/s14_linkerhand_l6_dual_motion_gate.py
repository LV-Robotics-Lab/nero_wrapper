#!/usr/bin/env python3
"""S14 LinkerHand L6 dual-hand gated motion.

This script is the first bimanual gate after each hand passed the single-hand
SDK health/open/index checks. It reuses the local linkerhand_wrapper API and preset
table, defaults to dry-run, and avoids SDK demos/GUI wrappers.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import threading
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
            f"Refusing to use {can_iface}. This gate is for standalone hand "
            "CAN interfaces, not NERO arm CAN interfaces."
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


def build_poses(args: argparse.Namespace) -> dict[str, dict[str, list[int] | None]]:
    left_base = list(PRESETS[args.preset]["left"])
    right_base = list(PRESETS[args.preset]["right"])
    if args.mode == "open-anchor":
        return {
            "left": {"base": left_base, "target": None},
            "right": {"base": right_base, "target": None},
        }

    joint_index = JOINT_NAMES.index(args.joint)
    left_target = list(left_base)
    right_target = list(right_base)
    left_target[joint_index] = clamp_byte(left_target[joint_index] + args.left_delta)
    right_target[joint_index] = clamp_byte(right_target[joint_index] + args.right_delta)

    if left_target[joint_index] == left_base[joint_index]:
        raise SystemExit("Left requested delta is clamped to no motion.")
    if right_target[joint_index] == right_base[joint_index]:
        raise SystemExit("Right requested delta is clamped to no motion.")

    return {
        "left": {"base": left_base, "target": left_target},
        "right": {"base": right_base, "target": right_target},
    }


def print_plan(args: argparse.Namespace, poses: dict[str, dict[str, list[int] | None]]) -> None:
    print("S14 LinkerHand L6 dual-hand motion gate")
    print(
        f"execute={args.execute} left_can={args.left_can} right_can={args.right_can}"
    )
    print(
        f"mode={args.mode} preset={args.preset} speed={args.speed} torque={args.torque}"
    )
    print(f"left_base_pose={poses['left']['base']}")
    print(f"right_base_pose={poses['right']['base']}")
    if args.mode == "open-anchor":
        print("sequence=send_both_base_poses_once")
    else:
        print(
            f"joint={args.joint} left_delta={args.left_delta} "
            f"right_delta={args.right_delta}"
        )
        print(f"left_target_pose={poses['left']['target']}")
        print(f"right_target_pose={poses['right']['target']}")
        print("sequence=send_both_targets_then_return_both_to_base")


def call_both(label: str, left_fn: Any, right_fn: Any) -> tuple[float, float]:
    left_time = 0.0
    right_time = 0.0
    errors: list[BaseException] = []

    def run_left() -> None:
        nonlocal left_time
        try:
            left_time = time.perf_counter()
            left_fn()
        except BaseException as exc:  # noqa: BLE001 - preserve thread failure.
            errors.append(exc)

    def run_right() -> None:
        nonlocal right_time
        try:
            right_time = time.perf_counter()
            right_fn()
        except BaseException as exc:  # noqa: BLE001 - preserve thread failure.
            errors.append(exc)

    left_thread = threading.Thread(target=run_left, name=f"{label}_left")
    right_thread = threading.Thread(target=run_right, name=f"{label}_right")
    left_thread.start()
    right_thread.start()
    left_thread.join()
    right_thread.join()

    if errors:
        raise RuntimeError(f"{label} failed: {errors[0]}") from errors[0]
    return left_time, right_time


def main() -> int:
    parser = argparse.ArgumentParser(
        description="SDK-backed gated dual-hand motion for LinkerHand L6."
    )
    parser.add_argument("--left-can", default="can1", help="Left hand SocketCAN interface.")
    parser.add_argument("--right-can", default="can2", help="Right hand SocketCAN interface.")
    parser.add_argument("--mode", choices=["open-anchor", "index-micro"], default="open-anchor")
    parser.add_argument("--preset", choices=sorted(PRESETS), default="open")
    parser.add_argument("--joint", choices=JOINT_NAMES, default="index")
    parser.add_argument("--left-delta", type=int, default=-10)
    parser.add_argument("--right-delta", type=int, default=-10)
    parser.add_argument("--speed", type=int, default=30)
    parser.add_argument("--torque", type=int, default=None)
    parser.add_argument("--dwell", type=float, default=1.2)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--allow-arm-can", action="store_true")
    args = parser.parse_args()

    if args.left_can == args.right_can:
        raise SystemExit("--left-can and --right-can must be different interfaces.")
    if not 10 <= args.speed <= 80:
        raise SystemExit("--speed must be in 10..80 for S14 first dual-hand gates.")
    if args.torque is not None and not 0 <= args.torque <= 120:
        raise SystemExit("--torque must be omitted or in 0..120 for S14 first dual-hand gates.")
    if abs(args.left_delta) > 20 or abs(args.right_delta) > 20:
        raise SystemExit("Delta absolute values must be <= 20 for S14 first dual-hand gates.")

    require_can_interface(args.left_can, args.allow_arm_can)
    require_can_interface(args.right_can, args.allow_arm_can)
    poses = build_poses(args)
    print_plan(args, poses)

    if not args.execute:
        print("Dry run only. Add --execute after the S14 dual-hand safety gate is confirmed.")
        return 0

    left_api: LinkerHandApi | None = None
    right_api: LinkerHandApi | None = None
    try:
        left_api = LinkerHandApi(hand_type="left", hand_joint="L6", can=args.left_can)
        right_api = LinkerHandApi(hand_type="right", hand_joint="L6", can=args.right_can)
        time.sleep(0.3)

        left_temp, left_fault, left_current = query_health(left_api)
        right_temp, right_fault, right_current = query_health(right_api)
        print(
            f"pre_left_health temperature={left_temp} "
            f"fault={left_fault} current_raw={left_current}"
        )
        print(
            f"pre_right_health temperature={right_temp} "
            f"fault={right_fault} current_raw={right_current}"
        )
        if any(value != 0 for value in left_fault + right_fault):
            print("REJECTED: nonzero fault before dual-hand motion.")
            return 20

        speed = [args.speed] * 6
        print(f"setting_left_speed={speed}")
        left_api.set_joint_speed(speed)
        print(f"setting_right_speed={speed}")
        right_api.set_joint_speed(speed)
        time.sleep(0.2)

        if args.torque is not None:
            torque = [args.torque] * 6
            print(f"setting_left_torque={torque}")
            left_api.set_torque(torque)
            print(f"setting_right_torque={torque}")
            right_api.set_torque(torque)
            time.sleep(0.2)

        left_base = poses["left"]["base"]
        right_base = poses["right"]["base"]
        left_target = poses["left"]["target"]
        right_target = poses["right"]["target"]

        if left_target is None or right_target is None:
            print(f"sending_left_pose={left_base}")
            print(f"sending_right_pose={right_base}")
            left_t, right_t = call_both(
                "open_anchor",
                lambda: left_api.finger_move(left_base),
                lambda: right_api.finger_move(right_base),
            )
            print(f"send_time_delta_ms={abs(left_t - right_t) * 1000.0:.3f}")
            time.sleep(args.dwell)
        else:
            print(f"sending_left_target_pose={left_target}")
            print(f"sending_right_target_pose={right_target}")
            left_t, right_t = call_both(
                "target",
                lambda: left_api.finger_move(left_target),
                lambda: right_api.finger_move(right_target),
            )
            print(f"target_send_time_delta_ms={abs(left_t - right_t) * 1000.0:.3f}")
            time.sleep(args.dwell)
            print(f"returning_left_to_base_pose={left_base}")
            print(f"returning_right_to_base_pose={right_base}")
            left_t, right_t = call_both(
                "return",
                lambda: left_api.finger_move(left_base),
                lambda: right_api.finger_move(right_base),
            )
            print(f"return_send_time_delta_ms={abs(left_t - right_t) * 1000.0:.3f}")
            time.sleep(args.dwell)

        left_temp, left_fault, left_current = query_health(left_api)
        right_temp, right_fault, right_current = query_health(right_api)
        print(
            f"post_left_health temperature={left_temp} "
            f"fault={left_fault} current_raw={left_current}"
        )
        print(
            f"post_right_health temperature={right_temp} "
            f"fault={right_fault} current_raw={right_current}"
        )
        if any(value != 0 for value in left_fault + right_fault):
            print("REJECTED: nonzero fault after dual-hand motion.")
            return 21

        print("S14 dual-hand SDK motion gate completed.")
        return 0
    finally:
        if left_api is not None:
            close_sdk_bus(left_api)
        if right_api is not None:
            close_sdk_bus(right_api)


if __name__ == "__main__":
    raise SystemExit(main())
