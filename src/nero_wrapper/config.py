"""Typed NERO hardware configuration loaded from environment variables.

The wrapper deliberately excludes Wi-Fi and Web UI credentials. Store those in
``config/nero.local.env`` on the robot workstation; that file is gitignored.
"""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from dataclasses import asdict, dataclass

_NAME_RE = re.compile(r"^[A-Za-z0-9_.:-]+$")
_SUPPORTED_FIRMWARE = frozenset({"default", "v111", "v112", "v120"})


def _value(env: Mapping[str, str], name: str, default: str) -> str:
    value = env.get(name, default).strip()
    if not value:
        raise ValueError(f"{name} cannot be empty")
    return value


def _integer(env: Mapping[str, str], name: str, default: int) -> int:
    raw = env.get(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer, got {raw!r}") from exc
    if value <= 0:
        raise ValueError(f"{name} must be positive, got {value}")
    return value


@dataclass(frozen=True, slots=True)
class CanEndpoint:
    """A physical SocketCAN endpoint with stable USB provenance."""

    name: str
    channel: str
    usb_bus_info: str

    def __post_init__(self) -> None:
        for field_name, value in (("name", self.name), ("channel", self.channel)):
            if not value or not _NAME_RE.fullmatch(value):
                raise ValueError(f"invalid {field_name}: {value!r}")
        if not self.usb_bus_info:
            raise ValueError("usb_bus_info cannot be empty")


@dataclass(frozen=True, slots=True)
class ArmEndpoint(CanEndpoint):
    """NERO arm endpoint."""

    namespace: str

    def __post_init__(self) -> None:
        CanEndpoint.__post_init__(self)
        normalized = self.namespace.removeprefix("/")
        if not normalized or not _NAME_RE.fullmatch(normalized):
            raise ValueError(f"invalid ROS namespace: {self.namespace!r}")
        object.__setattr__(self, "namespace", normalized)


@dataclass(frozen=True, slots=True)
class HandEndpoint(CanEndpoint):
    """LinkerHand endpoint attached to a NERO wrist."""

    side: str
    can_id: str

    def __post_init__(self) -> None:
        CanEndpoint.__post_init__(self)
        if self.side not in {"left", "right"}:
            raise ValueError(f"hand side must be left or right, got {self.side!r}")
        try:
            can_id = int(self.can_id, 16)
        except ValueError:
            raise ValueError(f"CAN id must be hexadecimal, got {self.can_id!r}") from None
        if not 0 <= can_id <= 0x7FF:
            raise ValueError(f"CAN id must be an 11-bit value, got {self.can_id!r}")


@dataclass(frozen=True, slots=True)
class NeroConfig:
    """Stable, non-secret configuration for one dual-arm NERO rig."""

    firmware: str
    can_interface: str
    bitrate: int
    arms: tuple[ArmEndpoint, ArmEndpoint]
    hands: tuple[HandEndpoint, HandEndpoint]
    container_image: str
    ros_workspace: str

    def __post_init__(self) -> None:
        if self.firmware not in _SUPPORTED_FIRMWARE:
            supported = ", ".join(sorted(_SUPPORTED_FIRMWARE))
            raise ValueError(f"unsupported firmware {self.firmware!r}; choose {supported}")
        if not self.can_interface:
            raise ValueError("can_interface cannot be empty")
        if self.bitrate <= 0:
            raise ValueError("bitrate must be positive")

        endpoints: tuple[CanEndpoint, ...] = (*self.arms, *self.hands)
        channels = [endpoint.channel for endpoint in endpoints]
        if len(set(channels)) != len(channels):
            raise ValueError(f"CAN channels must be unique, got {channels!r}")
        usb_paths = [endpoint.usb_bus_info for endpoint in endpoints]
        if len(set(usb_paths)) != len(usb_paths):
            raise ValueError(f"USB bus paths must be unique, got {usb_paths!r}")
        namespaces = [arm.namespace for arm in self.arms]
        if len(set(namespaces)) != len(namespaces):
            raise ValueError(f"arm namespaces must be unique, got {namespaces!r}")

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> NeroConfig:
        values = os.environ if env is None else env
        arm_a = ArmEndpoint(
            name="arm_a",
            channel=_value(values, "NERO_ARM_A_CAN_PORT", "can_arm_a"),
            usb_bus_info=_value(values, "NERO_ARM_A_USB_BUS_INFO", "1-3.4.1:1.0"),
            namespace=_value(values, "NERO_ARM_A_ROS_NAMESPACE", "arm_a"),
        )
        arm_b = ArmEndpoint(
            name="arm_b",
            channel=_value(values, "NERO_ARM_B_CAN_PORT", "can_arm_b"),
            usb_bus_info=_value(values, "NERO_ARM_B_USB_BUS_INFO", "1-3.4.3:1.0"),
            namespace=_value(values, "NERO_ARM_B_ROS_NAMESPACE", "arm_b"),
        )
        left_hand = HandEndpoint(
            name="left_hand",
            side="left",
            channel=_value(values, "NERO_LEFT_HAND_CAN_PORT", "can1"),
            usb_bus_info=_value(values, "NERO_LEFT_HAND_USB_BUS_INFO", "1-3.4.4:1.0"),
            can_id=_value(values, "NERO_LEFT_HAND_CAN_ID", "0x28"),
        )
        right_hand = HandEndpoint(
            name="right_hand",
            side="right",
            channel=_value(values, "NERO_RIGHT_HAND_CAN_PORT", "can2"),
            usb_bus_info=_value(values, "NERO_RIGHT_HAND_USB_BUS_INFO", "1-3.4.2:1.0"),
            can_id=_value(values, "NERO_RIGHT_HAND_CAN_ID", "0x27"),
        )
        return cls(
            firmware=_value(values, "NERO_FW", "v112").lower(),
            can_interface=_value(values, "NERO_CAN_INTERFACE", "socketcan"),
            bitrate=_integer(values, "NERO_CAN_BITRATE", 1_000_000),
            arms=(arm_a, arm_b),
            hands=(left_hand, right_hand),
            container_image=_value(values, "NERO_CONTAINER_IMAGE", "nero-humble:local"),
            ros_workspace=_value(
                values,
                "NERO_ROS_WS",
                os.path.expanduser("~/agx_arm_ws"),
            ),
        )

    def arm(self, name: str) -> ArmEndpoint:
        normalized = name.lower().removeprefix("arm_")
        target = f"arm_{normalized}"
        for arm in self.arms:
            if arm.name == target:
                return arm
        raise KeyError(f"unknown arm {name!r}; choose arm_a or arm_b")

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-safe view. Credentials are never part of this model."""

        return asdict(self)
