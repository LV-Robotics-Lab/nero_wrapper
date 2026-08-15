#!/usr/bin/env python3
"""S15 coordinated NERO arm + LinkerHand L6 sequence.

Run inside the ROS2 Humble container after the S15 observation session is
started. The script controls NERO arms through ROS topics and LinkerHand L6
hands through the local SDK. It defaults to dry-run and refuses large or
full-fist motions unless the operator supplies explicit safety confirmations.
"""

from __future__ import annotations

import argparse
import math
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import JointState
from std_srvs.srv import Empty

try:
    from agx_arm_msgs.msg import AgxArmStatus
except Exception:  # pragma: no cover - only used inside the ROS container
    AgxArmStatus = None


REPO_ROOT = Path(__file__).resolve().parents[1]
SDK_ROOT = REPO_ROOT / "upstream" / "linkerhand_wrapper"
LEGACY_SDK_ROOT = REPO_ROOT / "upstream" / ("linkerhand_" + "sdk")
if not SDK_ROOT.exists() and LEGACY_SDK_ROOT.exists():
    SDK_ROOT = LEGACY_SDK_ROOT
SDK_API_ROOT = SDK_ROOT / "LinkerHand"
for sdk_path in (SDK_ROOT, SDK_API_ROOT):
    if str(sdk_path) not in sys.path:
        sys.path.insert(0, str(sdk_path))

try:
    from linker_hand_api import LinkerHandApi  # type: ignore
    from linker_hand_l6 import PRESETS  # type: ignore
except ImportError as exc:  # pragma: no cover - validated in the real container
    raise SystemExit(
        "Failed to import local linkerhand_wrapper modules. "
        "Run this script inside the project Humble container."
    ) from exc


ARMS = ("arm_a", "arm_b")
SIDES = ("left", "right")
SIDE_TO_ARM = {"left": "arm_b", "right": "arm_a"}
ARM_TO_SIDE = {"arm_b": "left", "arm_a": "right"}
SIDE_TO_CAN_DEFAULT = {"left": "can1", "right": "can2"}
JOINT_TARGETS = ("joint1", "joint2", "joint3")
JOINT_LIMITS_DEG = {
    "joint1": (-157.0, 157.0),
    "joint2": (-15.0, 190.0),
    "joint3": (-160.0, 160.0),
    "joint4": (-60.0, 125.0),
    "joint5": (-160.0, 160.0),
    "joint6": (-43.0, 58.0),
    "joint7": (-90.0, 90.0),
}


@dataclass
class Sample:
    names: list[str]
    positions: list[float]
    stamp: float


class S15SafetyError(RuntimeError):
    pass


