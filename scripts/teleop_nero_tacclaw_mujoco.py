#!/usr/bin/env python3
"""Kinematic DataMaster teleoperation for the dual-NERO + TacClaw MuJoCo model.

This process subscribes directly to the DataMaster ZMQ publisher. It never
opens a CAN interface and never connects to either physical TacClaw.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import threading
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

SCRIPT_DIR = Path(__file__).resolve().parent
WRAPPER_ROOT = SCRIPT_DIR.parent
PROJECT_ROOT = WRAPPER_ROOT.parents[1]
WRAPPER_SOURCE = WRAPPER_ROOT / "src"
for source_root in (PROJECT_ROOT, WRAPPER_SOURCE, SCRIPT_DIR):
    value = str(source_root)
    if value not in sys.path:
        sys.path.insert(0, value)

from prometheus.nodes.sensors.datamaster import (  # noqa: E402
    DATAMASTER_TOPIC,
    DEFAULT_ENDPOINT,
    ClutchInterlock,
    DataMasterSample,
    configure_subscriber_socket,
    decode_datamaster_multipart,
)
from prometheus.nodes.sensors.xrobotoolkit import (  # noqa: E402
    DEFAULT_SDK_LIBRARY_PATH,
    XRobotToolkitSample,
    _read_xr_sample,
)
from visualize_nero_tacclaw_assembly import (  # noqa: E402
    CAPTURED_JOINTS,
    IK_READY_JOINTS,
    ZERO_JOINTS,
    _build_model,
    _joint_vector,
    _set_joint_pose,
)

DEFAULT_URDF = (
    WRAPPER_ROOT
    / "submodules/agx_arm_ros/src/agx_arm_description/agx_arm_urdf/nero/urdf"
    / "nero_description.urdf"
)
SIDE_TO_ARM = {"left": "arm_b", "right": "arm_a"}
ARM_NAMES = ("arm_a", "arm_b")
SIDE_NAMES = ("left", "right")

# ``MjSpec.compile()`` fuses the fixed flange/tool bodies into link7. Keep the
# same fixed transform used by ``visualize_nero_tacclaw_assembly.py`` so runtime
# finger updates remain in the compiled link7 frame rather than the original
# TacClaw tool-local frame.
TACCLAW_TO_LINK7_TRANSLATION = np.asarray([0.031, 0.0, -0.0235], dtype=np.float64)


def _positive_float(value: str) -> float:
    try:
        result = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("value must be a positive number") from exc
    if not math.isfinite(result) or result <= 0.0:
        raise argparse.ArgumentTypeError("value must be a positive finite number")
    return result


def _non_negative_float(value: str) -> float:
    try:
        result = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("value must be a non-negative number") from exc
    if not math.isfinite(result) or result < 0.0:
        raise argparse.ArgumentTypeError("value must be a non-negative finite number")
    return result


def _unit_interval(value: str) -> float:
    result = _non_negative_float(value)
    if result > 1.0:
        raise argparse.ArgumentTypeError("value must be in 0..1")
    return result


def _matrix3(value: str) -> np.ndarray:
    try:
        matrix = np.asarray([float(item) for item in value.split(",")]).reshape(3, 3)
    except (ValueError, TypeError) as exc:
        raise argparse.ArgumentTypeError(
            "matrix must contain nine comma-separated numbers"
        ) from exc
    if not np.all(np.isfinite(matrix)) or not np.allclose(
        matrix.T @ matrix, np.eye(3), atol=1.0e-5
    ):
        raise argparse.ArgumentTypeError("matrix must be finite and orthonormal")
    determinant = float(np.linalg.det(matrix))
    if not math.isclose(abs(determinant), 1.0, abs_tol=1.0e-5):
        raise argparse.ArgumentTypeError("matrix determinant must be +1 or -1")
    return matrix


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Teleoperate the dual-NERO + TacClaw MuJoCo model from DataMaster "
            "or native XRoboToolkit input. No robot or gripper hardware is opened."
        )
    )
    parser.add_argument("--urdf", type=Path, default=DEFAULT_URDF)
    parser.add_argument(
        "--input",
        choices=("datamaster", "xrobotoolkit"),
        default="datamaster",
        help="operator input source (default: datamaster)",
    )
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    parser.add_argument("--receive-hwm", type=int, default=8)
    parser.add_argument(
        "--xr-sdk-library",
        type=Path,
        default=Path(DEFAULT_SDK_LIBRARY_PATH),
    )
    parser.add_argument("--xr-publish-hz", type=_positive_float, default=100.0)
    parser.add_argument(
        "--xr-source-gap-timeout-s",
        type=_positive_float,
        default=1.0,
    )
    parser.add_argument("--xr-grip-threshold", type=_unit_interval, default=0.9)
    parser.add_argument(
        "--log-jsonl",
        type=Path,
        default=None,
        help=(
            "write a per-control-frame diagnostic JSONL trace; the path must "
            "not already exist"
        ),
    )
    parser.add_argument("--control-hz", type=_positive_float, default=60.0)
    parser.add_argument("--input-timeout-s", type=_positive_float, default=0.15)
    parser.add_argument("--release-stable-s", type=_positive_float, default=0.25)
    parser.add_argument("--base-spacing-m", type=_positive_float, default=0.260)
    parser.add_argument(
        "--initial-gripper-opening",
        type=_unit_interval,
        default=0.42,
        help="initial visual opening before a valid trigger sample (default: 0.42)",
    )
    parser.add_argument("--translation-scale", type=_non_negative_float, default=1.0)
    parser.add_argument("--rotation-scale", type=_non_negative_float, default=1.0)
    parser.add_argument(
        "--translation-matrix",
        type=_matrix3,
        default=np.eye(3),
        metavar="R00,R01,...,R22",
        help="orthonormal DataMaster-to-MuJoCo translation-axis mapping",
    )
    parser.add_argument(
        "--orientation-matrix",
        type=_matrix3,
        default=np.eye(3),
        metavar="R00,R01,...,R22",
        help="proper rotation mapping DataMaster orientation deltas into MuJoCo",
    )
    parser.add_argument("--damping", type=_positive_float, default=0.05)
    parser.add_argument("--orientation-weight", type=_positive_float, default=0.35)
    parser.add_argument("--max-joint-step-deg", type=_positive_float, default=1.5)
    parser.add_argument("--max-cartesian-step-m", type=_positive_float, default=0.010)
    parser.add_argument("--max-orientation-step-deg", type=_positive_float, default=3.0)
    parser.add_argument(
        "--pose",
        choices=("ik-ready", "zero", "captured"),
        default="ik-ready",
        help="named initial hardware pose (default: J4 +90 deg IK-ready)",
    )
    parser.add_argument(
        "--arm-a",
        type=_joint_vector,
        default=None,
        metavar="J1,J2,J3,J4,J5,J6,J7",
        help="raw arm_a feedback in radians; overrides --pose for arm_a",
    )
    parser.add_argument(
        "--arm-b",
        type=_joint_vector,
        default=None,
        metavar="J1,J2,J3,J4,J5,J6,J7",
        help="raw arm_b feedback in radians; overrides --pose for arm_b",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="use a synthetic input instead of connecting to DataMaster",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="run without opening the MuJoCo viewer (requires --duration-s)",
    )
    parser.add_argument(
        "--duration-s",
        type=_non_negative_float,
        default=0.0,
        help="stop after this duration; zero means run until the viewer closes",
    )
    args = parser.parse_args()
    if not 1 <= args.receive_hwm <= 64:
        parser.error("--receive-hwm must be in 1..64")
    if args.control_hz > 240.0:
        parser.error("--control-hz must not exceed 240 Hz")
    if args.xr_publish_hz > 250.0:
        parser.error("--xr-publish-hz must not exceed 250 Hz")
    if args.headless and args.duration_s <= 0.0:
        parser.error("--headless requires a positive --duration-s")
    if np.linalg.det(args.orientation_matrix) < 0.0:
        parser.error("--orientation-matrix must have determinant +1")
    named_pose = {
        "ik-ready": IK_READY_JOINTS,
        "zero": ZERO_JOINTS,
        "captured": CAPTURED_JOINTS,
    }[args.pose]
    if args.arm_a is None:
        args.arm_a = named_pose["arm_a"].copy()
    if args.arm_b is None:
        args.arm_b = named_pose["arm_b"].copy()
    return args


class _LatestSampleSlot:
    """Thread-safe one-sample mailbox that never queues stale tracking data."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._sample: DataMasterSample | None = None
        self._received_s: float | None = None
        self._published_sequence = 0
        self._consumed_sequence = 0
        self._discarded_messages = 0
        self._pending_error: Exception | None = None

    @property
    def discarded_messages(self) -> int:
        with self._lock:
            return self._discarded_messages

    def publish(self, sample: DataMasterSample, *, received_s: float) -> None:
        with self._lock:
            if self._published_sequence > self._consumed_sequence:
                self._discarded_messages += 1
            self._sample = sample
            self._received_s = float(received_s)
            self._published_sequence += 1

    def publish_error(self, error: Exception) -> None:
        with self._lock:
            self._pending_error = error

    def consume(self) -> tuple[DataMasterSample | None, float | None]:
        with self._lock:
            if self._pending_error is not None:
                error = self._pending_error
                self._pending_error = None
                raise error
            if self._published_sequence == self._consumed_sequence:
                return None, None
            self._consumed_sequence = self._published_sequence
            return self._sample, self._received_s


