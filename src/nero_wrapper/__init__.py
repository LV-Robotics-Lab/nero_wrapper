"""Public API for the NERO hardware wrapper."""

from .config import ArmEndpoint, CanEndpoint, HandEndpoint, NeroConfig
from .dual_model import (
    ARM_NAMES,
    HARDWARE_TO_MODEL_JOINT_OFFSETS,
    LAB_DUAL_BENCH_BASE_TRANSFORMS,
    BaseTransform,
    build_dual_nero_urdf,
    collision_pairs,
    load_dual_nero_model,
)
from .model import NERO_JOINT_LIMITS_RAD, NERO_JOINT_NAMES, validate_joint_positions
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
    "ARM_NAMES",
    "BaseTransform",
    "CanEndpoint",
    "HandEndpoint",
    "HARDWARE_TO_MODEL_JOINT_OFFSETS",
    "LAB_DUAL_BENCH_BASE_TRANSFORMS",
    "MotionGate",
    "NeroArm",
    "NeroConfig",
    "NeroSdkUnavailable",
    "NERO_JOINT_LIMITS_RAD",
    "NERO_JOINT_NAMES",
    "PAYLOAD_CONFIG_CAN_ID",
    "SafetyGateError",
    "SET_INSTRUCTION_ACK_CAN_ID",
    "is_payload_setting_ack",
    "build_dual_nero_urdf",
    "collision_pairs",
    "load_dual_nero_model",
    "pack_standard_can_frame",
    "payload_config_data",
    "unpack_standard_can_frame",
    "validate_joint_positions",
    "validate_joint_delta",
]