class S15ArmHandNode(Node):
    def __init__(self, arm_a_ns: str, arm_b_ns: str) -> None:
        super().__init__("nero_s15_arm_hand_sequence")
        self.namespaces = {
            "arm_a": arm_a_ns.strip("/"),
            "arm_b": arm_b_ns.strip("/"),
        }
        self.samples: dict[str, Sample | None] = {arm: None for arm in ARMS}
        self.statuses: dict[str, object | None] = {arm: None for arm in ARMS}
        self._move_publishers = {}
        self._estop_clients = {}

        for arm, ns in self.namespaces.items():
            prefix = f"/{ns}" if ns else ""
            self.create_subscription(
                JointState,
                f"{prefix}/feedback/joint_states",
                self._make_joint_cb(arm),
                1,
            )
            if AgxArmStatus is not None:
                self.create_subscription(
                    AgxArmStatus,
                    f"{prefix}/feedback/arm_status",
                    self._make_status_cb(arm),
                    1,
                )
            self._move_publishers[arm] = self.create_publisher(
                JointState, f"{prefix}/control/move_j", 1
            )
            self._estop_clients[arm] = self.create_client(Empty, f"{prefix}/emergency_stop")

    def _make_joint_cb(self, arm: str):
        def cb(msg: JointState) -> None:
            if len(msg.name) == len(msg.position) and len(msg.position) >= 7:
                self.samples[arm] = Sample(list(msg.name), list(msg.position), time.monotonic())

        return cb

    def _make_status_cb(self, arm: str):
        def cb(msg) -> None:
            self.statuses[arm] = msg

        return cb

    def wait_samples(self, timeout: float) -> dict[str, Sample]:
        deadline = time.monotonic() + timeout
        while rclpy.ok() and time.monotonic() < deadline:
            rclpy.spin_once(self, timeout_sec=0.05)
            if all(self.samples[arm] is not None for arm in ARMS):
                return {arm: self.samples[arm] for arm in ARMS}  # type: ignore[return-value]
        missing = [arm for arm in ARMS if self.samples[arm] is None]
        raise TimeoutError(f"No valid joint feedback for {missing} within {timeout:.1f}s")

    def spin_for_status(self, seconds: float) -> None:
        deadline = time.monotonic() + seconds
        while rclpy.ok() and time.monotonic() < deadline:
            rclpy.spin_once(self, timeout_sec=0.05)

    def publish_targets(
        self,
        active_arms: list[str],
        names: dict[str, list[str]],
        targets: dict[str, list[float]],
        repeats: int = 3,
    ) -> None:
        msgs = {}
        for arm in active_arms:
            msg = JointState()
            msg.name = names[arm]
            msg.position = targets[arm]
            msgs[arm] = msg

        for _ in range(max(1, repeats)):
            stamp = self.get_clock().now().to_msg()
            for arm in active_arms:
                msgs[arm].header.stamp = stamp
                self._move_publishers[arm].publish(msgs[arm])
            rclpy.spin_once(self, timeout_sec=0.05)
            time.sleep(0.05)

    def command_subscription_counts(self) -> dict[str, int]:
        return {
            arm: self._move_publishers[arm].get_subscription_count()
            for arm in ARMS
        }

    def wait_command_subscribers(self, active_arms: list[str], timeout: float) -> dict[str, int]:
        deadline = time.monotonic() + timeout
        counts = self.command_subscription_counts()
        while rclpy.ok() and time.monotonic() < deadline:
            if all(counts[arm] > 0 for arm in active_arms):
                return counts
            rclpy.spin_once(self, timeout_sec=0.05)
            counts = self.command_subscription_counts()
        missing = {arm: counts[arm] for arm in active_arms if counts[arm] <= 0}
        raise SystemExit(
            "No ROS driver subscriber for active move_j command topic(s): "
            f"{missing}. Start the S15 observation terminal in --active mode and "
            "verify /arm_*/control/move_j topic subscriptions before execute."
        )

    def wait_for_waypoint(
        self,
        active_arms: list[str],
        passive_arms: list[str],
        waypoint: dict[str, list[float]],
        starts: dict[str, list[float]],
        target_joint_indices: dict[str, list[int]],
        target_tolerance_rad: float,
        passive_tolerance_rad: float,
        non_commanded_tolerance_rad: float,
        timeout: float,
    ) -> dict[str, Sample]:
        deadline = time.monotonic() + timeout
        last_samples: dict[str, Sample | None] = {arm: None for arm in ARMS}

        while rclpy.ok() and time.monotonic() < deadline:
            rclpy.spin_once(self, timeout_sec=0.05)
            if any(self.samples[arm] is None for arm in ARMS):
                continue

            reached: dict[str, bool] = {}
            for arm in active_arms:
                sample = self.samples[arm]
                assert sample is not None
                last_samples[arm] = sample
                indices = target_joint_indices[arm]

                non_commanded_dev = max(
                    (
                        abs(current - start)
                        for idx, (current, start) in enumerate(zip(sample.positions, starts[arm]))
                        if idx not in indices
                    ),
                    default=0.0,
                )
                if non_commanded_dev > non_commanded_tolerance_rad:
                    raise S15SafetyError(
                        f"{arm} non-commanded joint moved "
                        f"{math.degrees(non_commanded_dev):.3f} deg, "
                        f"limit={math.degrees(non_commanded_tolerance_rad):.3f} deg"
                    )

                reached[arm] = all(
                    abs(sample.positions[idx] - waypoint[arm][idx]) <= target_tolerance_rad
                    for idx in indices
                )

            for arm in passive_arms:
                sample = self.samples[arm]
                assert sample is not None
                last_samples[arm] = sample
                passive_dev = max(
                    abs(current - start)
                    for current, start in zip(sample.positions, starts[arm])
                )
                if passive_dev > passive_tolerance_rad:
                    raise S15SafetyError(
                        f"Passive {arm} moved {math.degrees(passive_dev):.3f} deg, "
                        f"limit={math.degrees(passive_tolerance_rad):.3f} deg"
                    )

            if all(reached.values()):
                return {arm: self.samples[arm] for arm in ARMS}  # type: ignore[return-value]

        details = []
        for arm in active_arms:
            sample = last_samples[arm]
            if sample is None:
                details.append(f"{arm}=no sample")
                continue
            pieces = []
            for idx in target_joint_indices[arm]:
                pieces.append(
                    f"{sample.names[idx]} last={math.degrees(sample.positions[idx]):.2f} "
                    f"target={math.degrees(waypoint[arm][idx]):.2f}"
                )
            details.append(f"{arm}: " + ", ".join(pieces))
        raise TimeoutError("Timed out waiting for waypoint: " + "; ".join(details))

    def emergency_stop_all(self) -> None:
        for arm, client in self._estop_clients.items():
            if client.wait_for_service(timeout_sec=0.3):
                future = client.call_async(Empty.Request())
                rclpy.spin_until_future_complete(self, future, timeout_sec=0.8)
                print(f"Called {arm} emergency_stop service.", file=sys.stderr)


