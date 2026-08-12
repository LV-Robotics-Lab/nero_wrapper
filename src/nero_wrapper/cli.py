"""Console entry points for read-only NERO wrapper operations."""

from __future__ import annotations

import argparse
import json
import sys

from .config import NeroConfig
from .doctor import inspect_can_interfaces, inspect_commands
from .sdk import NeroArm, NeroSdkUnavailable


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)


def config_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Print validated, non-secret NERO configuration.")
    parser.parse_args(argv)
    try:
        config = NeroConfig.from_env()
    except ValueError as exc:
        print(f"configuration error: {exc}", file=sys.stderr)
        return 2
    print(_json(config.as_dict()))
    return 0


def doctor_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run read-only NERO host and CAN checks.")
    parser.add_argument("--skip-can", action="store_true", help="Skip SocketCAN inspection.")
    args = parser.parse_args(argv)
    try:
        config = NeroConfig.from_env()
    except ValueError as exc:
        print(f"configuration error: {exc}", file=sys.stderr)
        return 2

    checks = inspect_commands()
    if not args.skip_can:
        checks.extend(inspect_can_interfaces(config))
    for check in checks:
        print(f"[{'OK' if check.ok else 'FAIL'}] {check.name}: {check.detail}")
    return 0 if all(check.ok for check in checks) else 1


def read_state_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Read NERO arm state without enabling or moving it."
    )
    parser.add_argument("--arm", choices=("arm_a", "arm_b"), default="arm_a")
    parser.add_argument("--timeout", type=float, default=5.0)
    parser.add_argument("--poll-period", type=float, default=0.05)
    parser.add_argument(
        "--connect",
        action="store_true",
        help="Connect to the configured SocketCAN channel. Without this, print config only.",
    )
    args = parser.parse_args(argv)

    try:
        config = NeroConfig.from_env()
    except ValueError as exc:
        print(f"configuration error: {exc}", file=sys.stderr)
        return 2
    endpoint = config.arm(args.arm)
    print(_json({"arm": endpoint.name, "channel": endpoint.channel, "firmware": config.firmware}))
    if not args.connect:
        print("Dry run only. Add --connect after the CAN interface is active.")
        return 0

    try:
        with NeroArm(endpoint, config=config) as arm:
            snapshot = arm.wait_for_snapshot(timeout=args.timeout, poll_period=args.poll_period)
    except (NeroSdkUnavailable, RuntimeError, TimeoutError, ValueError) as exc:
        print(f"state read failed: {exc}", file=sys.stderr)
        return 1
    print(_json(snapshot.as_dict()))
    return 0


if __name__ == "__main__":
    raise SystemExit(config_main())
