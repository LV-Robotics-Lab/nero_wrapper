"""Read-only lifecycle wrapper for the optional ``pyAgxArm`` SDK.

Motion remains in the field-validated scripts under ``scripts/`` until the
package API has been revalidated on the physical NERO rig. This module never
enables an arm and never sends a target.
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from typing import Any

from .config import ArmEndpoint, NeroConfig


class NeroSdkUnavailable(ImportError):
    """The optional vendor SDK is not importable in the current environment."""


@dataclass(frozen=True, slots=True)
class ArmSnapshot:
    arm: str
    channel: str
    joint_angles_rad: tuple[float, ...]
    feedback_hz: float | None
    timestamp: float | int | None
    tcp_pose: object | None
    arm_status: object | None

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def _load_sdk() -> Any:
    try:
        import pyAgxArm
    except ImportError as exc:
        raise NeroSdkUnavailable(
            "pyAgxArm is required for live hardware access. Install the pinned vendor "
            "SDK in the NERO workstation venv; configuration and doctor commands do "
            "not require it."
        ) from exc
    return pyAgxArm


def _firmware_value(sdk: Any, name: str) -> Any:
    mapping = {
        "default": sdk.NeroFW.DEFAULT,
        "v111": sdk.NeroFW.V111,
        "v112": sdk.NeroFW.V112,
        "v120": sdk.NeroFW.V120,
    }
    return mapping[name]


def _message(value: object | None) -> object | None:
    return getattr(value, "msg", value)


def _serializable(value: object | None) -> object | None:
    value = _message(value)
    if value is None or isinstance(value, (bool, float, int, str)):
        return value
    if isinstance(value, (list, tuple)):
        return tuple(value)
    if hasattr(value, "__dict__"):
        return {
            key: item
            for key, item in vars(value).items()
            if not key.startswith("_") and isinstance(item, (bool, float, int, str, type(None)))
        }
    return repr(value)


class NeroArm:
    """A read-only, context-managed connection to one NERO arm."""

    def __init__(
        self,
        arm: str | ArmEndpoint = "arm_a",
        *,
        config: NeroConfig | None = None,
        sdk: Any | None = None,
    ) -> None:
        self.config = NeroConfig.from_env() if config is None else config
        self.endpoint = self.config.arm(arm) if isinstance(arm, str) else arm
        self._sdk = sdk
        self._robot: Any | None = None

    @property
    def is_connected(self) -> bool:
        return self._robot is not None

    @property
    def raw(self) -> Any:
        if self._robot is None:
            raise RuntimeError("NERO arm is not connected")
        return self._robot

    def connect(self) -> NeroArm:
        if self._robot is not None:
            return self
        sdk = _load_sdk() if self._sdk is None else self._sdk
        sdk_config = sdk.create_agx_arm_config(
            robot=sdk.ArmModel.NERO,
            firmeware_version=_firmware_value(sdk, self.config.firmware),
            interface=self.config.can_interface,
            channel=self.endpoint.channel,
        )
        robot = sdk.AgxArmFactory.create_arm(sdk_config)
        try:
            robot.connect()
        except Exception:
            if hasattr(robot, "disconnect"):
                robot.disconnect()
            raise
        self._robot = robot
        return self

    def close(self) -> None:
        robot, self._robot = self._robot, None
        if robot is not None and hasattr(robot, "disconnect"):
            robot.disconnect()

    def __enter__(self) -> NeroArm:
        return self.connect()

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()

    def wait_for_snapshot(self, *, timeout: float = 5.0, poll_period: float = 0.05) -> ArmSnapshot:
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        if poll_period <= 0:
            raise ValueError("poll_period must be positive")

        robot = self.raw
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if hasattr(robot, "has_comm_error") and robot.has_comm_error():
                detail = robot.get_comm_error() if hasattr(robot, "get_comm_error") else "unknown"
                raise RuntimeError(f"NERO SDK communication error: {detail}")
            feedback = robot.get_joint_angles()
            values = _message(feedback)
            if values is not None:
                joints = tuple(float(value) for value in values)
                if len(joints) == 7:
                    tcp = robot.get_tcp_pose() if hasattr(robot, "get_tcp_pose") else None
                    status = robot.get_arm_status() if hasattr(robot, "get_arm_status") else None
                    return ArmSnapshot(
                        arm=self.endpoint.name,
                        channel=self.endpoint.channel,
                        joint_angles_rad=joints,
                        feedback_hz=getattr(feedback, "hz", None),
                        timestamp=getattr(feedback, "timestamp", None),
                        tcp_pose=_serializable(tcp),
                        arm_status=_serializable(status),
                    )
            time.sleep(poll_period)
        raise TimeoutError(
            f"no valid 7-joint feedback from {self.endpoint.name} on "
            f"{self.endpoint.channel} within {timeout:.1f}s"
        )