class DataMasterReceiver:
    """Continuously consume ZMQ and expose only the newest decoded sample."""

    def __init__(self, *, endpoint: str, receive_hwm: int):
        try:
            import zmq
        except ImportError as exc:
            raise RuntimeError("pyzmq is required for live DataMaster input") from exc
        self.zmq = zmq
        self.endpoint = str(endpoint)
        self.receive_hwm = int(receive_hwm)
        self._slot = _LatestSampleSlot()
        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=self._receive_loop,
            name="datamaster_mujoco_receiver",
            daemon=True,
        )
        self._thread.start()

    @property
    def discarded_messages(self) -> int:
        return self._slot.discarded_messages

    def latest(self, now_s: float) -> tuple[DataMasterSample | None, float | None]:
        del now_s
        return self._slot.consume()

    def close(self) -> None:
        self._stop.set()
        self._thread.join(timeout=1.0)
        if self._thread.is_alive():
            raise RuntimeError("DataMaster receiver thread did not stop")

    def _receive_loop(self) -> None:
        context = None
        socket = None
        try:
            context = self.zmq.Context()
            socket = context.socket(self.zmq.SUB)
            socket.setsockopt(self.zmq.RCVTIMEO, 50)
            configure_subscriber_socket(
                socket,
                self.zmq,
                endpoint=self.endpoint,
                topic=DATAMASTER_TOPIC,
                receive_hwm=self.receive_hwm,
            )
            while not self._stop.is_set():
                try:
                    frames = socket.recv_multipart()
                except self.zmq.Again:
                    continue
                received_s = time.monotonic()
                try:
                    sample = decode_datamaster_multipart(frames)
                except ValueError as exc:
                    self._slot.publish_error(exc)
                    continue
                self._slot.publish(sample, received_s=received_s)
        except Exception as exc:
            if not self._stop.is_set():
                self._slot.publish_error(
                    RuntimeError(f"DataMaster receiver thread failed: {exc}")
                )
        finally:
            if socket is not None:
                socket.close(linger=0)
            if context is not None:
                context.term()


class XRobotToolkitReceiver:
    """Read native Quest controllers and expose latest headset-relative samples."""

    def __init__(
        self,
        *,
        sdk_library_path: Path,
        publish_hz: float,
        source_gap_timeout_s: float,
        grip_threshold: float,
    ) -> None:
        import ctypes

        library = Path(sdk_library_path).expanduser().resolve()
        if not library.is_file():
            raise FileNotFoundError(f"XRoboToolkit runtime library not found: {library}")
        ctypes.CDLL(str(library), mode=ctypes.RTLD_GLOBAL)
        try:
            import xrobotoolkit_sdk as xrt
        except ImportError as exc:
            raise RuntimeError(
                "xrobotoolkit_sdk is required for native Quest input"
            ) from exc

        self.xrt = xrt
        self.publish_hz = float(publish_hz)
        self.source_gap_timeout_s = float(source_gap_timeout_s)
        self.grip_threshold = float(grip_threshold)
        self._slot = _LatestSampleSlot()
        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=self._receive_loop,
            name="xrobotoolkit_mujoco_receiver",
            daemon=True,
        )
        self._thread.start()

    @property
    def discarded_messages(self) -> int:
        return self._slot.discarded_messages

    def latest(self, now_s: float) -> tuple[DataMasterSample | None, float | None]:
        del now_s
        return self._slot.consume()

    def close(self) -> None:
        self._stop.set()
        self._thread.join(timeout=2.0)
        if self._thread.is_alive():
            raise RuntimeError("XRoboToolkit receiver thread did not stop")

    def _receive_loop(self) -> None:
        initialized = False
        last_source_timestamp_ns: int | None = None
        last_source_advance_s = time.monotonic()
        fault_latched = False
        period_s = 1.0 / self.publish_hz
        next_tick_s = time.monotonic()
        try:
            self.xrt.init()
            initialized = True
            while not self._stop.is_set():
                now_s = time.monotonic()
                input_error: Exception | None = None
                try:
                    sample = _read_xr_sample(self.xrt)
                    source_timestamp_ns = int(sample.source_timestamp_ns)
                    if last_source_timestamp_ns is None or (
                        source_timestamp_ns > last_source_timestamp_ns
                    ):
                        self._slot.publish(
                            _xrobotoolkit_sample_to_datamaster(
                                sample,
                                grip_threshold=self.grip_threshold,
                            ),
                            received_s=time.monotonic(),
                        )
                        last_source_timestamp_ns = source_timestamp_ns
                        last_source_advance_s = now_s
                        fault_latched = False
                    elif source_timestamp_ns < last_source_timestamp_ns:
                        raise ValueError(
                            "Quest source timestamp moved backwards: "
                            f"{source_timestamp_ns} < {last_source_timestamp_ns}"
                        )
                    elif now_s - last_source_advance_s > self.source_gap_timeout_s:
                        raise TimeoutError(
                            "Quest source timestamp has not advanced for "
                            f"{now_s - last_source_advance_s:.3f}s"
                        )

                except Exception as exc:
                    input_error = exc

                if (
                    input_error is not None
                    and not fault_latched
                    and now_s - last_source_advance_s >= self.source_gap_timeout_s
                ):
                    fault_latched = True
                    last_source_timestamp_ns = None
                    self._slot.publish_error(
                        ValueError(
                            "Quest tracking unavailable; clutches disarmed: "
                            f"{type(input_error).__name__}: {input_error}"
                        )
                    )
                next_tick_s += period_s
                delay_s = next_tick_s - time.monotonic()
                if delay_s > 0.0:
                    self._stop.wait(delay_s)
                else:
                    next_tick_s = time.monotonic()
        except Exception as exc:
            if not self._stop.is_set():
                self._slot.publish_error(
                    RuntimeError(
                        f"XRoboToolkit receiver failed: {type(exc).__name__}: {exc}"
                    )
                )
        finally:
            if initialized:
                try:
                    self.xrt.close()
                except Exception:
                    pass


