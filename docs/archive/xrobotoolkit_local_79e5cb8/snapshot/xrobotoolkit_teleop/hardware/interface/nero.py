from __future__ import annotations

import math
import threading
import time
from dataclasses import dataclass
from typing import Any, Sequence

import numpy as np


NERO_JOINT_NAMES = tuple(f"joint{i}" for i in range(1, 8))
NERO_JOINT_LIMITS = np.array(
    [
        [-2.705261, 2.705261],
        [-1.745330, 1.745330],
        [-2.757621, 2.757621],
        [-1.012291, 2.146755],
        [-2.757621, 2.757621],
        [-0.733039, 0.959932],
        [-1.570797, 1.570797],
    ],
    dtype=np.float64,
)
NERO_FIRMWARE_SELECTORS = ("default", "v111", "v112", "v120")

# Mirrors of pyAgxArm's ARM_STATUS enums. Duplicated as plain ints so status can
# be decoded for diagnostics without importing the SDK (and so tests can feed in
# lightweight stubs).
NERO_ARM_STATUS_NAMES = {
    0x0: "NORMAL",
    0x1: "EMERGENCY_STOP",
    0x2: "NO_SOLUTION",
    0x3: "SINGULARITY_POINT",
    0x4: "TARGET_POS_EXCEEDS_LIMIT",
    0x5: "JOINT_COMMUNICATION_ERR",
    0x6: "JOINT_BRAKE_NOT_RELEASED",
    0x7: "COLLISION_OCCURRED",
    0x8: "OVERSPEED_DURING_TEACHING_DRAG",
    0x9: "JOINT_STATUS_ERR",
    0xA: "OTHER_ERR",
    0xB: "TEACHING_RECORD",
    0xC: "TEACHING_EXECUTION",
    0xD: "TEACHING_PAUSE",
    0xE: "MAIN_CONTROLLER_NTC_OVER_TEMPERATURE",
    0xF: "RELEASE_RESISTOR_NTC_OVER_TEMPERATURE",
    0xFF: "UNKNOWN",
}
NERO_CTRL_MODE_NAMES = {
    0x0: "STANDBY",
    0x1: "CAN_CTRL",
    0x2: "TEACHING_MODE",
    0x3: "ETHERNET_CONTROL_MODE",
    0x4: "WIFI_CONTROL_MODE",
    0x5: "REMOTE_CONTROL_MODE",
    0x6: "LINKAGE_TEACHING_INPUT_MODE",
    0x7: "OFFLINE_TRAJECTORY_MODE",
    0x8: "TCP_CTRL",
    0xFF: "UNKNOWN",
}
NERO_MOTION_STATUS_NAMES = {
    0x0: "REACH_TARGET_POS_SUCCESSFULLY",
    0x1: "REACH_TARGET_POS_FAILED",
    0xFF: "UNKNOWN",
}
NERO_CTRL_MODE_CAN = 0x1
NERO_ARM_STATUS_NORMAL = 0x0
NERO_ARM_STATUS_EMERGENCY_STOP = 0x1
NERO_ARM_STATUS_BRAKE_NOT_RELEASED = 0x6
# arm_status values from which a current-position hold may be initialized. These
# are the disabled/arming states: NORMAL is already live, EMERGENCY_STOP and
# JOINT_BRAKE_NOT_RELEASED are what a powered-but-disabled NERO reports at rest.
NERO_ENABLE_TRANSITION_ARM_STATUS = frozenset(
    {NERO_ARM_STATUS_NORMAL, NERO_ARM_STATUS_EMERGENCY_STOP, NERO_ARM_STATUS_BRAKE_NOT_RELEASED}
)


def _mode_name(table: dict[int, str], value: Any) -> str:
    numeric = _enum_value(value)
    if numeric is None:
        return f"{value!r}"
    return f"{numeric}/{table.get(numeric, 'UNDOCUMENTED')}"


