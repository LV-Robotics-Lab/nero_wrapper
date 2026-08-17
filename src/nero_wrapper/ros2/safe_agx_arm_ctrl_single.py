from __future__ import annotations

import math
import threading
import time

import rclpy
from agx_arm_ctrl.agx_arm_ctrl_single_node import AgxArmRosNode
from agx_arm_msgs.msg import MoveMITMsg
from rclpy.executors import ExternalShutdownException
from rclpy.qos import HistoryPolicy, QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import JointState
from std_srvs.srv import SetBool

from nero_wrapper.joint_targets import (
    complete_joint_positions,
    complete_joint_velocities,
    cpv_position_command_key,
    send_complete_cpv_positions,
    send_complete_cpv_velocities,
    send_complete_move_j,
)
from nero_wrapper.source_freshness import SourceObservation, SourceStampTracker


def _trace_integer(label: str, key: str) -> int | None:
    prefix = "nero_trace_v1;"
    if not isinstance(label, str) or not label.startswith(prefix):
        return None
    marker = f"{key}="
    for item in label.split(";")[1:]:
        if not item.startswith(marker):
            continue
        try:
            value = int(item[len(marker) :])
        except ValueError:
            return None
        return value if value > 0 else None
    return None


def _trace_with_times(label: str, **values: int) -> str:
    prefix = "nero_trace_v1;"
    if not isinstance(label, str) or not label.startswith(prefix):
        return ""
    keys = set(values)
    fields = [
        item
        for item in label.split(";")
        if "=" not in item or item.split("=", 1)[0] not in keys
    ]
    fields.extend(
        f"{key}={int(value)}" for key, value in values.items() if value > 0
    )
    return ";".join(fields)


class _TraceEchoPublisher:
    """Echo the last completely forwarded command trace on joint feedback."""

    def __init__(self, publisher, node) -> None:
        self._publisher = publisher
        self._node = node

    def __getattr__(self, name: str):
        return getattr(self._publisher, name)

    def publish(self, message: JointState) -> None:
        received_ns = time.monotonic_ns()
        source_stamp_ns = (
            int(message.header.stamp.sec) * 1_000_000_000
            + int(message.header.stamp.nanosec)
        )
        observation = self._node._joint_feedback_source_tracker.observe(
            source_stamp_ns,
            received_ns,
        )
        if observation is not SourceObservation.FRESH:
            # The SDK getters return their newest cached object.  Publishing it
            # again would make downstream receipt-time watchdogs believe that a
            # dead CAN feedback stream is healthy.
            return
        label = self._node._last_forwarded_cpv_trace_label
        if label:
            message.header.frame_id = _trace_with_times(
                label,
                fpub=received_ns,
            )
        self._publisher.publish(message)