def run_checked(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, text=True, capture_output=True, check=False)


def require_can_interface(can_iface: str, label: str) -> None:
    if can_iface.startswith("can_arm_"):
        raise SystemExit(f"Refusing to use arm CAN {can_iface} for {label} hand.")
    result = run_checked(["ip", "-details", "link", "show", can_iface])
    if result.returncode != 0:
        print(result.stderr.strip(), file=sys.stderr)
        raise SystemExit(f"{label} hand CAN interface {can_iface!r} does not exist.")
    if "state UP" not in result.stdout and "<NOARP,UP" not in result.stdout:
        raise SystemExit(f"{label} hand CAN interface {can_iface!r} is not UP.")


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


def as_int_list(value: Any, width: int = 6) -> list[int]:
    if value is None:
        return []
    return [int(v) for v in list(value)[:width]]


def query_hand_health(api: LinkerHandApi) -> tuple[list[int], list[int], list[int]]:
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


def blend_pose(open_pose: list[int], fist_pose: list[int], fraction: float) -> list[int]:
    return [
        int(round(open_value + fraction * (fist_value - open_value)))
        for open_value, fist_value in zip(open_pose, fist_pose)
    ]


def call_hands(label: str, calls: dict[str, Any]) -> dict[str, float]:
    times: dict[str, float] = {}
    errors: list[BaseException] = []

    def runner(side: str, fn: Any) -> None:
        try:
            times[side] = time.perf_counter()
            fn()
        except BaseException as exc:  # noqa: BLE001 - preserve worker failure.
            errors.append(exc)

    threads = [
        threading.Thread(target=runner, args=(side, fn), name=f"{label}_{side}")
        for side, fn in calls.items()
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    if errors:
        raise RuntimeError(f"{label} failed: {errors[0]}") from errors[0]
    return times


def deg_list(values: list[float]) -> list[float]:
    return [round(math.degrees(v), 3) for v in values]


def format_status(status: object | None) -> str:
    if status is None:
        return "None"
    return (
        f"ctrl_mode={getattr(status, 'ctrl_mode', None)} "
        f"arm_status={getattr(status, 'arm_status', None)} "
        f"mode_feedback={getattr(status, 'mode_feedback', None)} "
        f"motion_status={getattr(status, 'motion_status', None)} "
        f"err_status={getattr(status, 'err_status', None)}"
    )


def require_arm_status_ok(arm: str, status: object | None) -> None:
    if status is None:
        print(f"WARNING: no arm_status sample yet for {arm}; continuing with joint feedback only.")
        return
    err_status = getattr(status, "err_status", 0)
    if err_status not in (0, None):
        raise S15SafetyError(f"{arm} err_status is nonzero: {err_status}")
    joint_limits = list(getattr(status, "joint_angle_limit", []) or [])
    if any(bool(value) for value in joint_limits):
        raise S15SafetyError(f"{arm} joint_angle_limit is active: {joint_limits}")
    comm = list(getattr(status, "communication_status_joint", []) or [])
    if any(bool(value) for value in comm):
        raise S15SafetyError(f"{arm} communication_status_joint is active: {comm}")


def joint_indices(sample: Sample, joint_names: tuple[str, ...]) -> list[int]:
    indices = []
    for joint_name in joint_names:
        if joint_name not in sample.names:
            raise SystemExit(f"{joint_name} not found in feedback joints: {sample.names}")
        indices.append(sample.names.index(joint_name))
    return indices


def require_joint_limits(target_deg: dict[str, float], margin_deg: float) -> None:
    for joint, value in target_deg.items():
        low, high = JOINT_LIMITS_DEG[joint]
        if value < low + margin_deg or value > high - margin_deg:
            raise S15SafetyError(
                f"{joint} target {value:.2f} deg is outside safe limit margin: "
                f"[{low + margin_deg:.2f}, {high - margin_deg:.2f}]"
            )


def require_singularity_guard(target_deg: dict[str, float]) -> None:
    j2 = target_deg["joint2"]
    j3 = target_deg["joint3"]
    if j2 < 20.0:
        raise S15SafetyError("Refusing target with joint2 < 20 deg.")
    if j2 > 165.0:
        raise S15SafetyError("Refusing target with joint2 > 165 deg.")
    if abs(j3) > 140.0:
        raise S15SafetyError("Refusing target with |joint3| > 140 deg.")
    if j2 > 145.0 and abs(j3) < 20.0:
        raise S15SafetyError("Refusing near-straight shoulder/elbow posture.")


def build_arm_targets(
    args: argparse.Namespace,
    samples: dict[str, Sample],
    active_arms: list[str],
) -> tuple[dict[str, list[float]], dict[str, list[int]], dict[str, dict[str, float]]]:
    requested_deg = {
        "joint1": args.j1_deg,
        "joint2": args.j2_deg,
        "joint3": args.j3_deg,
    }
    require_joint_limits(requested_deg, args.joint_limit_margin_deg)
    require_singularity_guard(requested_deg)

    targets: dict[str, list[float]] = {}
    indices: dict[str, list[int]] = {}
    target_summary: dict[str, dict[str, float]] = {}

    for arm in active_arms:
        sample = samples[arm]
        idxs = joint_indices(sample, JOINT_TARGETS)
        indices[arm] = idxs
        target = list(sample.positions)
        summary = {}
        for joint_name, idx in zip(JOINT_TARGETS, idxs):
            if args.target_mode == "absolute":
                target[idx] = math.radians(requested_deg[joint_name])
            else:
                target[idx] += math.radians(requested_deg[joint_name])
            summary[joint_name] = math.degrees(target[idx])
        require_joint_limits(summary, args.joint_limit_margin_deg)
        require_singularity_guard(summary)
        targets[arm] = target
        target_summary[arm] = summary

    return targets, indices, target_summary


def max_target_delta_deg(
    starts: dict[str, list[float]],
    targets: dict[str, list[float]],
    indices: dict[str, list[int]],
    active_arms: list[str],
) -> float:
    max_delta = 0.0
    for arm in active_arms:
        for idx in indices[arm]:
            max_delta = max(max_delta, abs(math.degrees(targets[arm][idx] - starts[arm][idx])))
    return max_delta


def build_waypoints(
    starts: dict[str, list[float]],
    targets: dict[str, list[float]],
    indices: dict[str, list[int]],
    active_arms: list[str],
    max_step_deg: float,
) -> list[dict[str, list[float]]]:
    if max_step_deg <= 0:
        raise SystemExit("--max-step-deg must be positive")
    max_delta = max_target_delta_deg(starts, targets, indices, active_arms)
    steps = max(1, math.ceil(max_delta / max_step_deg))
    waypoints: list[dict[str, list[float]]] = []
    for step in range(1, steps + 1):
        alpha = step / steps
        waypoint: dict[str, list[float]] = {}
        for arm in active_arms:
            values = list(starts[arm])
            for idx in indices[arm]:
                values[idx] = starts[arm][idx] + alpha * (targets[arm][idx] - starts[arm][idx])
            waypoint[arm] = values
        waypoints.append(waypoint)
    return waypoints


def selected_sides(side_arg: str) -> list[str]:
    if side_arg == "both":
        return ["left", "right"]
    return [side_arg]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--side", choices=["left", "right", "both"], required=True)
    parser.add_argument("--arm-a-namespace", default="arm_a")
    parser.add_argument("--arm-b-namespace", default="arm_b")
    parser.add_argument("--left-can", default=SIDE_TO_CAN_DEFAULT["left"])
    parser.add_argument("--right-can", default=SIDE_TO_CAN_DEFAULT["right"])
    parser.add_argument("--target-mode", choices=["absolute", "delta"], default="absolute")
    parser.add_argument("--j1-deg", type=float, default=30.0)
    parser.add_argument("--j2-deg", type=float, default=90.0)
    parser.add_argument("--j3-deg", type=float, default=30.0)
    parser.add_argument("--max-step-deg", type=float, default=10.0)
    parser.add_argument("--wide-motion-threshold-deg", type=float, default=30.0)
    parser.add_argument("--allow-wide-motion", action="store_true")
    parser.add_argument("--joint-limit-margin-deg", type=float, default=3.0)
    parser.add_argument("--feedback-timeout", type=float, default=5.0)
    parser.add_argument("--command-subscriber-timeout", type=float, default=2.0)
    parser.add_argument("--motion-timeout", type=float, default=20.0)
    parser.add_argument("--target-tolerance-deg", type=float, default=1.2)
    parser.add_argument("--passive-tolerance-deg", type=float, default=1.0)
    parser.add_argument("--non-commanded-tolerance-deg", type=float, default=1.5)
    parser.add_argument("--hold-seconds", type=float, default=1.0)
    parser.add_argument("--hand-speed", type=int, default=30)
    parser.add_argument("--hand-dwell", type=float, default=1.2)
    parser.add_argument("--hand-close-fraction", type=float, default=1.0)
    parser.add_argument("--allow-full-fist", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--confirm-clearance", action="store_true")
    parser.add_argument("--confirm-rviz-visible", action="store_true")
    parser.add_argument("--no-return", dest="return_to_start", action="store_false")
    parser.add_argument("--no-estop-on-error", dest="estop_on_error", action="store_false")
    parser.set_defaults(return_to_start=True, estop_on_error=True)
    return parser.parse_args()


def require_safe_args(args: argparse.Namespace) -> None:
    if args.max_step_deg > 15.0:
        raise SystemExit("--max-step-deg must be <= 15 deg for S15 first gates.")
    if args.joint_limit_margin_deg < 2.0:
        raise SystemExit("--joint-limit-margin-deg must be >= 2 deg.")
    if args.hand_speed < 10 or args.hand_speed > 50:
        raise SystemExit("--hand-speed must be in 10..50 for S15 first gates.")
    if args.hand_close_fraction < 0.0 or args.hand_close_fraction > 1.0:
        raise SystemExit("--hand-close-fraction must be in 0..1.")
    if args.execute and args.hand_close_fraction > 0.5 and not args.allow_full_fist:
        raise SystemExit(
            "Full or near-full fist is blocked. Add --allow-full-fist only after "
            "the hand path is clear and no object/contact risk exists."
        )
    if not args.return_to_start:
        raise SystemExit("S15 first gates must return arms to start; do not use --no-return.")
    if args.execute and not args.confirm_clearance:
        raise SystemExit("Execution requires --confirm-clearance.")
    if args.execute and not args.confirm_rviz_visible:
        raise SystemExit("Execution requires --confirm-rviz-visible.")


def print_plan(
    args: argparse.Namespace,
    active_sides: list[str],
    active_arms: list[str],
    passive_arms: list[str],
    samples: dict[str, Sample],
    targets: dict[str, list[float]],
    target_summary: dict[str, dict[str, float]],
    waypoints: list[dict[str, list[float]]],
) -> None:
    print("S15 NERO coordinated arm + hand sequence")
    print(f"execute={args.execute} side={args.side} target_mode={args.target_mode}")
    print(f"side_mapping=left->arm_b/can1 right->arm_a/can2")
    print(f"active_sides={active_sides} active_arms={active_arms} passive_arms={passive_arms}")
    print(f"requested_joints_deg={{'joint1': {args.j1_deg}, 'joint2': {args.j2_deg}, 'joint3': {args.j3_deg}}}")
    print(f"waypoint_count={len(waypoints)} max_step_deg={args.max_step_deg}")
    print(f"hand_sequence=open -> close_fraction_{args.hand_close_fraction:.2f} -> open")
    for side in active_sides:
        open_pose = list(PRESETS["open"][side])
        close_pose = blend_pose(open_pose, list(PRESETS["fist"][side]), args.hand_close_fraction)
        print(f"{side}_hand_open_pose={open_pose}")
        print(f"{side}_hand_close_pose={close_pose}")
    for arm in ARMS:
        print(f"{arm}_current_deg={deg_list(samples[arm].positions)}")
    for arm in active_arms:
        print(f"{arm}_target_summary_deg={target_summary[arm]}")
        print(f"{arm}_target_full_deg={deg_list(targets[arm])}")


def connect_hands(args: argparse.Namespace, active_sides: list[str]) -> dict[str, LinkerHandApi]:
    can_by_side = {"left": args.left_can, "right": args.right_can}
    apis: dict[str, LinkerHandApi] = {}
    for side in active_sides:
        require_can_interface(can_by_side[side], side)
    for side in active_sides:
        apis[side] = LinkerHandApi(hand_type=side, hand_joint="L6", can=can_by_side[side])
    time.sleep(0.3)
    return apis


def run_hand_sequence(args: argparse.Namespace, active_sides: list[str]) -> None:
    apis: dict[str, LinkerHandApi] = {}
    try:
        apis = connect_hands(args, active_sides)
        for side, api in apis.items():
            temp, fault, current = query_hand_health(api)
            print(f"pre_{side}_hand_health temperature={temp} fault={fault} current_raw={current}")
            if any(value != 0 for value in fault):
                raise S15SafetyError(f"{side} hand has nonzero fault before motion: {fault}")

        speed = [args.hand_speed] * 6
        for side, api in apis.items():
            print(f"setting_{side}_hand_speed={speed}")
            api.set_joint_speed(speed)
        time.sleep(0.2)

        open_poses = {side: list(PRESETS["open"][side]) for side in active_sides}
        fist_poses = {
            side: blend_pose(list(PRESETS["open"][side]), list(PRESETS["fist"][side]), args.hand_close_fraction)
            for side in active_sides
        }

        print(f"sending_hand_open={open_poses}")
        open_times = call_hands(
            "hand_open",
            {side: (lambda api=api, pose=open_poses[side]: api.finger_move(pose)) for side, api in apis.items()},
        )
        if len(open_times) == 2:
            print(f"hand_open_send_delta_ms={abs(open_times['left'] - open_times['right']) * 1000.0:.3f}")
        time.sleep(args.hand_dwell)

        print(f"sending_hand_close={fist_poses}")
        close_times = call_hands(
            "hand_close",
            {side: (lambda api=api, pose=fist_poses[side]: api.finger_move(pose)) for side, api in apis.items()},
        )
        if len(close_times) == 2:
            print(f"hand_close_send_delta_ms={abs(close_times['left'] - close_times['right']) * 1000.0:.3f}")
        time.sleep(args.hand_dwell)

        print(f"returning_hand_open={open_poses}")
        return_times = call_hands(
            "hand_return_open",
            {side: (lambda api=api, pose=open_poses[side]: api.finger_move(pose)) for side, api in apis.items()},
        )
        if len(return_times) == 2:
            print(f"hand_return_send_delta_ms={abs(return_times['left'] - return_times['right']) * 1000.0:.3f}")
        time.sleep(args.hand_dwell)

        for side, api in apis.items():
            temp, fault, current = query_hand_health(api)
            print(f"post_{side}_hand_health temperature={temp} fault={fault} current_raw={current}")
            if any(value != 0 for value in fault):
                raise S15SafetyError(f"{side} hand has nonzero fault after motion: {fault}")
    finally:
        for api in apis.values():
            close_sdk_bus(api)


def execute_arm_path(
    args: argparse.Namespace,
    node: S15ArmHandNode,
    active_arms: list[str],
    passive_arms: list[str],
    names: dict[str, list[str]],
    starts: dict[str, list[float]],
    targets: dict[str, list[float]],
    indices: dict[str, list[int]],
    waypoints: list[dict[str, list[float]]],
) -> None:
    for number, waypoint in enumerate(waypoints, start=1):
        print(f"Publishing arm waypoint {number}/{len(waypoints)}")
        node.publish_targets(active_arms, names, waypoint)
        node.wait_for_waypoint(
            active_arms,
            passive_arms,
            waypoint,
            starts,
            indices,
            math.radians(args.target_tolerance_deg),
            math.radians(args.passive_tolerance_deg),
            math.radians(args.non_commanded_tolerance_deg),
            args.motion_timeout,
        )
        for arm in active_arms:
            sample = node.samples[arm]
            if sample is not None:
                print(f"after_waypoint_{number}_{arm}_deg={deg_list(sample.positions)}")

    print(f"Holding target for {args.hold_seconds:.1f}s before hand sequence.")
    node.wait_for_waypoint(
        active_arms,
        passive_arms,
        targets,
        starts,
        indices,
        math.radians(args.target_tolerance_deg),
        math.radians(args.passive_tolerance_deg),
        math.radians(args.non_commanded_tolerance_deg),
        args.hold_seconds,
    )


def main() -> int:
    args = parse_args()
    require_safe_args(args)

    active_sides = selected_sides(args.side)
    active_arms = sorted({SIDE_TO_ARM[side] for side in active_sides})
    passive_arms = [arm for arm in ARMS if arm not in active_arms]

    rclpy.init()
    node = S15ArmHandNode(args.arm_a_namespace, args.arm_b_namespace)
    try:
        samples = node.wait_samples(args.feedback_timeout)
        node.spin_for_status(0.5)
        for arm in ARMS:
            require_arm_status_ok(arm, node.statuses[arm])

        starts = {arm: list(samples[arm].positions) for arm in ARMS}
        names = {arm: samples[arm].names for arm in ARMS}
        targets, indices, target_summary = build_arm_targets(args, samples, active_arms)
        max_delta = max_target_delta_deg(starts, targets, indices, active_arms)
        waypoints = build_waypoints(starts, targets, indices, active_arms, args.max_step_deg)
        print_plan(
            args,
            active_sides,
            active_arms,
            passive_arms,
            samples,
            targets,
            target_summary,
            waypoints,
        )
        for arm in ARMS:
            print(f"{arm}_status={format_status(node.statuses[arm])}")
        print(f"command_subscriber_counts={node.command_subscription_counts()}")
        print(f"max_planned_joint_delta_deg={max_delta:.3f}")
        if max_delta > args.wide_motion_threshold_deg:
            print(
                f"wide_motion_required=true threshold_deg={args.wide_motion_threshold_deg} "
                f"add --allow-wide-motion for execute"
            )

        if not args.execute:
            print("Dry run only. Add --execute plus required safety confirmations after review.")
            return 0
        if max_delta > args.wide_motion_threshold_deg and not args.allow_wide_motion:
            raise SystemExit(
                f"Planned arm motion requires {max_delta:.2f} deg max joint change. "
                f"Add --allow-wide-motion only after dry-run review."
            )
        counts = node.wait_command_subscribers(active_arms, args.command_subscriber_timeout)
        print(f"execute_command_subscriber_counts={counts}")

        execute_arm_path(args, node, active_arms, passive_arms, names, starts, targets, indices, waypoints)
        run_hand_sequence(args, active_sides)

        print("Returning active arms to original joint angles.")
        return_waypoints = build_waypoints(targets, starts, indices, active_arms, args.max_step_deg)
        execute_arm_path(
            args,
            node,
            active_arms,
            passive_arms,
            names,
            starts,
            starts,
            indices,
            return_waypoints,
        )

        node.spin_for_status(0.5)
        for arm in ARMS:
            print(f"final_{arm}_status={format_status(node.statuses[arm])}")
        print("S15 coordinated arm + hand sequence completed.")
        return 0
    except KeyboardInterrupt:
        print("Interrupted by operator.", file=sys.stderr)
        if args.execute and args.estop_on_error:
            node.emergency_stop_all()
        return 130
    except Exception as exc:
        print(f"S15 coordinated sequence failed: {exc}", file=sys.stderr)
        if args.execute and args.estop_on_error:
            node.emergency_stop_all()
        return 1
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