def _xrobotoolkit_sample_to_datamaster(
    sample: XRobotToolkitSample,
    *,
    grip_threshold: float,
) -> DataMasterSample:
    headset = _xyzw_pose_transform(sample.headset_pose_xyzw)
    world_to_local = _headset_yaw_world_to_local(headset)
    left = world_to_local @ _xyzw_pose_transform(sample.left_pose_xyzw)
    right = world_to_local @ _xyzw_pose_transform(sample.right_pose_xyzw)
    return DataMasterSample(
        left_pose=_transform_to_wire_pose(left),
        right_pose=_transform_to_wire_pose(right),
        left_joints=(0.0,) * 7,
        right_joints=(0.0,) * 7,
        left_clutch=float(sample.left_grip) > float(grip_threshold),
        right_clutch=float(sample.right_grip) > float(grip_threshold),
        left_trigger=float(sample.left_trigger),
        right_trigger=float(sample.right_trigger),
        left_glove=(0.0,) * 15,
        right_glove=(0.0,) * 15,
        left_glove_raw=(0.0,) * 15,
        right_glove_raw=(0.0,) * 15,
    )


def _xyzw_pose_transform(values: Sequence[float]) -> np.ndarray:
    vector = np.asarray(values, dtype=np.float64)
    if vector.shape != (7,) or not np.all(np.isfinite(vector)):
        raise ValueError("XR pose must contain seven finite values")
    return _wire_pose_transform(
        (vector[0], vector[1], vector[2], vector[6], *vector[3:6])
    )


def _headset_yaw_world_to_local(headset: np.ndarray) -> np.ndarray:
    transform = np.asarray(headset, dtype=np.float64).reshape(4, 4)
    backward = transform[:3, 2].copy()
    backward[1] = 0.0
    norm = float(np.linalg.norm(backward))
    if norm < 1.0e-6:
        raise ValueError("headset forward axis cannot define a horizontal frame")
    backward /= norm
    up = np.asarray([0.0, 1.0, 0.0], dtype=np.float64)
    right = np.cross(up, backward)
    right /= float(np.linalg.norm(right))
    local_to_world_rotation = np.column_stack((right, up, backward))
    world_to_local = np.eye(4, dtype=np.float64)
    world_to_local[:3, :3] = local_to_world_rotation.T
    world_to_local[:3, 3] = -local_to_world_rotation.T @ transform[:3, 3]
    return world_to_local


def _transform_to_wire_pose(transform: np.ndarray) -> tuple[float, ...]:
    matrix = np.asarray(transform, dtype=np.float64).reshape(4, 4)
    quaternion = _rotation_matrix_to_quaternion_wxyz(matrix[:3, :3])
    return (*tuple(float(value) for value in matrix[:3, 3]), *quaternion)


def _rotation_matrix_to_quaternion_wxyz(
    rotation: np.ndarray,
) -> tuple[float, float, float, float]:
    matrix = np.asarray(rotation, dtype=np.float64).reshape(3, 3)
    if not np.all(np.isfinite(matrix)):
        raise ValueError("rotation matrix must be finite")
    trace = float(np.trace(matrix))
    if trace > 0.0:
        scale = math.sqrt(trace + 1.0) * 2.0
        w = 0.25 * scale
        x = (matrix[2, 1] - matrix[1, 2]) / scale
        y = (matrix[0, 2] - matrix[2, 0]) / scale
        z = (matrix[1, 0] - matrix[0, 1]) / scale
    else:
        index = int(np.argmax(np.diag(matrix)))
        if index == 0:
            scale = math.sqrt(1.0 + matrix[0, 0] - matrix[1, 1] - matrix[2, 2]) * 2.0
            w = (matrix[2, 1] - matrix[1, 2]) / scale
            x = 0.25 * scale
            y = (matrix[0, 1] + matrix[1, 0]) / scale
            z = (matrix[0, 2] + matrix[2, 0]) / scale
        elif index == 1:
            scale = math.sqrt(1.0 + matrix[1, 1] - matrix[0, 0] - matrix[2, 2]) * 2.0
            w = (matrix[0, 2] - matrix[2, 0]) / scale
            x = (matrix[0, 1] + matrix[1, 0]) / scale
            y = 0.25 * scale
            z = (matrix[1, 2] + matrix[2, 1]) / scale
        else:
            scale = math.sqrt(1.0 + matrix[2, 2] - matrix[0, 0] - matrix[1, 1]) * 2.0
            w = (matrix[1, 0] - matrix[0, 1]) / scale
            x = (matrix[0, 2] + matrix[2, 0]) / scale
            y = (matrix[1, 2] + matrix[2, 1]) / scale
            z = 0.25 * scale
    quaternion = np.asarray([w, x, y, z], dtype=np.float64)
    quaternion /= float(np.linalg.norm(quaternion))
    if quaternion[0] < 0.0:
        quaternion *= -1.0
    return tuple(float(value) for value in quaternion)  # type: ignore[return-value]


