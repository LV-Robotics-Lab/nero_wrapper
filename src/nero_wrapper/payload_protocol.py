"""Pure codecs for the NERO V1.2.1 end-payload CAN protocol.

This module performs no I/O. It only constructs and validates bytes so callers
can test the safety-critical protocol before opening SocketCAN.
"""

from __future__ import annotations

import struct

PAYLOAD_CONFIG_CAN_ID = 0x477
SET_INSTRUCTION_ACK_CAN_ID = 0x476
SET_INSTRUCTION_PAYLOAD_INDEX = 0x77

# NERO protocol V1.2.1, CAN 0x477 byte 4. These values are not the legacy
# Piper enum; Piper values are offset and must not be substituted here.
PAYLOAD_LEVEL_CODES = {
    "empty": 0x00,
    "half": 0x01,
    "full": 0x02,
}

CAN_SFF_MASK = 0x7FF
CAN_EFF_FLAG = 0x80000000
CAN_RTR_FLAG = 0x40000000
CAN_ERR_FLAG = 0x20000000
CAN_FRAME_STRUCT = struct.Struct("=IB3x8s")


def payload_config_data(level: str) -> bytes:
    """Return the exact eight data bytes for NERO CAN command ``0x477``."""

    try:
        code = PAYLOAD_LEVEL_CODES[level]
    except KeyError as exc:
        allowed = ", ".join(PAYLOAD_LEVEL_CODES)
        raise ValueError(f"payload level must be one of: {allowed}") from exc
    # Byte 3 0xAE applies the setting; byte 4 selects the firmware level.
    return bytes((0x00, 0x00, 0x00, 0xAE, code, 0x00, 0x00, 0x00))


def pack_standard_can_frame(can_id: int, data: bytes) -> bytes:
    """Pack a Linux ``struct can_frame`` for a standard 11-bit CAN ID."""

    if not 0 <= can_id <= CAN_SFF_MASK:
        raise ValueError("can_id must be an 11-bit standard CAN identifier")
    if len(data) > 8:
        raise ValueError("classic CAN data must not exceed 8 bytes")
    return CAN_FRAME_STRUCT.pack(can_id, len(data), data.ljust(8, b"\x00"))


def unpack_standard_can_frame(frame: bytes) -> tuple[int, bytes]:
    """Unpack classic CAN and reject extended, RTR, error, or invalid frames."""

    if len(frame) != CAN_FRAME_STRUCT.size:
        raise ValueError(f"classic CAN frame must be {CAN_FRAME_STRUCT.size} bytes")
    raw_can_id, data_length, data = CAN_FRAME_STRUCT.unpack(frame)
    if raw_can_id & (CAN_EFF_FLAG | CAN_RTR_FLAG | CAN_ERR_FLAG):
        raise ValueError("expected a standard CAN data frame")
    if data_length > 8:
        raise ValueError("invalid classic CAN data length")
    return raw_can_id & CAN_SFF_MASK, data[:data_length]


def is_payload_setting_ack(can_id: int, data: bytes) -> bool:
    """Recognize the ``0x476`` ACK for payload-setting instruction ``0x77``."""

    return (
        can_id == SET_INSTRUCTION_ACK_CAN_ID
        and len(data) >= 1
        and data[0] == SET_INSTRUCTION_PAYLOAD_INDEX
    )
