#!/usr/bin/env python3
"""S14 LinkerHand L6 SDK-backed identity and health check.

This script intentionally avoids SDK calls that may command motion on the live
bench device: get_state(), get_torque(), finger_move(), and demo wrappers.
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

if str(SDK_API_ROOT) not in sys.path:
    sys.path.insert(0, str(SDK_API_ROOT))

try:
    from linker_hand_api import LinkerHandApi  # type: ignore
except ImportError as exc:
    raise SystemExit(
        "Failed to import linker_hand_api from upstream/linkerhand_wrapper. "
        "Run this with .venv/nero-sdk/bin/python from the project root."
    ) from exc


def run_checked(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, check=False, text=True, capture_output=True)


def require_can_interface(can_iface: str, allow_arm_can: bool) -> None:
    if can_iface.startswith("can_arm_") and not allow_arm_can:
        raise SystemExit(
            f"Refusing to use {can_iface}. This health check is for the "
            "standalone hand CAN bus, not the NERO arm CAN interfaces."
        )

    result = run_checked(["ip", "-details", "link", "show", can_iface])
    if result.returncode != 0:
        print(result.stderr.strip(), file=sys.stderr)
        raise SystemExit(f"CAN interface {can_iface!r} does not exist.")

    print("CAN interface:")
    print(result.stdout.rstrip())
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


def main() -> int:
    parser = argparse.ArgumentParser(
        description="SDK-backed LinkerHand L6 identity/health check."
    )
    parser.add_argument("--can", default="can1", help="SocketCAN interface.")
    parser.add_argument("--side", choices=["left", "right"], default="left")
    parser.add_argument("--samples", type=int, default=3)
    parser.add_argument("--allow-arm-can", action="store_true")
    args = parser.parse_args()

    if args.samples < 1:
        raise SystemExit("--samples must be >= 1")

    print("S14 LinkerHand L6 SDK health check", flush=True)
    print(f"side={args.side} can={args.can} samples={args.samples}", flush=True)
    print("safety=no_get_state no_get_torque no_finger_move", flush=True)
    require_can_interface(args.can, args.allow_arm_can)

    api: LinkerHandApi | None = None
    try:
        api = LinkerHandApi(hand_type=args.side, hand_joint="L6", can=args.can)
        time.sleep(0.3)

        print(f"hand_id=0x{api.hand_id:02X}", flush=True)
        print(f"serial={getattr(api, 'serial_number', '<unknown>')}", flush=True)
        print(f"embedded_version_raw={getattr(api.hand, 'version', None)}", flush=True)

        all_faults: list[list[int]] = []
        for index in range(1, args.samples + 1):
            temperature, fault, current = query_health(api)
            all_faults.append(fault)
            print(
                f"sample={index} "
                f"temperature={temperature} fault={fault} current_raw={current}",
                flush=True,
            )
            time.sleep(0.2)

        if any(any(value != 0 for value in fault) for fault in all_faults):
            print("REJECTED: nonzero LinkerHand fault code observed.", flush=True)
            return 20

        print("ACCEPTED: SDK identity/health responses are present; faults are zero.", flush=True)
        return 0
    finally:
        if api is not None:
            close_sdk_bus(api)


if __name__ == "__main__":
    raise SystemExit(main())