def _ctrl_mode_help(value: Any) -> str:
    """Describe which channel currently owns the arm.

    The official V112 ``enable()`` claims CAN control on its own by re-sending
    the 0x151 mode frame, so these states are usually informational rather than
    something the operator must clear by hand. Teaching mode is the exception:
    it is driven from the pendant and should be left deliberately.
    """
    numeric = _enum_value(value)
    if numeric == 0x3:
        return "currently owned over Ethernet (web UI or ROS driver)"
    if numeric == 0x4:
        return "currently owned over WiFi"
    if numeric == 0x2:
        return "in teaching/drag mode -- leave teaching mode on the pendant first"
    if numeric == 0x0:
        return "in STANDBY, no control channel claimed yet"
    return "no CAN control channel is claimed"


class NeroSafetyError(RuntimeError):
    pass


@dataclass(frozen=True)
class NeroArmState:
    joints: np.ndarray
    feedback_timestamp: float
    feedback_hz: float
    status: Any


def validate_joint_target(
    current: Sequence[float],
    target: Sequence[float],
    *,
    joint_limit_margin_rad: float,
    max_joint_step_rad: float,
) -> np.ndarray:
    current_array = np.asarray(current, dtype=np.float64)
    target_array = np.asarray(target, dtype=np.float64)
    if current_array.shape != (7,) or target_array.shape != (7,):
        raise NeroSafetyError("NERO joint vectors must contain exactly seven values")
    if not np.all(np.isfinite(current_array)) or not np.all(np.isfinite(target_array)):
        raise NeroSafetyError("NERO joint vectors must contain only finite values")
    if joint_limit_margin_rad < 0.0:
        raise ValueError("joint_limit_margin_rad must be non-negative")
    if max_joint_step_rad <= 0.0:
        raise ValueError("max_joint_step_rad must be positive")

    lower = NERO_JOINT_LIMITS[:, 0] + joint_limit_margin_rad
    upper = NERO_JOINT_LIMITS[:, 1] - joint_limit_margin_rad
    outside = np.flatnonzero((target_array < lower) | (target_array > upper))
    if outside.size:
        joint_index = int(outside[0])
        raise NeroSafetyError(
            f"{NERO_JOINT_NAMES[joint_index]} target {target_array[joint_index]:.5f} rad "
            f"is outside the guarded interval [{lower[joint_index]:.5f}, {upper[joint_index]:.5f}]"
        )

    step = np.abs(target_array - current_array)
    if float(np.max(step)) > max_joint_step_rad:
        joint_index = int(np.argmax(step))
        raise NeroSafetyError(
            f"{NERO_JOINT_NAMES[joint_index]} step {step[joint_index]:.5f} rad exceeds "
            f"the per-command limit {max_joint_step_rad:.5f} rad"
        )
    return target_array


