"""Public API for the NERO hardware wrapper."""

from .config import ArmEndpoint, CanEndpoint, HandEndpoint, NeroConfig
from .payload_protocol import (
    PAYLOAD_CONFIG_CAN_ID,
    SET_INSTRUCTION_ACK_CAN_ID,
    is_payload_setting_ack,
    pack_standard_can_frame,
    payload_config_data,
    unpack_standard_can_frame,
)
from .safety import MotionGate, SafetyGateError, validate_joint_delta
from .sdk import ArmSnapshot, NeroArm, NeroSdkUnavailable

__all__ = [
    "ArmEndpoint",
    "ArmSnapshot",
    "CanEndpoint",
    "HandEndpoint",
    "MotionGate",
    "NeroArm",
    "NeroConfig",
    "NeroSdkUnavailable",
    "PAYLOAD_CONFIG_CAN_ID",
    "SafetyGateError",
    "SET_INSTRUCTION_ACK_CAN_ID",
    "is_payload_setting_ack",
    "pack_standard_can_frame",
    "payload_config_data",
    "unpack_standard_can_frame",
    "validate_joint_delta",
]