class DemoSource:
    """Synthetic clutch-anchored motion for validating the model without a device."""

    discarded_messages = 0

    def __init__(self):
        self.started_s = time.monotonic()

    def latest(self, now_s: float) -> tuple[DataMasterSample, float]:
        elapsed = now_s - self.started_s
        engaged = elapsed >= 0.5
        motion_time = max(0.0, elapsed - 0.5)
        angle = 0.20 * math.sin(motion_time * 0.8)
        right_pose = _demo_pose(
            0.045 * math.sin(motion_time * 0.55),
            0.025 * math.sin(motion_time * 0.37),
            0.030 * math.sin(motion_time * 0.71),
            axis=(1.0, 0.0, 0.0),
            angle=angle,
        )
        left_pose = _demo_pose(
            right_pose[0],
            -right_pose[1],
            right_pose[2],
            axis=(1.0, 0.0, 0.0),
            angle=-angle,
        )
        trigger_phase = 0.5 + 0.5 * math.sin(motion_time * 1.2)
        return (
            DataMasterSample(
                left_pose=left_pose,
                right_pose=right_pose,
                left_joints=(0.0,) * 7,
                right_joints=(0.0,) * 7,
                left_clutch=engaged,
                right_clutch=engaged,
                left_trigger=trigger_phase,
                right_trigger=trigger_phase,
                left_glove=(0.0,) * 15,
                right_glove=(0.0,) * 15,
                left_glove_raw=(0.0,) * 15,
                right_glove_raw=(0.0,) * 15,
            ),
            now_s,
        )

    def close(self) -> None:
        return None


@dataclass(frozen=True)
class TeleopStatus:
    active_sides: tuple[str, ...]
    gripper_openings: tuple[float, float]
    position_errors_m: dict[str, float]
    orientation_errors_deg: dict[str, float]
    joint_steps_model_rad: dict[str, tuple[float, ...]]
    jacobian_conditions: dict[str, float | None]
    joint_step_limited: dict[str, tuple[bool, ...]]
    joint_limit_hits: dict[str, tuple[bool, ...]]