def _enum_value(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def resolve_nero_firmware_selector(software_version: str) -> str:
    """Map NERO's firmware string to the matching official SDK driver.

    NERO can report patch releases such as ``1.121`` for the 1.12 driver
    family. The first two digits after the decimal identify the SDK family;
    treating 1.121 as a conventional semantic version would incorrectly
    select the >=1.20 driver.
    """
    text = str(software_version).strip()
    try:
        major_text, release_text = text.split(".", 1)
        if not major_text.isdigit() or not release_text.isdigit():
            raise ValueError
        major = int(major_text)
        release = int(release_text[:2].ljust(2, "0"))
    except ValueError as exc:
        raise NeroSafetyError(f"Unsupported NERO firmware version string: {text!r}") from exc

    family = (major, release)
    if family >= (1, 20):
        return "v120"
    if family >= (1, 12):
        return "v112"
    if family >= (1, 11):
        return "v111"
    return "default"


def status_error_flags(status: Any) -> list[str]:
    if status is None or getattr(status, "msg", None) is None:
        return ["missing_status"]
    errors = getattr(status.msg, "err_status", None)
    if errors is None:
        return ["missing_error_status"]
    flags = []
    for name in dir(errors):
        if name.startswith("_"):
            continue
        try:
            value = getattr(errors, name)
        except Exception:
            continue
        if isinstance(value, (bool, np.bool_)) and bool(value):
            flags.append(name)
    return flags


class NeroArmInterface:
    """Guarded pyAgxArm interface. Connecting is read-only; arming is explicit."""

    def __init__(
        self,
        *,
        arm_name: str,
        channel: str,
        firmware: str = "v112",
        execute: bool = False,
        speed_percent: int = 5,
        feedback_timeout_s: float = 0.15,
        feedback_stale_grace_s: float = 0.5,
        joint_limit_margin_rad: float = math.radians(3.0),
        max_joint_step_rad: float = math.radians(0.75),
        robot: Any | None = None,
    ):
        if speed_percent < 1 or speed_percent > 5:
            raise ValueError("NERO live speed_percent must be in [1, 5]")
        if feedback_stale_grace_s < 0.0:
            raise ValueError("feedback_stale_grace_s must be non-negative")
        self.arm_name = arm_name
        self.channel = channel
        self.firmware = firmware
        self.resolved_firmware: str | None = None
        self.detected_firmware_version: str | None = None
        self.execute = execute
        self.speed_percent = speed_percent
        self.feedback_timeout_s = feedback_timeout_s
        self.feedback_stale_grace_s = feedback_stale_grace_s
        # label -> monotonic time the message first went over feedback_timeout_s.
        self._stale_since: dict[str, float] = {}
        self.joint_limit_margin_rad = joint_limit_margin_rad
        self.max_joint_step_rad = max_joint_step_rad
        self._robot = robot
        self._connected = False
        self._armed = False
        self._enable_requested = False
        self._lock = threading.RLock()
        self.last_command: np.ndarray | None = None

    def _require_fresh_message(self, feedback: Any, label: str) -> None:
        """Fault only when feedback has been stale *continuously*.

        A single late frame is not a comms failure. The CAN feedback arrives at
        100-150 Hz, but bus arbitration and SDK receive-thread scheduling can
        leave an occasional gap of a few hundred ms, and faulting on one sample
        latches HOLD for the rest of the run on healthy hardware.

        So an over-age sample starts a timer instead of raising, and the fault
        only fires if nothing fresh arrives within ``feedback_stale_grace_s``.
        A genuinely dead bus never recovers, so it still faults -- just after the
        grace window rather than on the first gap. A missing or never-received
        message still raises immediately: that is absence, not lateness.
        """
        if feedback is None:
            raise NeroSafetyError(f"{self.arm_name} has no {label} feedback")
        timestamp = float(getattr(feedback, "timestamp", 0.0))
        age = time.time() - timestamp
        if timestamp <= 0.0:
            raise NeroSafetyError(f"{self.arm_name} has never received {label} feedback")
        if age < -1.0:
            raise NeroSafetyError(
                f"{self.arm_name} {label} feedback timestamp is in the future "
                f"(timestamp={timestamp:.6f}, age={age:.3f}s); check the system clock"
            )
        if age <= self.feedback_timeout_s:
            self._stale_since.pop(label, None)
            return
        now = time.monotonic()
        first_stale = self._stale_since.setdefault(label, now)
        stale_for = now - first_stale
        if stale_for > self.feedback_stale_grace_s:
            raise NeroSafetyError(
                f"{self.arm_name} {label} feedback has been stale for {stale_for:.3f}s "
                f"(timestamp={timestamp:.6f}, age={age:.3f}s, "
                f"limit={self.feedback_timeout_s:.3f}s)"
            )

    def _require_no_comm_error(self) -> None:
        if self._robot is None or not hasattr(self._robot, "has_comm_error"):
            return
        if self._robot.has_comm_error():
            detail = self._robot.get_comm_error() if hasattr(self._robot, "get_comm_error") else "unknown"
            raise NeroSafetyError(f"{self.arm_name} SDK communication error: {detail}")

    def _sdk_symbols(self):
        try:
            from pyAgxArm import AgxArmFactory, ArmModel, NeroFW, create_agx_arm_config
        except ImportError as exc:
            raise RuntimeError(
                "pyAgxArm is not installed. Run setup_conda.sh --install in the nero environment."
            ) from exc
        return AgxArmFactory, ArmModel, NeroFW, create_agx_arm_config

    def _create_robot(self, firmware: str):
        AgxArmFactory, ArmModel, NeroFW, create_agx_arm_config = self._sdk_symbols()

        firmware_values = {
            "default": NeroFW.DEFAULT,
            "v111": NeroFW.V111,
            "v112": NeroFW.V112,
            "v120": NeroFW.V120,
        }
        if firmware not in firmware_values:
            raise ValueError(f"Unsupported NERO firmware selector: {firmware}")
        config = create_agx_arm_config(
            robot=ArmModel.NERO,
            firmeware_version=firmware_values[firmware],
            interface="socketcan",
            channel=self.channel,
        )
        robot = AgxArmFactory.create_arm(config)
        if hasattr(robot, "set_joint_limits_enabled"):
            robot.set_joint_limits_enabled(True)
        return robot

    @staticmethod
    def _firmware_version_from_info(info: Any) -> str | None:
        if not isinstance(info, dict):
            return None
        version = info.get("software_version")
        return None if version is None else str(version)

    def _detect_and_create_robot(self, timeout_s: float):
        """Follow the official detector's reconnect flow without enabling."""
        probe = self._create_robot("default")
        probe_connected = False
        try:
            probe.connect()
            probe_connected = True
            deadline = time.monotonic() + timeout_s
            info = None
            while time.monotonic() < deadline and info is None:
                remaining = max(0.0, deadline - time.monotonic())
                try:
                    info = probe.get_firmware(timeout=min(0.5, remaining), min_interval=0.0)
                except TypeError:
                    info = probe.get_firmware()
                if info is None:
                    time.sleep(0.02)
            version = self._firmware_version_from_info(info)
            if version is None:
                raise TimeoutError(
                    f"{self.arm_name} could not read NERO firmware on {self.channel}. "
                    "Automatic detection never enables the arm; for legacy firmware <=1.11, "
                    "pass --firmware default or --firmware v111 explicitly."
                )
            selector = resolve_nero_firmware_selector(version)
            self.detected_firmware_version = version
            self.resolved_firmware = selector
        finally:
            if probe_connected:
                probe.disconnect()
        return self._create_robot(selector)

    def _record_and_validate_firmware(self, timeout_s: float) -> None:
        if self._robot is None or not hasattr(self._robot, "get_firmware"):
            return
        try:
            info = self._robot.get_firmware(timeout=max(0.0, timeout_s), min_interval=0.0)
        except TypeError:
            info = self._robot.get_firmware()
        version = self._firmware_version_from_info(info)
        if version is None:
            return
        detected_selector = resolve_nero_firmware_selector(version)
        self.detected_firmware_version = version
        if self.resolved_firmware is None:
            self.resolved_firmware = detected_selector
        if detected_selector != self.resolved_firmware:
            raise NeroSafetyError(
                f"{self.arm_name} firmware {version} requires {detected_selector}, "
                f"but {self.resolved_firmware} was selected"
            )

    @property
    def armed(self) -> bool:
        return self._armed

    def connect(self, timeout_s: float = 3.0) -> NeroArmState:
        try:
            with self._lock:
                if self._connected:
                    return self.read_state()
                if self._robot is None:
                    if self.firmware == "auto":
                        self._robot = self._detect_and_create_robot(timeout_s)
                    else:
                        if self.firmware not in NERO_FIRMWARE_SELECTORS:
                            raise ValueError(f"Unsupported NERO firmware selector: {self.firmware}")
                        self.resolved_firmware = self.firmware
                        self._robot = self._create_robot(self.resolved_firmware)
                self._robot.connect()
                self._connected = True
            state = self.wait_for_feedback(timeout_s)
            self._record_and_validate_firmware(min(1.0, timeout_s))
            return state
        except Exception:
            self.close(hold_if_armed=False, disable_if_armed=False)
            raise

    def wait_for_feedback(self, timeout_s: float) -> NeroArmState:
        deadline = time.monotonic() + timeout_s
        last_error: Exception | None = None
        while time.monotonic() < deadline:
            try:
                state = self.read_state()
                # NERO joint and flange poses are assembled from several CAN
                # frames. Requiring every motor state and the full flange pose
                # prevents accepting the SDK's initially zero-filled aggregate.
                self.get_flange_pose()
                return state
            except (NeroSafetyError, AttributeError, TypeError) as exc:
                last_error = exc
            time.sleep(0.01)
        detail = f": {last_error}" if last_error else ""
        raise TimeoutError(f"{self.arm_name} received no complete fresh feedback on {self.channel}{detail}")

    def read_state(self, *, require_fresh: bool = True) -> NeroArmState:
        if not self._connected or self._robot is None:
            raise NeroSafetyError(f"{self.arm_name} is not connected")
        with self._lock:
            self._require_no_comm_error()
            feedback = self._robot.get_joint_angles()
            status = self._robot.get_arm_status()
            motor_states = [self._robot.get_motor_states(index) for index in range(1, 8)]
        if require_fresh:
            self._require_fresh_message(feedback, "joint-angle")
            self._require_fresh_message(status, "arm-status")
            for index, motor_state in enumerate(motor_states, 1):
                self._require_fresh_message(motor_state, f"joint{index} motor-state")
        elif feedback is None:
            raise NeroSafetyError(f"{self.arm_name} has no joint-angle feedback")
        joints = np.asarray(feedback.msg, dtype=np.float64)
        if joints.shape != (7,) or not np.all(np.isfinite(joints)):
            raise NeroSafetyError(f"{self.arm_name} returned invalid joint feedback")
        timestamp = float(getattr(feedback, "timestamp", 0.0))
        return NeroArmState(joints.copy(), timestamp, float(getattr(feedback, "hz", 0.0)), status)

    def get_flange_pose(self) -> np.ndarray:
        if not self._connected or self._robot is None:
            raise NeroSafetyError(f"{self.arm_name} is not connected")
        with self._lock:
            self._require_no_comm_error()
            feedback = self._robot.get_flange_pose()
        self._require_fresh_message(feedback, "flange-pose")
        pose = np.asarray(feedback.msg, dtype=np.float64)
        if pose.shape != (6,) or not np.all(np.isfinite(pose)):
            raise NeroSafetyError(f"{self.arm_name} returned invalid flange-pose feedback")
        return pose

    def _require_motion_safe_status(self, status: Any) -> None:
        flags = status_error_flags(status)
        if flags:
            raise NeroSafetyError(f"{self.arm_name} status error flags: {', '.join(flags)}")
        message = getattr(status, "msg", None)
        arm_status = _enum_value(getattr(message, "arm_status", None))
        ctrl_mode = _enum_value(getattr(message, "ctrl_mode", None))
        # ctrl_mode is checked first: when another client owns the arm over
        # Ethernet the controller silently drops every CAN move_j, so reporting
        # a downstream arm_status here would point at the wrong cause.
        if ctrl_mode != NERO_CTRL_MODE_CAN:
            raise NeroSafetyError(
                f"{self.arm_name} ctrl_mode is "
                f"{_mode_name(NERO_CTRL_MODE_NAMES, getattr(message, 'ctrl_mode', None))}, "
                f"expected 1/CAN_CTRL -- {_ctrl_mode_help(getattr(message, 'ctrl_mode', None))}"
            )
        if arm_status != NERO_ARM_STATUS_NORMAL:
            if arm_status == NERO_ARM_STATUS_EMERGENCY_STOP:
                raise NeroSafetyError(
                    f"{self.arm_name} arm_status is "
                    f"{_mode_name(NERO_ARM_STATUS_NAMES, getattr(message, 'arm_status', None))}. "
                    "Release the physical emergency stop/safety chain and power-cycle "
                    "the controller with the arm supported. The official reset command "
                    "is intentionally not sent because it can make a raised arm drop immediately"
                )
            raise NeroSafetyError(
                f"{self.arm_name} arm_status is "
                f"{_mode_name(NERO_ARM_STATUS_NAMES, getattr(message, 'arm_status', None))}, "
                "expected 0/NORMAL"
            )

    def _require_enable_transition_status(self, status: Any) -> None:
        """Allow only the documented disabled/arming states before first hold."""
        flags = status_error_flags(status)
        if flags:
            raise NeroSafetyError(f"{self.arm_name} status error flags: {', '.join(flags)}")
        message = getattr(status, "msg", None)
        arm_status = _enum_value(getattr(message, "arm_status", None))
        ctrl_mode = _enum_value(getattr(message, "ctrl_mode", None))
        if ctrl_mode != NERO_CTRL_MODE_CAN:
            raise NeroSafetyError(
                f"{self.arm_name} ctrl_mode is "
                f"{_mode_name(NERO_CTRL_MODE_NAMES, getattr(message, 'ctrl_mode', None))}, "
                f"expected 1/CAN_CTRL -- {_ctrl_mode_help(getattr(message, 'ctrl_mode', None))}"
            )
        if arm_status not in NERO_ENABLE_TRANSITION_ARM_STATUS:
            raise NeroSafetyError(
                f"{self.arm_name} cannot initialize a current-position hold from arm_status "
                f"{_mode_name(NERO_ARM_STATUS_NAMES, getattr(message, 'arm_status', None))}"
            )

    def describe_status(self) -> str:
        """One-line human-readable controller state, for preflight diagnostics."""
        state = self.read_state()
        message = getattr(state.status, "msg", None)
        enabled = self.joint_enable_bits()
        flags = status_error_flags(state.status)
        return (
            f"{self.arm_name} [{self.channel}] "
            f"arm_status={_mode_name(NERO_ARM_STATUS_NAMES, getattr(message, 'arm_status', None))} "
            f"ctrl_mode={_mode_name(NERO_CTRL_MODE_NAMES, getattr(message, 'ctrl_mode', None))} "
            f"motion={_mode_name(NERO_MOTION_STATUS_NAMES, getattr(message, 'motion_status', None))} "
            f"enabled={sum(1 for bit in enabled if bit)}/7 "
            f"feedback={state.feedback_hz:.0f}Hz "
            f"errors={','.join(flags) if flags else 'none'}"
        )

    def joint_enable_bits(self) -> list[bool]:
        """Per-joint enable bits, so a partial enable names the stuck joints."""
        if not self._connected or self._robot is None:
            raise NeroSafetyError(f"{self.arm_name} is not connected")
        with self._lock:
            if hasattr(self._robot, "get_joints_enable_status_list"):
                bits = self._robot.get_joints_enable_status_list()
                if bits is not None:
                    return [bool(bit) for bit in bits]
            if hasattr(self._robot, "get_joint_enable_status"):
                return [bool(self._robot.get_joint_enable_status(index)) for index in range(1, 8)]
        return [False] * 7

    def arm(self, timeout_s: float = 5.0) -> None:
        if not self.execute:
            raise NeroSafetyError(f"{self.arm_name} is a read-only/shadow interface")
        state = self.read_state()
        # Deliberately NOT gating on ctrl_mode here. The official V112 driver's
        # enable() claims CAN control itself: when ctrl_mode != CAN_CTRL it
        # re-sends the 0x151 mode frame (Byte0=0x01) until the controller hands
        # over, which is the only supported way out of ETHERNET_CONTROL_MODE.
        # Checking ctrl_mode before enable() would block the very call that
        # fixes it. Error flags are still worth failing on early.
        error_flags = status_error_flags(state.status)
        if error_flags:
            raise NeroSafetyError(
                f"{self.arm_name} status error flags before enable: {', '.join(error_flags)}"
            )
        with self._lock:
            self._robot.set_speed_percent(self.speed_percent)
        deadline = time.monotonic() + timeout_s
        enabled = False
        self._enable_requested = True
        try:
            while time.monotonic() < deadline:
                with self._lock:
                    try:
                        enabled = bool(
                            self._robot.enable(
                                timeout=min(1.0, max(0.1, deadline - time.monotonic()))
                            )
                        )
                    except TypeError:
                        enabled = bool(self._robot.enable())
                if enabled:
                    break
                time.sleep(0.05)
            if not enabled:
                raise NeroSafetyError(
                    f"{self.arm_name} failed to enable within {timeout_s:.1f}s. "
                    f"Last state: {self.describe_status()}"
                )

            # Match the official agx_arm_ros control gate: require all joint
            # enable bits and a live joint stream. Once those are valid, send
            # one move_j at the measured position. This engages position hold
            # without requesting displacement and lets the controller leave
            # its disabled EMERGENCY_STOP/JOINT_BRAKE_NOT_RELEASED state.
            last_status_error = "no post-enable feedback"
            initial_hold_sent = False
            while time.monotonic() < deadline:
                state = self.read_state()
                enable_bits = self.joint_enable_bits()
                if not all(enable_bits):
                    stuck = [f"joint{i}" for i, bit in enumerate(enable_bits, 1) if not bit]
                    last_status_error = (
                        f"{len(stuck)} joint enable bit(s) still clear: {', '.join(stuck)}"
                    )
                    time.sleep(0.05)
                    continue
                if state.feedback_hz <= 0.0:
                    last_status_error = "joint feedback stream is not ready (0 Hz)"
                    time.sleep(0.05)
                    continue
                if not initial_hold_sent:
                    self._require_enable_transition_status(state.status)
                    with self._lock:
                        self._robot.move_j(state.joints.tolist())
                    self.last_command = state.joints.copy()
                    initial_hold_sent = True
                    time.sleep(0.05)
                    continue
                try:
                    self._require_motion_safe_status(state.status)
                    self._armed = True
                    return
                except NeroSafetyError as exc:
                    last_status_error = str(exc)
                time.sleep(0.05)
            raise NeroSafetyError(
                f"{self.arm_name} did not reach a motion-safe state within "
                f"{timeout_s:.1f}s: {last_status_error}"
            )
        except Exception as exc:
            cleanup_error = None
            try:
                with self._lock:
                    try:
                        disabled = bool(self._robot.disable(timeout=1.5))
                    except TypeError:
                        disabled = bool(self._robot.disable())
                if not disabled:
                    cleanup_error = "disable returned false"
                else:
                    self._enable_requested = False
            except Exception as disable_exc:
                cleanup_error = str(disable_exc)
            self._armed = False
            if cleanup_error is not None:
                raise NeroSafetyError(
                    f"{exc}; post-enable cleanup failed: {cleanup_error}"
                ) from exc
            raise

    def command(self, target: Sequence[float]) -> np.ndarray:
        if not self.execute or not self._armed:
            raise NeroSafetyError(f"{self.arm_name} live output is not armed")
        state = self.read_state()
        self._require_motion_safe_status(state.status)
        safe_target = validate_joint_target(
            state.joints,
            target,
            joint_limit_margin_rad=self.joint_limit_margin_rad,
            max_joint_step_rad=self.max_joint_step_rad,
        )
        with self._lock:
            self._robot.move_j(safe_target.tolist())
        self.last_command = safe_target.copy()
        return safe_target

    def move_to_pose(
        self,
        target: Sequence[float],
        *,
        timeout_s: float = 60.0,
        tolerance_rad: float = math.radians(0.5),
    ) -> np.ndarray:
        """Ramp to ``target`` in bounded steps, then confirm arrival.

        Each step goes through :meth:`command`, so the per-command step bound,
        the guarded joint limits and the ctrl_mode/arm_status checks all apply
        exactly as they do during teleoperation -- this is not a privileged
        path that can move faster or further than the operator can.

        Used to leave the straight-elbow singularity before IK starts. It only
        runs on an already-armed arm and returns the measured position.
        """
        if not self.execute or not self._armed:
            raise NeroSafetyError(f"{self.arm_name} live output is not armed")
        goal = np.asarray(target, dtype=np.float64)
        if goal.shape != (7,) or not np.all(np.isfinite(goal)):
            raise ValueError(f"{self.arm_name} pose target must contain seven finite values")
        # Reject an unreachable goal up front rather than after ramping toward
        # it for timeout_s and stalling against the guard band.
        lower = NERO_JOINT_LIMITS[:, 0] + self.joint_limit_margin_rad
        upper = NERO_JOINT_LIMITS[:, 1] - self.joint_limit_margin_rad
        outside = np.where((goal < lower) | (goal > upper))[0]
        if outside.size:
            raise NeroSafetyError(
                f"{self.arm_name} pose target is outside the guarded joint interval for "
                + ", ".join(f"joint{index + 1}" for index in outside)
            )

        deadline = time.monotonic() + timeout_s
        measured = self.read_state().joints
        while time.monotonic() < deadline:
            error = goal - measured
            if float(np.max(np.abs(error))) <= tolerance_rad:
                return measured
            # Step toward the goal without ever exceeding the per-command bound.
            # Stay strictly inside it: clipping to exactly max_joint_step_rad can
            # round to just above it and be rejected by validate_joint_target.
            bound = self.max_joint_step_rad * (1.0 - 1e-9)
            step = np.clip(error, -bound, bound)
            self.command(measured + step)
            time.sleep(0.05)
            measured = self.read_state().joints
        remaining = np.max(np.abs(goal - measured))
        raise NeroSafetyError(
            f"{self.arm_name} did not reach the startup pose within {timeout_s:.1f}s "
            f"(largest remaining joint error {math.degrees(float(remaining)):.2f} deg)"
        )

    def hold(self) -> None:
        if not self.execute or not self._armed:
            return
        try:
            current = self.read_state().joints
            with self._lock:
                self._robot.move_j(current.tolist())
            self.last_command = current.copy()
        except Exception as exc:
            raise NeroSafetyError(f"{self.arm_name} failed to issue a current-position hold: {exc}") from exc

    def emergency_stop(self) -> None:
        if self._connected and self._robot is not None:
            with self._lock:
                self._robot.electronic_emergency_stop()
            self._armed = False

    def clear_emergency_stop(self) -> None:
        """Send the 0x150 Byte0=2 damping-exit frame (SDK ``reset()``).

        DANGEROUS on a raised arm. Exiting damping drops the joints' holding
        torque and this arm has no mechanical brakes, so a lifted arm falls
        immediately. Nothing in the normal arm()/teleop path calls this; it
        exists only for an explicit operator-driven recovery from a latched
        EMERGENCY_STOP, and the caller is responsible for confirming the arm is
        already resting or supported.

        Per the protocol, 0x471 must re-enable the motors afterwards before any
        motion, which arm() does.
        """
        if not self._connected or self._robot is None:
            raise NeroSafetyError(f"{self.arm_name} is not connected")
        if not hasattr(self._robot, "reset"):
            raise NeroSafetyError(f"{self.arm_name} driver has no reset() command")
        with self._lock:
            self._robot.reset()
        self._armed = False

    def close(self, *, hold_if_armed: bool = True, disable_if_armed: bool = True) -> None:
        if not self._connected or self._robot is None:
            return
        failures = []
        try:
            if hold_if_armed and self._armed:
                try:
                    self.hold()
                except Exception as exc:
                    failures.append(f"hold: {exc}")
            if (
                disable_if_armed
                and (self._armed or self._enable_requested)
                and hasattr(self._robot, "disable")
            ):
                try:
                    with self._lock:
                        try:
                            disabled = bool(self._robot.disable(timeout=1.5))
                        except TypeError:
                            disabled = bool(self._robot.disable())
                    if not disabled:
                        failures.append("disable returned false")
                    else:
                        self._enable_requested = False
                except Exception as exc:
                    failures.append(f"disable: {exc}")
        finally:
            with self._lock:
                self._robot.disconnect()
            self._connected = False
            self._armed = False
            self._enable_requested = False
        if failures:
            raise NeroSafetyError(f"{self.arm_name} shutdown failures: {'; '.join(failures)}")