class SafeAgxArmRosNode(AgxArmRosNode):
    """Vendor driver with an explicitly stoppable feedback publisher thread."""

    def _declare_parameters(self) -> None:
        super()._declare_parameters()
        self.declare_parameter("cpv_speed_percent", 100)
        self.declare_parameter("cpv_velocity_limit_rad_s", 1.5)
        self.declare_parameter("cpv_velocity_timeout_s", 0.10)
        self.declare_parameter("cpv_feedback_source_timeout_s", 0.05)
        self.declare_parameter("cpv_input_trace_timeout_s", 0.10)
        self.declare_parameter("cpv_require_fresh_trace", True)
        self.declare_parameter("move_j_mode_handover_timeout_s", 0.5)
        self.declare_parameter("joint_pub_rate", 200)

    def _load_parameters(self) -> None:
        super()._load_parameters()
        self.cpv_speed_percent = self.get_parameter("cpv_speed_percent").value
        if (
            not isinstance(self.cpv_speed_percent, int)
            or isinstance(self.cpv_speed_percent, bool)
            or not 1 <= self.cpv_speed_percent <= 100
        ):
            raise ValueError("cpv_speed_percent must be an integer from 1 to 100")
        self.cpv_velocity_limit_rad_s = float(
            self.get_parameter("cpv_velocity_limit_rad_s").value
        )
        if (
            not math.isfinite(self.cpv_velocity_limit_rad_s)
            or self.cpv_velocity_limit_rad_s <= 0.0
            or self.cpv_velocity_limit_rad_s > 5.0
        ):
            raise ValueError("cpv_velocity_limit_rad_s must be in (0, 5] rad/s")
        self.cpv_velocity_timeout_s = float(
            self.get_parameter("cpv_velocity_timeout_s").value
        )
        if (
            not math.isfinite(self.cpv_velocity_timeout_s)
            or self.cpv_velocity_timeout_s <= 0.0
            or self.cpv_velocity_timeout_s > 1.0
        ):
            raise ValueError("cpv_velocity_timeout_s must be in (0, 1] seconds")
        self.cpv_feedback_source_timeout_s = float(
            self.get_parameter("cpv_feedback_source_timeout_s").value
        )
        if (
            not math.isfinite(self.cpv_feedback_source_timeout_s)
            or self.cpv_feedback_source_timeout_s <= 0.0
            or self.cpv_feedback_source_timeout_s > self.cpv_velocity_timeout_s
        ):
            raise ValueError(
                "cpv_feedback_source_timeout_s must be positive and no larger "
                "than cpv_velocity_timeout_s"
            )
        self.cpv_input_trace_timeout_s = float(
            self.get_parameter("cpv_input_trace_timeout_s").value
        )
        if (
            not math.isfinite(self.cpv_input_trace_timeout_s)
            or self.cpv_input_trace_timeout_s <= 0.0
            or self.cpv_input_trace_timeout_s > 1.0
        ):
            raise ValueError("cpv_input_trace_timeout_s must be in (0, 1] seconds")
        self.cpv_require_fresh_trace = self.get_parameter(
            "cpv_require_fresh_trace"
        ).value
        if not isinstance(self.cpv_require_fresh_trace, bool):
            raise ValueError("cpv_require_fresh_trace must be true or false")
        self.move_j_mode_handover_timeout_s = float(
            self.get_parameter("move_j_mode_handover_timeout_s").value
        )
        if (
            not math.isfinite(self.move_j_mode_handover_timeout_s)
            or self.move_j_mode_handover_timeout_s <= 0.0
            or self.move_j_mode_handover_timeout_s > 2.0
        ):
            raise ValueError(
                "move_j_mode_handover_timeout_s must be in (0, 2] seconds"
            )
        self.joint_pub_rate = int(self.get_parameter("joint_pub_rate").value)
        if (
            self.joint_pub_rate < int(self.pub_rate)
            or self.joint_pub_rate > 500
        ):
            raise ValueError("joint_pub_rate must be between pub_rate and 500Hz")

    def _log_parameters(self) -> None:
        super()._log_parameters()
        self.get_logger().info(
            f"cpv_speed_percent: {self.cpv_speed_percent}; firmware move_j "
            f"park speed remains {self.speed_percent}%; MOVE_J handover timeout "
            f"is {self.move_j_mode_handover_timeout_s:.2f}s; CPV velocity limit "
            f"is {self.cpv_velocity_limit_rad_s:.3f}rad/s with a "
            f"{self.cpv_velocity_timeout_s:.3f}s command watchdog, "
            f"{self.cpv_feedback_source_timeout_s:.3f}s encoder-source watchdog, "
            f"{self.cpv_input_trace_timeout_s:.3f}s upstream trace watchdog "
            f"(required={self.cpv_require_fresh_trace}); joint "
            f"feedback {self.joint_pub_rate}Hz / full telemetry {self.pub_rate}Hz"
        )

    def __init__(self) -> None:
        # AgxArmRosNode.__init__ starts a thread using self._publish_thread, so
        # the event must exist before entering the vendor constructor.
        self._publisher_stop = threading.Event()
        self._motion_command_lock = threading.RLock()
        self._joint_feedback_source_tracker = SourceStampTracker()
        self._motion_fault_reason = ""
        self._cpv_stream_kind: str | None = None
        self._last_cpv_velocity_received_at: float | None = None
        self._cpv_velocity_zeroed = True
        self._cpv_velocity_watchdog_stops = 0
        self._cpv_velocity_received_count = 0
        self._cpv_velocity_forwarded_count = 0
        self._cpv_velocity_stale_dropped_count = 0
        self._last_cpv_velocity_stamp_ns: int | None = None
        self._last_cpv_velocity_command_monotonic_ns: int | None = None
        self._cpv_velocity_stats_window_started: float | None = None
        self._cpv_velocity_stats_window_received = 0
        self._cpv_velocity_stats_window_forwarded = 0
        self._cpv_velocity_stats_window_stale_dropped = 0
        self._cpv_velocity_stats_window_watchdog_stops = 0
        self._cpv_velocity_stats_message_age_sum_ms = 0.0
        self._cpv_velocity_stats_message_age_max_ms = 0.0
        self._cpv_velocity_stats_message_age_samples = 0
        self._cpv_velocity_stats_send_sum_ms = 0.0
        self._cpv_velocity_stats_send_max_ms = 0.0
        self._cpv_velocity_stats_send_samples = 0
        self._cpv_velocity_stats_relay_age_sum_ms = 0.0
        self._cpv_velocity_stats_relay_age_max_ms = 0.0
        self._cpv_velocity_stats_relay_age_samples = 0
        self._last_cpv_input_sequence: int | None = None
        self._last_accepted_cpv_input_sequence: int | None = None
        self._last_forwarded_cpv_trace_label = ""
        self.publisher_thread_alive = False
        self.publisher_thread_fault_reason = ""
        self._enabled_by_this_process = False
        super().__init__()
        self.joint_states_pub = _TraceEchoPublisher(self.joint_states_pub, self)
        self._cpv_mode_active = False
        self._last_cpv_position_key: tuple[int, ...] | None = None
        self._cpv_received_count = 0
        self._cpv_forwarded_count = 0
        self._cpv_suppressed_count = 0
        self._cpv_stats_window_started: float | None = None
        self._cpv_stats_window_received = 0
        self._cpv_stats_window_forwarded = 0
        self._cpv_stats_window_suppressed = 0
        self._cpv_stats_message_age_sum_ms = 0.0
        self._cpv_stats_message_age_max_ms = 0.0
        self._cpv_stats_message_age_samples = 0
        self._cpv_stats_send_sum_ms = 0.0
        self._cpv_stats_send_max_ms = 0.0
        self._cpv_stats_send_samples = 0
        self._move_j_mode_active = False
        self._move_j_command_count = 0
        cpv_qos = QoSProfile(
            history=HistoryPolicy.KEEP_LAST,
            depth=1,
            reliability=ReliabilityPolicy.BEST_EFFORT,
        )
        self._cpv_position_subscription = self.create_subscription(
            JointState,
            "control/move_cpv_pos",
            self._move_cpv_pos_callback,
            cpv_qos,
        )
        self._cpv_velocity_subscription = self.create_subscription(
            JointState,
            "control/move_cpv_vel",
            self._move_cpv_vel_callback,
            cpv_qos,
        )

    def _enable_callback(
        self,
        request: SetBool.Request,
        response: SetBool.Response,
    ) -> SetBool.Response:
        with self._motion_command_lock:
            if request.data and self._motion_fault_reason:
                response.success = False
                response.message = (
                    "Arm enable rejected: driver motion fault is latched "
                    f"({self._motion_fault_reason}); restart required"
                )
                return response
            if not request.data:
                self._stop_cpv_velocity_locked("motor disable")
            result = super()._enable_callback(request, response)
            if result.success:
                self._enabled_by_this_process = bool(request.data)
                if not request.data:
                    self._cpv_mode_active = False
                    self._cpv_stream_kind = None
                    self._last_cpv_position_key = None
                    self._last_cpv_velocity_received_at = None
                    self._last_cpv_velocity_stamp_ns = None
                    self._cpv_velocity_zeroed = True
                    self._last_forwarded_cpv_trace_label = ""
                    self._move_j_mode_active = False
            return result

    def _control_gate_callback(self, request, response):
        with self._motion_command_lock:
            if request.data and self._motion_fault_reason:
                response.success = False
                response.message = (
                    "External control gate remains closed: driver motion fault "
                    f"is latched ({self._motion_fault_reason})"
                )
                return response
            if request.data and not self._joint_feedback_source_tracker.is_fresh(
                time.monotonic_ns(),
                self.cpv_feedback_source_timeout_s,
            ):
                response.success = False
                response.message = (
                    "External control gate remains closed: no fresh unique "
                    "encoder source"
                )
                return response
            if not request.data:
                self._stop_cpv_velocity_locked("external control gate close")
            return super()._control_gate_callback(request, response)

    def _trip_motion_fault_locked(self, reason: str) -> None:
        """Latch a driver fault after attempting the only safe CPV overwrite."""

        if self._motion_fault_reason:
            return
        self._motion_fault_reason = reason
        self._stop_cpv_velocity_locked(reason)
        self.control_enabled = False
        self.control_ready = False
        self.get_logger().error(
            f"NERO motion path failed closed: {reason}; control gate closed and "
            "driver shutdown requested so the arm can be disabled"
        )
        self._publisher_stop.set()
        if rclpy.ok():
            rclpy.shutdown()

    def _check_can_control(self) -> bool:
        with self._motion_command_lock:
            if self._motion_fault_reason:
                return False
            if self.control_ready:
                try:
                    healthy = self.agx_arm.is_ok() and self._check_arm_ready()
                except Exception as exc:
                    self._trip_motion_fault_locked(
                        f"SDK/CAN health check raised {type(exc).__name__}: {exc}"
                    )
                    return False
                if not healthy:
                    self._trip_motion_fault_locked(
                        "SDK/CAN connection or encoder source became unavailable"
                    )
                    return False
            return super()._check_can_control()

    def _record_cpv_velocity_message_age(
        self,
        msg: JointState,
    ) -> tuple[int | None, float | None]:
        stamp_ns = (
            int(msg.header.stamp.sec) * 1_000_000_000
            + int(msg.header.stamp.nanosec)
        )
        if stamp_ns <= 0:
            return None, None
        age_ms = max(
            0.0,
            (self.get_clock().now().nanoseconds - stamp_ns) / 1_000_000.0,
        )
        self._cpv_velocity_stats_message_age_sum_ms += age_ms
        self._cpv_velocity_stats_message_age_max_ms = max(
            self._cpv_velocity_stats_message_age_max_ms,
            age_ms,
        )
        self._cpv_velocity_stats_message_age_samples += 1
        return stamp_ns, age_ms

    def _record_cpv_velocity_trace_age(
        self,
        msg: JointState,
    ) -> tuple[int | None, int | None, float | None]:
        relay_receive_ns = _trace_integer(msg.header.frame_id, "rrx")
        input_sequence = _trace_integer(msg.header.frame_id, "rseq")
        self._last_cpv_input_sequence = input_sequence
        if relay_receive_ns is None:
            return input_sequence, None, None
        age_ms = max(
            0.0,
            float(time.monotonic_ns() - relay_receive_ns) / 1_000_000.0,
        )
        self._cpv_velocity_stats_relay_age_sum_ms += age_ms
        self._cpv_velocity_stats_relay_age_max_ms = max(
            self._cpv_velocity_stats_relay_age_max_ms,
            age_ms,
        )
        self._cpv_velocity_stats_relay_age_samples += 1
        return input_sequence, relay_receive_ns, age_ms

    def _maybe_log_cpv_velocity_stream_stats(self, now: float) -> None:
        if self._cpv_velocity_stats_window_started is None:
            self._cpv_velocity_stats_window_started = now
            return
        elapsed = now - self._cpv_velocity_stats_window_started
        if elapsed < 5.0:
            return

        receive_hz = self._cpv_velocity_stats_window_received / elapsed
        if self._cpv_velocity_stats_message_age_samples:
            average_age_ms = (
                self._cpv_velocity_stats_message_age_sum_ms
                / self._cpv_velocity_stats_message_age_samples
            )
            age_summary = (
                f"{average_age_ms:.3f}/"
                f"{self._cpv_velocity_stats_message_age_max_ms:.3f}"
            )
        else:
            age_summary = "n/a"
        if self._cpv_velocity_stats_send_samples:
            average_send_ms = (
                self._cpv_velocity_stats_send_sum_ms
                / self._cpv_velocity_stats_send_samples
            )
            send_summary = (
                f"{average_send_ms:.3f}/"
                f"{self._cpv_velocity_stats_send_max_ms:.3f}"
            )
        else:
            send_summary = "n/a"
        if self._cpv_velocity_stats_relay_age_samples:
            relay_age_summary = (
                f"{self._cpv_velocity_stats_relay_age_sum_ms / self._cpv_velocity_stats_relay_age_samples:.3f}/"
                f"{self._cpv_velocity_stats_relay_age_max_ms:.3f}"
            )
        else:
            relay_age_summary = "n/a"

        self.get_logger().info(
            "CPV velocity latest-stream stats (5s window): "
            f"received={self._cpv_velocity_stats_window_received}, "
            f"forwarded={self._cpv_velocity_stats_window_forwarded}, "
            f"stale_or_out_of_order_dropped="
            f"{self._cpv_velocity_stats_window_stale_dropped}, "
            f"watchdog_stops={self._cpv_velocity_stats_window_watchdog_stops}, "
            f"ingress_hz={receive_hz:.2f}, "
            f"message_age_ms(avg/max)={age_summary}, "
            f"relay_to_driver_ms(avg/max)={relay_age_summary}, "
            f"last_input_sequence={self._last_cpv_input_sequence}, "
            f"seven_joint_send_ms(avg/max)={send_summary}; "
            f"totals received/forwarded/stale_dropped/watchdog_stops="
            f"{self._cpv_velocity_received_count}/"
            f"{self._cpv_velocity_forwarded_count}/"
            f"{self._cpv_velocity_stale_dropped_count}/"
            f"{self._cpv_velocity_watchdog_stops}"
        )

        self._cpv_velocity_stats_window_started = now
        self._cpv_velocity_stats_window_received = 0
        self._cpv_velocity_stats_window_forwarded = 0
        self._cpv_velocity_stats_window_stale_dropped = 0
        self._cpv_velocity_stats_window_watchdog_stops = 0
        self._cpv_velocity_stats_message_age_sum_ms = 0.0
        self._cpv_velocity_stats_message_age_max_ms = 0.0
        self._cpv_velocity_stats_message_age_samples = 0
        self._cpv_velocity_stats_send_sum_ms = 0.0
        self._cpv_velocity_stats_send_max_ms = 0.0
        self._cpv_velocity_stats_send_samples = 0
        self._cpv_velocity_stats_relay_age_sum_ms = 0.0
        self._cpv_velocity_stats_relay_age_max_ms = 0.0
        self._cpv_velocity_stats_relay_age_samples = 0

    def _record_cpv_message_age(self, msg: JointState) -> None:
        stamp_ns = (
            int(msg.header.stamp.sec) * 1_000_000_000
            + int(msg.header.stamp.nanosec)
        )
        if stamp_ns <= 0:
            return
        age_ms = max(
            0.0,
            (self.get_clock().now().nanoseconds - stamp_ns) / 1_000_000.0,
        )
        self._cpv_stats_message_age_sum_ms += age_ms
        self._cpv_stats_message_age_max_ms = max(
            self._cpv_stats_message_age_max_ms,
            age_ms,
        )
        self._cpv_stats_message_age_samples += 1

    def _maybe_log_cpv_stream_stats(self, now: float) -> None:
        if self._cpv_stats_window_started is None:
            self._cpv_stats_window_started = now
            return
        elapsed = now - self._cpv_stats_window_started
        if elapsed < 5.0:
            return

        receive_hz = self._cpv_stats_window_received / elapsed
        if self._cpv_stats_message_age_samples:
            age_average = (
                self._cpv_stats_message_age_sum_ms
                / self._cpv_stats_message_age_samples
            )
            age_summary = (
                f"{age_average:.3f}/{self._cpv_stats_message_age_max_ms:.3f}"
            )
        else:
            age_summary = "n/a"
        if self._cpv_stats_send_samples:
            send_average = (
                self._cpv_stats_send_sum_ms / self._cpv_stats_send_samples
            )
            send_summary = f"{send_average:.3f}/{self._cpv_stats_send_max_ms:.3f}"
        else:
            send_summary = "n/a"

        self.get_logger().info(
            "CPV stream stats (5s window): "
            f"received={self._cpv_stats_window_received}, "
            f"forwarded={self._cpv_stats_window_forwarded}, "
            f"duplicate_targets_suppressed={self._cpv_stats_window_suppressed}, "
            f"ingress_hz={receive_hz:.2f}, "
            f"message_age_ms(avg/max)={age_summary}, "
            f"seven_joint_send_ms(avg/max)={send_summary}; "
            f"totals received/forwarded/suppressed={self._cpv_received_count}/"
            f"{self._cpv_forwarded_count}/{self._cpv_suppressed_count}"
        )

        self._cpv_stats_window_started = now
        self._cpv_stats_window_received = 0
        self._cpv_stats_window_forwarded = 0
        self._cpv_stats_window_suppressed = 0
        self._cpv_stats_message_age_sum_ms = 0.0
        self._cpv_stats_message_age_max_ms = 0.0
        self._cpv_stats_message_age_samples = 0
        self._cpv_stats_send_sum_ms = 0.0
        self._cpv_stats_send_max_ms = 0.0
        self._cpv_stats_send_samples = 0

    def _send_cpv_velocities_locked(self, targets: list[float]) -> float:
        """Send one complete CPV velocity reference while owning the mode lock."""

        send_started = time.monotonic()
        self._cpv_mode_active = send_complete_cpv_velocities(
            self.agx_arm,
            targets,
            mode_active=self._cpv_mode_active,
        )
        return (time.monotonic() - send_started) * 1_000.0

    def _stop_cpv_velocity_locked(self, reason: str) -> None:
        """Overwrite a persistent velocity reference once before leaving/stalling."""

        if self._cpv_stream_kind != "velocity" or self._cpv_velocity_zeroed:
            return
        try:
            self._send_cpv_velocities_locked([0.0] * 7)
        except Exception as exc:
            self.get_logger().error(
                f"Failed to send CPV zero velocity during {reason}: {exc}"
            )
            return
        self._cpv_velocity_zeroed = True
        self._last_forwarded_cpv_trace_label = ""
        self.get_logger().warning(f"CPV velocity reference zeroed: {reason}")

    def _enforce_cpv_velocity_watchdog(self, now: float) -> None:
        with self._motion_command_lock:
            if self._motion_fault_reason:
                return
            if (
                self.control_ready
                and self.enable_flag
                and self.control_enabled
                and not self._joint_feedback_source_tracker.is_fresh(
                    time.monotonic_ns(),
                    self.cpv_feedback_source_timeout_s,
                )
            ):
                age_s = self._joint_feedback_source_tracker.age_s(
                    time.monotonic_ns()
                )
                detail = (
                    "no unique encoder sample"
                    if age_s is None
                    else f"unique encoder age {age_s * 1000.0:.1f}ms"
                )
                self._trip_motion_fault_locked(
                    f"encoder source watchdog expired while motion was authorized "
                    f"({detail})"
                )
                return
            received_at = self._last_cpv_velocity_received_at
            if (
                self._cpv_stream_kind != "velocity"
                or self._cpv_velocity_zeroed
                or (
                    received_at is not None
                    and now - received_at <= self.cpv_velocity_timeout_s
                )
            ):
                return
            before_zeroed = self._cpv_velocity_zeroed
            timeout_detail = (
                "no complete command"
                if received_at is None
                else f"{now - received_at:.3f}s"
            )
            self._stop_cpv_velocity_locked(
                f"command timeout ({timeout_detail})"
            )
            if not before_zeroed and self._cpv_velocity_zeroed:
                self._cpv_velocity_watchdog_stops += 1
                self._cpv_velocity_stats_window_watchdog_stops += 1

    def _move_cpv_vel_callback(self, msg: JointState) -> None:
        """Immediately overwrite the seven-joint CPV velocity reference."""

        driver_receive_ns = time.monotonic_ns()
        if not self._check_can_control():
            return
        if not self.is_nero or not hasattr(self.agx_arm, "move_cpv_vel"):
            self.get_logger().error(
                "CPV velocity commands require NERO firmware 1.12 or newer"
            )
            return
        try:
            targets = complete_joint_velocities(
                msg.name,
                msg.velocity,
                self.arm_joint_names,
            )
        except ValueError as exc:
            with self._motion_command_lock:
                self._trip_motion_fault_locked(
                    f"invalid CPV velocity command: {exc}"
                )
            return
        largest = max(abs(value) for value in targets)
        if largest > self.cpv_velocity_limit_rad_s + 1.0e-9:
            with self._motion_command_lock:
                self._trip_motion_fault_locked(
                    "CPV velocity command exceeded configured limit: "
                    f"{largest:.4f} > {self.cpv_velocity_limit_rad_s:.4f}rad/s"
                )
            return

        received_at = time.monotonic()
        command_is_zero = not any(abs(value) > 1.0e-12 for value in targets)
        self._cpv_velocity_received_count += 1
        self._cpv_velocity_stats_window_received += 1
        stamp_ns, message_age_ms = self._record_cpv_velocity_message_age(msg)
        command_publish_ns = _trace_integer(msg.header.frame_id, "cpub")
        input_sequence, relay_receive_ns, relay_age_ms = (
            self._record_cpv_velocity_trace_age(msg)
        )
        with self._motion_command_lock:
            if not self._check_can_control():
                return
            if (
                not command_is_zero
                and not self._joint_feedback_source_tracker.is_fresh(
                    driver_receive_ns,
                    self.cpv_feedback_source_timeout_s,
                )
            ):
                age_s = self._joint_feedback_source_tracker.age_s(
                    driver_receive_ns
                )
                detail = (
                    "no unique encoder sample"
                    if age_s is None
                    else f"unique encoder age {age_s * 1000.0:.1f}ms"
                )
                self._trip_motion_fault_locked(
                    f"refused nonzero CPV command with stale feedback ({detail})"
                )
                return
            missing_required_trace = (
                not command_is_zero
                and self.cpv_require_fresh_trace
                and (
                    input_sequence is None
                    or relay_receive_ns is None
                    or command_publish_ns is None
                )
            )
            stale_input_trace = (
                not command_is_zero
                and relay_age_ms is not None
                and relay_age_ms > self.cpv_input_trace_timeout_s * 1_000.0
            )
            input_out_of_order = (
                not command_is_zero
                and input_sequence is not None
                and self._last_accepted_cpv_input_sequence is not None
                and input_sequence < self._last_accepted_cpv_input_sequence
            )
            if missing_required_trace or stale_input_trace or input_out_of_order:
                self._cpv_velocity_stale_dropped_count += 1
                self._cpv_velocity_stats_window_stale_dropped += 1
                if missing_required_trace:
                    provenance_reason = "required upstream trace is incomplete"
                elif stale_input_trace:
                    provenance_reason = (
                        f"upstream input trace age {relay_age_ms:.1f}ms exceeds "
                        f"{self.cpv_input_trace_timeout_s * 1000.0:.1f}ms"
                    )
                else:
                    provenance_reason = (
                        f"upstream sequence moved backwards: {input_sequence} < "
                        f"{self._last_accepted_cpv_input_sequence}"
                    )
                self._trip_motion_fault_locked(provenance_reason)
                return
            # Maintained controller and driver share one host monotonic clock.
            # Prefer that trace over ROS wall time so an NTP/clock correction
            # cannot discard every otherwise-current velocity command.
            if command_publish_ns is not None:
                command_age_ms = max(
                    0.0,
                    (driver_receive_ns - command_publish_ns) / 1_000_000.0,
                )
                stale = (
                    command_age_ms > self.cpv_velocity_timeout_s * 1_000.0
                )
                out_of_order = (
                    self._last_cpv_velocity_command_monotonic_ns is not None
                    and command_publish_ns
                    < self._last_cpv_velocity_command_monotonic_ns
                )
            else:
                stale = (
                    message_age_ms is not None
                    and message_age_ms > self.cpv_velocity_timeout_s * 1_000.0
                )
                out_of_order = (
                    stamp_ns is not None
                    and self._last_cpv_velocity_stamp_ns is not None
                    and stamp_ns < self._last_cpv_velocity_stamp_ns
                )
            if not command_is_zero and (stale or out_of_order):
                self._cpv_velocity_stale_dropped_count += 1
                self._cpv_velocity_stats_window_stale_dropped += 1
                self._maybe_log_cpv_velocity_stream_stats(received_at)
                self._trip_motion_fault_locked(
                    "stale or out-of-order controller CPV command"
                )
                return
            if self._cpv_stream_kind != "velocity":
                self.agx_arm.set_speed_percent(self.cpv_speed_percent)
                self.get_logger().info(
                    "Switching to latest-only CPV velocity streaming at "
                    f"{self.cpv_speed_percent}% speed; firmware move_j parking "
                    f"remains {self.speed_percent}%"
                )
            self._move_j_mode_active = False
            self._last_cpv_position_key = None
            self._cpv_stream_kind = "velocity"
            # A seven-frame write can fail part-way through. Treat it as moving
            # until a complete write proves otherwise, so the cleanup path sends
            # a full zero vector instead of leaving mixed old/new references.
            self._cpv_velocity_zeroed = False
            try:
                send_ms = self._send_cpv_velocities_locked(targets)
            except Exception as exc:
                self.get_logger().error(
                    f"Failed to send complete CPV velocity command: {exc}"
                )
                self._stop_cpv_velocity_locked("partial command send failure")
                self._last_cpv_velocity_received_at = None
                return
            driver_send_complete_ns = time.monotonic_ns()
            self._last_cpv_velocity_received_at = received_at
            if stamp_ns is not None:
                self._last_cpv_velocity_stamp_ns = stamp_ns
            if command_publish_ns is not None:
                self._last_cpv_velocity_command_monotonic_ns = command_publish_ns
            if input_sequence is not None:
                self._last_accepted_cpv_input_sequence = input_sequence
            self._cpv_velocity_zeroed = command_is_zero
            self._last_forwarded_cpv_trace_label = (
                ""
                if command_is_zero
                else _trace_with_times(
                    msg.header.frame_id,
                    drx=driver_receive_ns,
                    dsend=driver_send_complete_ns,
                )
            )
            self.is_mit_mode = False

        self._cpv_velocity_forwarded_count += 1
        self._cpv_velocity_stats_window_forwarded += 1
        self._cpv_velocity_stats_send_sum_ms += send_ms
        self._cpv_velocity_stats_send_max_ms = max(
            self._cpv_velocity_stats_send_max_ms,
            send_ms,
        )
        self._cpv_velocity_stats_send_samples += 1
        self._maybe_log_cpv_velocity_stream_stats(received_at)

    def _wait_for_move_j_mode(self) -> bool:
        """Wait for fresh firmware status to acknowledge the J-mode handover."""

        deadline = time.monotonic() + self.move_j_mode_handover_timeout_s
        expected = self.agx_arm.ARM_STATUS.ModeFeedback.MOVE_J
        last_mode = None
        while time.monotonic() < deadline:
            status = self.agx_arm.get_arm_status()
            if status is not None:
                last_mode = status.msg.mode_feedback
                if last_mode == expected:
                    return True
            time.sleep(0.005)
        self.get_logger().error(
            "Timed out waiting for firmware MOVE_J mode feedback; "
            f"last_mode_feedback={last_mode!s}"
        )
        return False

    def _leave_cpv_stream_locked(self, reason: str) -> None:
        self._stop_cpv_velocity_locked(reason)
        self._cpv_mode_active = False
        self._cpv_stream_kind = None
        self._last_cpv_position_key = None
        self._last_cpv_velocity_received_at = None
        self._last_cpv_velocity_stamp_ns = None
        self._cpv_velocity_zeroed = True
        self._last_forwarded_cpv_trace_label = ""
        self._move_j_mode_active = False

    def _joint_states_callback(self, msg: JointState) -> None:
        with self._motion_command_lock:
            self._leave_cpv_stream_locked("joint_states handover")
            super()._joint_states_callback(msg)

    def _move_p_callback(self, msg) -> None:
        with self._motion_command_lock:
            self._leave_cpv_stream_locked("move_p handover")
            super()._move_p_callback(msg)

    def _move_l_callback(self, msg) -> None:
        with self._motion_command_lock:
            self._leave_cpv_stream_locked("move_l handover")
            super()._move_l_callback(msg)

    def _move_c_callback(self, msg) -> None:
        with self._motion_command_lock:
            self._leave_cpv_stream_locked("move_c handover")
            super()._move_c_callback(msg)

    def _move_home_callback(self, request, response):
        with self._motion_command_lock:
            self._leave_cpv_stream_locked("move_home handover")
            return super()._move_home_callback(request, response)

    def _emergency_stop_callback(self, request, response):
        with self._motion_command_lock:
            self._leave_cpv_stream_locked("emergency stop")
            return super()._emergency_stop_callback(request, response)

    def _move_j_callback(self, msg: JointState) -> None:
        with self._motion_command_lock:
            self._stop_cpv_velocity_locked("move_j handover")
            self._move_j_callback_locked(msg)

    def _move_j_callback_locked(self, msg: JointState) -> None:
        """Forward a complete firmware trajectory target and log CPV handover."""

        if not self._check_can_control():
            return
        try:
            targets = complete_joint_positions(
                msg.name,
                msg.position,
                self.arm_joint_names,
            )
        except ValueError as exc:
            self.get_logger().error(f"Ignoring unsafe move_j command: {exc}")
            return

        leaving_cpv = self._cpv_mode_active
        needs_handover = not self._move_j_mode_active
        self._cpv_mode_active = False
        self._cpv_stream_kind = None
        self._last_cpv_position_key = None
        self._last_cpv_velocity_received_at = None
        self._last_cpv_velocity_stamp_ns = None
        self._cpv_velocity_zeroed = True
        self._last_forwarded_cpv_trace_label = ""
        if needs_handover:
            self.agx_arm.set_speed_percent(self.speed_percent)
        try:
            self._move_j_mode_active = send_complete_move_j(
                self.agx_arm,
                targets,
                mode_active=self._move_j_mode_active,
                confirm_mode=self._wait_for_move_j_mode,
            )
        except (RuntimeError, TimeoutError, ValueError) as exc:
            self._move_j_mode_active = False
            self.get_logger().error(
                f"Ignoring move_j command because firmware handover failed: {exc}"
            )
            return
        self.is_mit_mode = False
        self._move_j_command_count += 1
        target_deg = [round(math.degrees(value), 2) for value in targets]
        handover = (
            f"CPV-to-move_j handover at {self.speed_percent}% park speed"
            if leaving_cpv
            else "move_j"
        )
        self.get_logger().info(
            f"Forwarded {handover} command #{self._move_j_command_count}; "
            f"target_deg={target_deg}"
        )

    def _move_js_callback(self, msg: JointState) -> None:
        with self._motion_command_lock:
            self._stop_cpv_velocity_locked("move_js handover")
            self._cpv_mode_active = False
            self._cpv_stream_kind = None
            self._last_cpv_position_key = None
            self._last_cpv_velocity_received_at = None
            self._last_cpv_velocity_stamp_ns = None
            self._cpv_velocity_zeroed = True
            self._last_forwarded_cpv_trace_label = ""
            self._move_j_mode_active = False
            super()._move_js_callback(msg)

    def _move_cpv_pos_callback(self, msg: JointState) -> None:
        with self._motion_command_lock:
            self._stop_cpv_velocity_locked("CPV position handover")
            self._move_cpv_pos_callback_locked(msg)

    def _move_cpv_pos_callback_locked(self, msg: JointState) -> None:
        """Send one complete seven-joint CPV position update.

        NERO firmware 1.12+ exposes a real cyclic position loop.  Unlike the
        vendor ROS ``move_js`` callback, this path rejects partial JointState
        messages instead of silently replacing missing joints with zero.
        """

        if not self._check_can_control():
            return
        if not self.is_nero or not hasattr(self.agx_arm, "move_cpv_pos"):
            self.get_logger().error(
                "CPV position commands require NERO firmware 1.12 or newer"
            )
            return
        try:
            targets = complete_joint_positions(
                msg.name,
                msg.position,
                self.arm_joint_names,
            )
        except ValueError as exc:
            self.get_logger().error(f"Ignoring unsafe CPV position command: {exc}")
            return

        received_at = time.monotonic()
        position_key = cpv_position_command_key(targets)
        self._cpv_received_count += 1
        self._cpv_stats_window_received += 1
        self._record_cpv_message_age(msg)

        # The controller retains CPV position targets.  Re-sending the same
        # encoded target at the ROS control rate can build a seconds-long
        # firmware trajectory queue.  Forward the first target after every mode
        # handover, then only targets whose actual CAN payload has changed.
        if (
            self._cpv_mode_active
            and position_key == self._last_cpv_position_key
        ):
            self._cpv_suppressed_count += 1
            self._cpv_stats_window_suppressed += 1
            self._maybe_log_cpv_stream_stats(received_at)
            return

        # A full ROS update contains all seven joints. Suppress the SDK's
        # per-joint mode handover frames so feedback is not starved.
        if not self._cpv_mode_active:
            self.agx_arm.set_speed_percent(self.cpv_speed_percent)
            self.get_logger().info(
                f"Switching to CPV streaming at {self.cpv_speed_percent}% speed; "
                f"firmware move_j parking remains {self.speed_percent}%"
            )
        self._move_j_mode_active = False
        send_started = time.monotonic()
        self._cpv_mode_active = send_complete_cpv_positions(
            self.agx_arm,
            targets,
            mode_active=self._cpv_mode_active,
        )
        send_ms = (time.monotonic() - send_started) * 1_000.0
        self._last_cpv_position_key = position_key
        self._cpv_stream_kind = "position"
        self._last_cpv_velocity_received_at = None
        self._last_cpv_velocity_stamp_ns = None
        self._cpv_velocity_zeroed = True
        self._last_forwarded_cpv_trace_label = ""
        self._cpv_forwarded_count += 1
        self._cpv_stats_window_forwarded += 1
        self._cpv_stats_send_sum_ms += send_ms
        self._cpv_stats_send_max_ms = max(
            self._cpv_stats_send_max_ms,
            send_ms,
        )
        self._cpv_stats_send_samples += 1
        self._maybe_log_cpv_stream_stats(received_at)
        self.is_mit_mode = False

    def _publish_thread(self) -> None:
        joint_period = 1.0 / float(self.joint_pub_rate)
        telemetry_period = 1.0 / float(self.pub_rate)
        next_joint = time.monotonic()
        next_telemetry = next_joint
        self.publisher_thread_alive = True
        try:
            while not self._publisher_stop.is_set() and rclpy.ok():
                try:
                    now = time.monotonic()
                    self._enforce_cpv_velocity_watchdog(now)
                    if self._publisher_stop.is_set() or not rclpy.ok():
                        break
                    if self.agx_arm.is_ok():
                        if not self.control_ready and self._check_arm_ready():
                            self.control_ready = True
                            if not self._control_ready_logged:
                                gate_state = "open" if self.control_enabled else "closed"
                                motor_state = "enabled" if self.enable_flag else "disabled"
                                self.get_logger().info(
                                    "Agx_arm feedback publishing is ready; external "
                                    f"control gate is {gate_state}; motors were detected "
                                    f"as {motor_state}"
                                )
                                self._control_ready_logged = True
                        if now >= next_joint:
                            self._publish_joint_states()
                            next_joint += joint_period
                            if next_joint <= now:
                                next_joint = now + joint_period
                        if now >= next_telemetry:
                            self._publish_pose()
                            self._publish_arm_status()
                            self._publish_effector_status()
                            self._publish_leader_joint_states()
                            next_telemetry += telemetry_period
                            if next_telemetry <= now:
                                next_telemetry = now + telemetry_period
                    elif self.control_ready or self.enable_flag:
                        with self._motion_command_lock:
                            self._trip_motion_fault_locked(
                                "SDK reported the CAN arm disconnected"
                            )
                        break
                except Exception as exc:
                    # A dead publisher also removes the velocity watchdog. Zero
                    # the persistent reference and terminate the driver process
                    # so the supervisor cannot mistake it for a healthy node.
                    if self._publisher_stop.is_set() or not rclpy.ok():
                        break
                    self.publisher_thread_fault_reason = str(exc)
                    self.get_logger().error(
                        f"Feedback/watchdog publisher thread failed: {exc}"
                    )
                    with self._motion_command_lock:
                        self._stop_cpv_velocity_locked("publisher thread failure")
                    self._publisher_stop.set()
                    rclpy.shutdown()
                    break
                if next_joint <= now:
                    next_joint = now + joint_period
                if next_telemetry <= now:
                    next_telemetry = now + telemetry_period
                delay = max(
                    0.0,
                    min(next_joint, next_telemetry) - time.monotonic(),
                )
                if self._publisher_stop.wait(delay):
                    break
        finally:
            self.publisher_thread_alive = False

    def _move_mit_callback(self, msg: MoveMITMsg) -> None:
        with self._motion_command_lock:
            self._stop_cpv_velocity_locked("MIT handover")
            self._move_mit_callback_locked(msg)

    def _move_mit_callback_locked(self, msg: MoveMITMsg) -> None:
        """Send one MIT mode frame per handover, then one frame per joint.

        The vendor callback calls ``move_mit`` seven times while automatic mode
        selection remains enabled.  NERO V112 therefore emits seven redundant
        mode frames for every ROS command, which can starve the CAN feedback
        stream.  Keep automatic mode selection for all other vendor callbacks,
        but suppress it inside this already-batched MIT update.
        """
        if not self._check_can_control():
            return
        self._cpv_mode_active = False
        self._cpv_stream_kind = None
        self._last_cpv_position_key = None
        self._last_cpv_velocity_received_at = None
        self._last_cpv_velocity_stamp_ns = None
        self._cpv_velocity_zeroed = True
        self._last_forwarded_cpv_trace_label = ""
        self._move_j_mode_active = False
        arrays = [msg.joint_index, msg.p_des, msg.v_des, msg.kp, msg.kd, msg.torque]
        if len(set(len(values) for values in arrays)) > 1:
            self.get_logger().error("MoveMITMsg arrays have inconsistent lengths")
            return
        if not msg.joint_index:
            self.get_logger().warn("Received empty MoveMITMsg")
            return

        automatic_mode = self.agx_arm.get_auto_set_motion_mode_enabled()
        try:
            if not self.is_mit_mode:
                self.agx_arm.set_motion_mode("mit")
            self.agx_arm.set_auto_set_motion_mode_enabled(False)
            for index, joint_index in enumerate(msg.joint_index):
                self.agx_arm.move_mit(
                    joint_index=joint_index,
                    p_des=msg.p_des[index],
                    v_des=msg.v_des[index],
                    kp=msg.kp[index],
                    kd=msg.kd[index],
                    t_ff=msg.torque[index],
                )
        finally:
            self.agx_arm.set_auto_set_motion_mode_enabled(automatic_mode)
        self.is_mit_mode = True

    def stop_publisher(self, timeout_s: float = 2.0) -> None:
        self._publisher_stop.set()
        thread = getattr(self, "publisher_thread", None)
        if thread is None or thread is threading.current_thread():
            return
        thread.join(timeout=timeout_s)
        if thread.is_alive():
            self.get_logger().warn(
                "Feedback publisher did not stop within 2 seconds"
            )

    def disable_for_shutdown(self, timeout_s: float = 8.0) -> None:
        """Fail-safe: disable an arm enabled through this process before exit."""

        if not self._enabled_by_this_process:
            return
        try:
            with self._motion_command_lock:
                self._stop_cpv_velocity_locked("driver shutdown")
            if self._enable_arm(False, timeout_s):
                self._enabled_by_this_process = False
                self.get_logger().info("Arm disabled during driver shutdown")
            else:
                self.get_logger().error(
                    "Arm was enabled by this process but shutdown disable failed; "
                    "use the physical emergency stop"
                )
        except Exception as exc:
            self.get_logger().error(
                f"Exception while disabling arm during shutdown: {exc}; "
                "use the physical emergency stop"
            )


def main(args: list[str] | None = None) -> None:
    # Retain rclpy's SIGINT handler so a blocking executor wakes immediately.
    # Unlike the vendor entry point, the guarded publisher exits if that handler
    # invalidates the context and shutdown is never called a second time.
    rclpy.init(args=args)
    node: SafeAgxArmRosNode | None = None
    try:
        node = SafeAgxArmRosNode()
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        if node is not None:
            node.stop_publisher()
            node.disable_for_shutdown()
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