class MuJoCoTeleopJsonlLogger:
    """Write enough per-frame state to diagnose joint discontinuities."""

    SCHEMA = "prometheus.mujoco_teleop.v1"

    def __init__(
        self,
        path: Path,
        *,
        args: argparse.Namespace,
        controller: Any,
        joint_offsets: Mapping[str, Sequence[float]],
        joint_signs: Mapping[str, Sequence[float]],
    ) -> None:
        self.path = Path(path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._stream = self.path.open("x", encoding="utf-8", buffering=1)
        self.controller = controller
        self.offsets = {
            arm: np.asarray(joint_offsets[arm], dtype=np.float64) for arm in ARM_NAMES
        }
        self.signs = {
            arm: np.asarray(joint_signs[arm], dtype=np.float64) for arm in ARM_NAMES
        }
        for arm in ARM_NAMES:
            if self.offsets[arm].shape != (7,) or self.signs[arm].shape != (7,):
                raise ValueError(f"joint conversion for {arm} must contain 7 values")
            if np.any(self.signs[arm] == 0.0):
                raise ValueError(f"joint signs for {arm} must be non-zero")
        self.started_s = time.monotonic()
        self.sequence = 0
        self._previous_s: float | None = None
        self._previous_joints: dict[str, np.ndarray] = {}
        self._previous_velocities: dict[str, np.ndarray] = {}
        self._write(
            {
                "type": "metadata",
                "schema": self.SCHEMA,
                "wall_time_ns": time.time_ns(),
                "operator_input": str(getattr(args, "input", "datamaster")),
                "endpoint": str(args.endpoint),
                "pose": str(args.pose),
                "control_hz": float(args.control_hz),
                "translation_scale": float(args.translation_scale),
                "rotation_scale": float(args.rotation_scale),
                "damping": float(args.damping),
                "orientation_weight": float(args.orientation_weight),
                "max_joint_step_deg": float(args.max_joint_step_deg),
                "max_cartesian_step_m": float(args.max_cartesian_step_m),
                "max_orientation_step_deg": float(args.max_orientation_step_deg),
                "arm_joint_order": [f"J{index}" for index in range(1, 8)],
                "joint_coordinate": "hardware_radians",
            }
        )

    def record(
        self,
        *,
        now_s: float,
        sample: DataMasterSample | None,
        sample_received: bool,
        received_s: float | None,
        fresh: bool,
        active: Mapping[str, bool],
        interlocks: Mapping[str, ClutchInterlock],
        status: TeleopStatus | None,
        discarded_messages: int,
        receive_ms: float,
        control_ms: float,
        viewer_sync_ms: float,
    ) -> None:
        dt_s = None if self._previous_s is None else now_s - self._previous_s
        arms: dict[str, dict[str, Any]] = {}
        for arm in ARM_NAMES:
            model_joints = self.controller.data.qpos[
                self.controller.qpos_addresses[arm]
            ].copy()
            joints = (model_joints - self.offsets[arm]) / self.signs[arm]
            previous = self._previous_joints.get(arm)
            if previous is None or dt_s is None or dt_s <= 0.0:
                delta = np.zeros(7, dtype=np.float64)
                velocity = np.zeros(7, dtype=np.float64)
                acceleration = np.zeros(7, dtype=np.float64)
                reversals = np.zeros(7, dtype=bool)
            else:
                delta = joints - previous
                velocity = delta / dt_s
                previous_velocity = self._previous_velocities.get(arm)
                if previous_velocity is None:
                    acceleration = np.zeros(7, dtype=np.float64)
                    reversals = np.zeros(7, dtype=bool)
                else:
                    acceleration = (velocity - previous_velocity) / dt_s
                    threshold = math.radians(1.0)
                    reversals = (
                        (velocity * previous_velocity < 0.0)
                        & (np.abs(velocity) >= threshold)
                        & (np.abs(previous_velocity) >= threshold)
                    )
            self._previous_joints[arm] = joints.copy()
            self._previous_velocities[arm] = velocity.copy()

            model_step = None
            condition = None
            step_limited = None
            limit_hits = None
            position_error = None
            orientation_error = None
            if status is not None:
                if arm in status.joint_steps_model_rad:
                    model_step = np.asarray(
                        status.joint_steps_model_rad[arm], dtype=np.float64
                    )
                condition = status.jacobian_conditions.get(arm)
                step_limited = status.joint_step_limited.get(arm)
                limit_hits = status.joint_limit_hits.get(arm)
                position_error = status.position_errors_m.get(arm)
                orientation_error = status.orientation_errors_deg.get(arm)
            hardware_step = None if model_step is None else model_step / self.signs[arm]
            arms[arm] = {
                "joints_rad": joints.tolist(),
                "joint_delta_rad": delta.tolist(),
                "joint_velocity_rad_s": velocity.tolist(),
                "joint_acceleration_rad_s2": acceleration.tolist(),
                "velocity_direction_reversal": reversals.tolist(),
                "max_abs_joint_delta_deg": math.degrees(
                    float(np.max(np.abs(delta)))
                ),
                "solver_joint_step_rad": (
                    None if hardware_step is None else hardware_step.tolist()
                ),
                "solver_step_limited": (
                    None if step_limited is None else list(step_limited)
                ),
                "joint_limit_hits": None if limit_hits is None else list(limit_hits),
                "jacobian_condition": condition,
                "tcp_position_error_m": position_error,
                "tcp_orientation_error_deg": orientation_error,
            }

        input_sample = None
        if sample is not None:
            input_sample = {
                "left_pose": list(sample.left_pose),
                "right_pose": list(sample.right_pose),
                "left_joints": list(sample.left_joints),
                "right_joints": list(sample.right_joints),
                "left_clutch": bool(sample.left_clutch),
                "right_clutch": bool(sample.right_clutch),
                "left_trigger": float(sample.left_trigger),
                "right_trigger": float(sample.right_trigger),
            }
        self._write(
            {
                "type": "frame",
                "schema": self.SCHEMA,
                "sequence": self.sequence,
                "wall_time_ns": time.time_ns(),
                "elapsed_s": now_s - self.started_s,
                "dt_s": dt_s,
                "sample_received": bool(sample_received),
                "input_fresh": bool(fresh),
                "input_local_age_ms": (
                    None
                    if received_s is None
                    else max(0.0, (now_s - received_s) * 1000.0)
                ),
                "discarded_messages": int(discarded_messages),
                "timing_ms": {
                    "receive": float(receive_ms),
                    "control": float(control_ms),
                    "viewer_sync": float(viewer_sync_ms),
                },
                "clutch": {
                    "interlock": {side: interlocks[side].state for side in SIDE_NAMES},
                    "active": {side: bool(active[side]) for side in SIDE_NAMES},
                },
                "input": input_sample,
                "arms": arms,
            }
        )
        self.sequence += 1
        self._previous_s = now_s

    def close(self) -> None:
        if not self._stream.closed:
            self._stream.close()

    def _write(self, value: Mapping[str, Any]) -> None:
        self._stream.write(
            json.dumps(value, ensure_ascii=True, allow_nan=False, separators=(",", ":"))
            + "\n"
        )


class MuJoCoTeleopController:
    def __init__(
        self,
        mujoco: Any,
        model: Any,
        data: Any,
        *,
        translation_matrix: np.ndarray,
        orientation_matrix: np.ndarray,
        translation_scale: float,
        rotation_scale: float,
        damping: float,
        orientation_weight: float,
        max_joint_step_rad: float,
        max_cartesian_step_m: float,
        max_orientation_step_rad: float,
        initial_gripper_opening: float = 0.42,
    ):
        self.mujoco = mujoco
        self.model = model
        self.data = data
        self.translation_matrix = np.asarray(translation_matrix, dtype=np.float64)
        self.orientation_matrix = np.asarray(orientation_matrix, dtype=np.float64)
        self.translation_scale = float(translation_scale)
        self.rotation_scale = float(rotation_scale)
        self.damping = float(damping)
        self.orientation_weight = float(orientation_weight)
        self.max_joint_step_rad = float(max_joint_step_rad)
        self.max_cartesian_step_m = float(max_cartesian_step_m)
        self.max_orientation_step_rad = float(max_orientation_step_rad)
        self.input_anchors: dict[str, np.ndarray | None] = {
            side: None for side in SIDE_NAMES
        }
        self.robot_anchors: dict[str, np.ndarray | None] = {
            side: None for side in SIDE_NAMES
        }
        self.previous_active = {side: False for side in SIDE_NAMES}
        if not 0.0 <= float(initial_gripper_opening) <= 1.0:
            raise ValueError("initial_gripper_opening must be in 0..1")
        self.gripper_openings = {
            side: float(initial_gripper_opening) for side in SIDE_NAMES
        }
        self.site_ids = {
            arm: _required_id(
                mujoco,
                model,
                mujoco.mjtObj.mjOBJ_SITE,
                f"{arm}_tacclaw_tcp",
            )
            for arm in ARM_NAMES
        }
        self.qpos_addresses: dict[str, np.ndarray] = {}
        self.dof_addresses: dict[str, np.ndarray] = {}
        self.joint_ranges: dict[str, np.ndarray] = {}
        for arm in ARM_NAMES:
            joint_ids = np.asarray(
                [
                    _required_id(
                        mujoco,
                        model,
                        mujoco.mjtObj.mjOBJ_JOINT,
                        f"{arm}_joint{index}",
                    )
                    for index in range(1, 8)
                ],
                dtype=int,
            )
            self.qpos_addresses[arm] = model.jnt_qposadr[joint_ids].copy()
            self.dof_addresses[arm] = model.jnt_dofadr[joint_ids].copy()
            self.joint_ranges[arm] = model.jnt_range[joint_ids].copy()
        _set_gripper_opening(mujoco, model, "left", initial_gripper_opening)
        _set_gripper_opening(mujoco, model, "right", initial_gripper_opening)
        mujoco.mj_forward(model, data)

    def release(self) -> None:
        self.input_anchors = {side: None for side in SIDE_NAMES}
        self.robot_anchors = {side: None for side in SIDE_NAMES}
        self.previous_active = {side: False for side in SIDE_NAMES}

    def step(
        self,
        sample: DataMasterSample,
        *,
        active: dict[str, bool],
    ) -> TeleopStatus:
        input_poses = {
            "left": _wire_pose_transform(sample.left_pose),
            "right": _wire_pose_transform(sample.right_pose),
        }
        position_errors: dict[str, float] = {}
        orientation_errors: dict[str, float] = {}
        joint_steps: dict[str, tuple[float, ...]] = {}
        jacobian_conditions: dict[str, float | None] = {}
        joint_step_limited: dict[str, tuple[bool, ...]] = {}
        joint_limit_hits: dict[str, tuple[bool, ...]] = {}
        for side in SIDE_NAMES:
            arm = SIDE_TO_ARM[side]
            if not active[side]:
                self.input_anchors[side] = None
                self.robot_anchors[side] = None
                continue
            if not self.previous_active[side]:
                self.input_anchors[side] = input_poses[side].copy()
                self.robot_anchors[side] = self._tcp_transform(arm)
            input_anchor = self.input_anchors[side]
            robot_anchor = self.robot_anchors[side]
            if input_anchor is None or robot_anchor is None:
                raise RuntimeError(f"{side} clutch is active without an anchor")
            target = _retarget_from_anchor(
                robot_anchor,
                input_anchor,
                input_poses[side],
                translation_matrix=self.translation_matrix,
                orientation_matrix=self.orientation_matrix,
                translation_scale=self.translation_scale,
                rotation_scale=self.rotation_scale,
            )
            (
                position_error,
                orientation_error,
                joint_step,
                jacobian_condition,
                step_limited,
                limit_hits,
            ) = self._solve_arm(arm, target)
            position_errors[arm] = position_error
            orientation_errors[arm] = math.degrees(orientation_error)
            joint_steps[arm] = tuple(float(value) for value in joint_step)
            jacobian_conditions[arm] = jacobian_condition
            joint_step_limited[arm] = tuple(bool(value) for value in step_limited)
            joint_limit_hits[arm] = tuple(bool(value) for value in limit_hits)

        triggers = {"left": sample.left_trigger, "right": sample.right_trigger}
        for side in SIDE_NAMES:
            if active[side]:
                self.gripper_openings[side] = 1.0 - float(triggers[side])
            _set_gripper_opening(
                self.mujoco,
                self.model,
                side,
                self.gripper_openings[side],
            )
        self.previous_active = {side: bool(active[side]) for side in SIDE_NAMES}
        self.data.qvel[:] = 0.0
        self.mujoco.mj_forward(self.model, self.data)
        return TeleopStatus(
            active_sides=tuple(side for side in SIDE_NAMES if active[side]),
            gripper_openings=(
                self.gripper_openings["left"],
                self.gripper_openings["right"],
            ),
            position_errors_m=position_errors,
            orientation_errors_deg=orientation_errors,
            joint_steps_model_rad=joint_steps,
            jacobian_conditions=jacobian_conditions,
            joint_step_limited=joint_step_limited,
            joint_limit_hits=joint_limit_hits,
        )

    def _tcp_transform(self, arm: str) -> np.ndarray:
        site_id = self.site_ids[arm]
        result = np.eye(4, dtype=np.float64)
        result[:3, :3] = self.data.site_xmat[site_id].reshape(3, 3)
        result[:3, 3] = self.data.site_xpos[site_id]
        return result

    def _solve_arm(
        self, arm: str, target: np.ndarray
    ) -> tuple[float, float, np.ndarray, float | None, np.ndarray, np.ndarray]:
        current = self._tcp_transform(arm)
        raw_position_error = target[:3, 3] - current[:3, 3]
        raw_rotation_error = _rotation_vector(target[:3, :3] @ current[:3, :3].T)
        position_error = float(np.linalg.norm(raw_position_error))
        orientation_error = float(np.linalg.norm(raw_rotation_error))
        position_step = _bounded_vector(raw_position_error, self.max_cartesian_step_m)
        rotation_step = _bounded_vector(raw_rotation_error, self.max_orientation_step_rad)

        jacobian_position = np.zeros((3, self.model.nv), dtype=np.float64)
        jacobian_rotation = np.zeros((3, self.model.nv), dtype=np.float64)
        self.mujoco.mj_jacSite(
            self.model,
            self.data,
            jacobian_position,
            jacobian_rotation,
            self.site_ids[arm],
        )
        dof_addresses = self.dof_addresses[arm]
        jacobian = np.vstack(
            (jacobian_position[:, dof_addresses], jacobian_rotation[:, dof_addresses])
        )
        task_error = np.concatenate((position_step, rotation_step))
        jacobian[3:] *= self.orientation_weight
        task_error[3:] *= self.orientation_weight
        regularized = jacobian @ jacobian.T + np.eye(6) * self.damping**2
        raw_joint_step = jacobian.T @ np.linalg.solve(regularized, task_error)
        step_limited = np.abs(raw_joint_step) > self.max_joint_step_rad + 1.0e-12
        joint_step = _bounded_vector(
            raw_joint_step, self.max_joint_step_rad, max_norm=False
        )
        jacobian_condition = float(np.linalg.cond(jacobian))
        if not math.isfinite(jacobian_condition):
            jacobian_condition = None

        qpos_addresses = self.qpos_addresses[arm]
        next_qpos = self.data.qpos[qpos_addresses] + joint_step
        limits = self.joint_ranges[arm]
        clipped_qpos = np.clip(next_qpos, limits[:, 0], limits[:, 1])
        limit_hits = np.abs(clipped_qpos - next_qpos) > 1.0e-12
        self.data.qpos[qpos_addresses] = clipped_qpos
        self.mujoco.mj_forward(self.model, self.data)
        return (
            position_error,
            orientation_error,
            joint_step,
            jacobian_condition,
            step_limited,
            limit_hits,
        )


def _required_id(mujoco: Any, model: Any, object_type: Any, name: str) -> int:
    object_id = mujoco.mj_name2id(model, object_type, name)
    if object_id < 0:
        raise RuntimeError(f"MuJoCo object is missing: {name}")
    return int(object_id)


def _wire_pose_transform(values: Sequence[float]) -> np.ndarray:
    vector = np.asarray(values, dtype=np.float64)
    if vector.shape != (7,) or not np.all(np.isfinite(vector)):
        raise ValueError("DataMaster pose must contain seven finite values")
    quaternion = vector[3:]
    quaternion /= np.linalg.norm(quaternion)
    w, x, y, z = quaternion
    result = np.eye(4, dtype=np.float64)
    result[:3, :3] = np.asarray(
        [
            [1.0 - 2.0 * (y * y + z * z), 2.0 * (x * y - z * w), 2.0 * (x * z + y * w)],
            [2.0 * (x * y + z * w), 1.0 - 2.0 * (x * x + z * z), 2.0 * (y * z - x * w)],
            [2.0 * (x * z - y * w), 2.0 * (y * z + x * w), 1.0 - 2.0 * (x * x + y * y)],
        ]
    )
    result[:3, 3] = vector[:3]
    return result


def _quaternion_matrix(quaternion: Sequence[float]) -> np.ndarray:
    w, x, y, z = np.asarray(quaternion, dtype=np.float64)
    return np.asarray(
        [
            [1.0 - 2.0 * (y * y + z * z), 2.0 * (x * y - z * w), 2.0 * (x * z + y * w)],
            [2.0 * (x * y + z * w), 1.0 - 2.0 * (x * x + z * z), 2.0 * (y * z - x * w)],
            [2.0 * (x * z - y * w), 2.0 * (y * z + x * w), 1.0 - 2.0 * (x * x + y * y)],
        ]
    )


TACCLAW_TO_LINK7_ROTATION = _quaternion_matrix(
    [0.5, -0.5, 0.5, -0.5]
) @ _quaternion_matrix([math.sqrt(0.5), 0.0, 0.0, math.sqrt(0.5)])


def _tacclaw_point_to_link7(point: np.ndarray) -> np.ndarray:
    return TACCLAW_TO_LINK7_TRANSLATION + TACCLAW_TO_LINK7_ROTATION @ np.asarray(
        point, dtype=np.float64
    )


def _retarget_from_anchor(
    robot_anchor: np.ndarray,
    input_anchor: np.ndarray,
    input_current: np.ndarray,
    *,
    translation_matrix: np.ndarray,
    orientation_matrix: np.ndarray,
    translation_scale: float,
    rotation_scale: float,
) -> np.ndarray:
    result = robot_anchor.copy()
    result[:3, 3] += (
        translation_matrix
        @ (input_current[:3, 3] - input_anchor[:3, 3])
        * translation_scale
    )
    input_delta = input_current[:3, :3] @ input_anchor[:3, :3].T
    world_delta = orientation_matrix @ input_delta @ orientation_matrix.T
    scaled_delta = _rotation_matrix(_rotation_vector(world_delta) * rotation_scale)
    result[:3, :3] = scaled_delta @ robot_anchor[:3, :3]
    return result


def _rotation_vector(rotation: np.ndarray) -> np.ndarray:
    matrix = np.asarray(rotation, dtype=np.float64).reshape(3, 3)
    cosine = float(np.clip((np.trace(matrix) - 1.0) * 0.5, -1.0, 1.0))
    angle = math.acos(cosine)
    if angle < 1.0e-8:
        return np.zeros(3, dtype=np.float64)
    if math.pi - angle < 1.0e-5:
        diagonal = np.maximum((np.diag(matrix) + 1.0) * 0.5, 0.0)
        axis = np.sqrt(diagonal)
        axis[1] = math.copysign(axis[1], matrix[0, 1] + matrix[1, 0])
        axis[2] = math.copysign(axis[2], matrix[0, 2] + matrix[2, 0])
        norm = float(np.linalg.norm(axis))
        return np.asarray([1.0, 0.0, 0.0]) * angle if norm < 1.0e-8 else axis / norm * angle
    axis = np.asarray(
        [
            matrix[2, 1] - matrix[1, 2],
            matrix[0, 2] - matrix[2, 0],
            matrix[1, 0] - matrix[0, 1],
        ]
    ) / (2.0 * math.sin(angle))
    return axis * angle


def _rotation_matrix(rotation_vector: np.ndarray) -> np.ndarray:
    vector = np.asarray(rotation_vector, dtype=np.float64).reshape(3)
    angle = float(np.linalg.norm(vector))
    if angle < 1.0e-8:
        return np.eye(3, dtype=np.float64)
    x, y, z = vector / angle
    skew = np.asarray([[0.0, -z, y], [z, 0.0, -x], [-y, x, 0.0]])
    return np.eye(3) + math.sin(angle) * skew + (1.0 - math.cos(angle)) * (skew @ skew)


def _bounded_vector(
    vector: np.ndarray,
    maximum: float,
    *,
    max_norm: bool = True,
) -> np.ndarray:
    result = np.asarray(vector, dtype=np.float64).copy()
    magnitude = float(np.linalg.norm(result) if max_norm else np.max(np.abs(result)))
    if magnitude > maximum:
        result *= maximum / magnitude
    return result


def _demo_pose(
    x: float,
    y: float,
    z: float,
    *,
    axis: tuple[float, float, float],
    angle: float,
) -> tuple[float, ...]:
    unit_axis = np.asarray(axis, dtype=np.float64)
    unit_axis /= np.linalg.norm(unit_axis)
    sine = math.sin(angle / 2.0)
    return (
        x,
        y,
        z,
        math.cos(angle / 2.0),
        *(unit_axis * sine),
    )


def _set_capsule_fromto(
    mujoco: Any,
    model: Any,
    name: str,
    start: np.ndarray,
    end: np.ndarray,
    radius: float,
) -> None:
    geom_id = _required_id(mujoco, model, mujoco.mjtObj.mjOBJ_GEOM, name)
    direction = np.asarray(end, dtype=np.float64) - np.asarray(start, dtype=np.float64)
    length = float(np.linalg.norm(direction))
    if length <= 1.0e-8:
        raise ValueError(f"capsule {name} has zero length")
    # MuJoCo's compiled ``fromto`` capsule convention stores the local
    # capsule axis along the reverse endpoint direction. Capsules are
    # geometrically symmetric, but retaining this orientation keeps runtime
    # lighting identical to the static assembly preview.
    unit = -direction / length
    z_axis = np.asarray([0.0, 0.0, 1.0])
    dot = float(np.clip(np.dot(z_axis, unit), -1.0, 1.0))
    if dot < -1.0 + 1.0e-8:
        quaternion = np.asarray([0.0, 1.0, 0.0, 0.0])
    else:
        quaternion = np.concatenate(([1.0 + dot], np.cross(z_axis, unit)))
        quaternion /= np.linalg.norm(quaternion)
    model.geom_pos[geom_id] = (start + end) * 0.5
    model.geom_quat[geom_id] = quaternion
    model.geom_size[geom_id, 0] = float(radius)
    model.geom_size[geom_id, 1] = length * 0.5


def _set_gripper_opening(mujoco: Any, model: Any, side: str, opening: float) -> None:
    arm = SIDE_TO_ARM[side]
    normalized = min(1.0, max(0.0, float(opening)))
    tip_center_x = 0.012 + 0.0382 * normalized
    for sign, finger_side in ((-1.0, "negative"), (1.0, "positive")):
        base = np.asarray([sign * 0.022, 0.0, 0.082])
        middle = np.asarray([sign * (0.024 + 0.45 * tip_center_x), 0.0, 0.132])
        tip = np.asarray([sign * tip_center_x, 0.0, 0.1825])
        inner_shift = np.asarray([-sign * 0.010, -0.001, 0.0])
        prefix = f"{arm}_tacclaw_{finger_side}"
        _set_capsule_fromto(
            mujoco,
            model,
            f"{prefix}_finger_lower",
            _tacclaw_point_to_link7(base),
            _tacclaw_point_to_link7(middle),
            0.015,
        )
        _set_capsule_fromto(
            mujoco,
            model,
            f"{prefix}_finger_upper",
            _tacclaw_point_to_link7(middle),
            _tacclaw_point_to_link7(tip),
            0.012,
        )
        _set_capsule_fromto(
            mujoco,
            model,
            f"{prefix}_tactile_lower",
            _tacclaw_point_to_link7(base + inner_shift),
            _tacclaw_point_to_link7(middle + inner_shift),
            0.0055,
        )
        _set_capsule_fromto(
            mujoco,
            model,
            f"{prefix}_tactile_upper",
            _tacclaw_point_to_link7(middle + inner_shift),
            _tacclaw_point_to_link7(tip + inner_shift),
            0.005,
        )


def _status_line(
    status: TeleopStatus | None,
    interlocks: dict[str, ClutchInterlock],
    *,
    age_s: float | None,
    discarded: int,
) -> str:
    active = "none" if status is None or not status.active_sides else "+".join(status.active_sides)
    openings = (1.0, 1.0) if status is None else status.gripper_openings
    age = "no input" if age_s is None else f"input {age_s * 1000.0:.0f} ms"
    return (
        f"active={active:<10} clutch={interlocks['left'].state}/"
        f"{interlocks['right'].state} claws={openings[0] * 100:3.0f}%/"
        f"{openings[1] * 100:3.0f}% {age} discarded={discarded}"
    )


def _run_loop(
    args: argparse.Namespace,
    source: DataMasterReceiver | XRobotToolkitReceiver | DemoSource,
    controller: Any,
    viewer: Any | None,
    logger: MuJoCoTeleopJsonlLogger | None = None,
) -> None:
    interlocks = {
        side: ClutchInterlock(release_stable_s=args.release_stable_s)
        for side in SIDE_NAMES
    }
    period_s = 1.0 / args.control_hz
    started_s = time.monotonic()
    next_tick_s = started_s
    last_rx_s: float | None = None
    latest_sample: DataMasterSample | None = None
    input_faulted = True
    last_status: TeleopStatus | None = None
    next_status_s = started_s

    while viewer is None or viewer.is_running():
        now_s = time.monotonic()
        if args.duration_s > 0.0 and now_s - started_s >= args.duration_s:
            break
        active = {side: False for side in SIDE_NAMES}
        receive_started_s = time.perf_counter()
        try:
            sample, received_s = source.latest(now_s)
        except ValueError as exc:
            sample, received_s = None, None
            latest_sample = None
            last_rx_s = None
            if not input_faulted:
                print(f"{args.input} input rejected: {exc}", file=sys.stderr)
            input_faulted = True
            for interlock in interlocks.values():
                interlock.fault()
            controller.release()
        receive_ms = (time.perf_counter() - receive_started_s) * 1000.0
        sample_received = sample is not None and received_s is not None
        if sample is not None and received_s is not None:
            latest_sample = sample
            last_rx_s = received_s

        observation_s = time.monotonic()
        fresh = (
            latest_sample is not None
            and last_rx_s is not None
            and observation_s - last_rx_s <= args.input_timeout_s
        )
        control_started_s = time.perf_counter()
        if not fresh:
            if not input_faulted:
                for interlock in interlocks.values():
                    interlock.fault()
                controller.release()
            input_faulted = True
            last_status = None
        else:
            input_faulted = False
            assert latest_sample is not None
            active = {
                "left": interlocks["left"].update(
                    latest_sample.left_clutch, now_s=observation_s
                ),
                "right": interlocks["right"].update(
                    latest_sample.right_clutch, now_s=observation_s
                ),
            }
            last_status = controller.step(latest_sample, active=active)
        control_ms = (time.perf_counter() - control_started_s) * 1000.0

        viewer_started_s = time.perf_counter()
        if viewer is not None:
            viewer.sync()
        viewer_sync_ms = (time.perf_counter() - viewer_started_s) * 1000.0
        record_s = time.monotonic()
        if logger is not None:
            logger.record(
                now_s=record_s,
                sample=latest_sample,
                sample_received=sample_received,
                received_s=last_rx_s,
                fresh=fresh,
                active=active,
                interlocks=interlocks,
                status=last_status,
                discarded_messages=source.discarded_messages,
                receive_ms=receive_ms,
                control_ms=control_ms,
                viewer_sync_ms=viewer_sync_ms,
            )
        if record_s >= next_status_s:
            age_s = None if last_rx_s is None else record_s - last_rx_s
            print(
                _status_line(
                    last_status,
                    interlocks,
                    age_s=age_s,
                    discarded=source.discarded_messages,
                )
            )
            next_status_s = record_s + 1.0
        next_tick_s += period_s
        delay_s = next_tick_s - time.monotonic()
        if delay_s > 0.0:
            time.sleep(delay_s)
        else:
            next_tick_s = time.monotonic()


def main() -> None:
    args = _arguments()
    os.environ.setdefault("MUJOCO_GL", "glfw")
    import mujoco

    model, offsets, signs = _build_model(
        mujoco,
        args.urdf,
        base_spacing_m=args.base_spacing_m,
        opening=1.0,
    )
    data = mujoco.MjData(model)
    _set_joint_pose(
        mujoco,
        model,
        data,
        {"arm_a": args.arm_a.copy(), "arm_b": args.arm_b.copy()},
        offsets,
        signs,
    )
    controller = MuJoCoTeleopController(
        mujoco,
        model,
        data,
        translation_matrix=args.translation_matrix,
        orientation_matrix=args.orientation_matrix,
        translation_scale=args.translation_scale,
        rotation_scale=args.rotation_scale,
        damping=args.damping,
        orientation_weight=args.orientation_weight,
        max_joint_step_rad=math.radians(args.max_joint_step_deg),
        max_cartesian_step_m=args.max_cartesian_step_m,
        max_orientation_step_rad=math.radians(args.max_orientation_step_deg),
        initial_gripper_opening=args.initial_gripper_opening,
    )
    logger = None
    if args.log_jsonl is not None:
        logger = MuJoCoTeleopJsonlLogger(
            args.log_jsonl,
            args=args,
            controller=controller,
            joint_offsets=offsets,
            joint_signs=signs,
        )
    source: DataMasterReceiver | XRobotToolkitReceiver | DemoSource
    if args.demo:
        source = DemoSource()
        mode = "synthetic demo"
    elif args.input == "xrobotoolkit":
        source = XRobotToolkitReceiver(
            sdk_library_path=args.xr_sdk_library,
            publish_hz=args.xr_publish_hz,
            source_gap_timeout_s=args.xr_source_gap_timeout_s,
            grip_threshold=args.xr_grip_threshold,
        )
        mode = "native Quest controllers (latest raw samples)"
    else:
        source = DataMasterReceiver(
            endpoint=args.endpoint,
            receive_hwm=args.receive_hwm,
        )
        mode = args.endpoint
    print(f"MuJoCo-only teleop input: {mode}")
    print("Controller/model: same DataMaster MuJoCo path; input receiver only changed")
    print(f"Mapping: {args.input} left -> arm_b/left claw; right -> arm_a/right claw")
    if args.input == "xrobotoolkit" and not args.demo:
        print("Quest poses are headset-yaw-relative before the fixed axis mapping")
    print("Both sides use the same operator-to-lab_world axis mapping")
    print("Release both clutches for 0.25 s after startup or an input gap.")
    if logger is not None:
        print(f"Per-frame diagnostic log: {logger.path}")
    try:
        if args.headless:
            _run_loop(args, source, controller, viewer=None, logger=logger)
        else:
            import mujoco.viewer

            with mujoco.viewer.launch_passive(model, data) as viewer:
                viewer.cam.lookat[:] = [0.0, 0.0, -0.42]
                viewer.cam.azimuth = 145.0
                viewer.cam.elevation = -14.0
                viewer.cam.distance = 1.75
                _run_loop(args, source, controller, viewer, logger=logger)
    except KeyboardInterrupt:
        pass
    finally:
        source.close()
        if logger is not None:
            logger.close()


if __name__ == "__main__":
    main()
