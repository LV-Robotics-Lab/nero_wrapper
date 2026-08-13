import struct

import pytest

from nero_wrapper.payload_protocol import (
    CAN_EFF_FLAG,
    CAN_FRAME_STRUCT,
    PAYLOAD_CONFIG_CAN_ID,
    SET_INSTRUCTION_ACK_CAN_ID,
    is_payload_setting_ack,
    pack_standard_can_frame,
    payload_config_data,
    unpack_standard_can_frame,
)


def test_1010g_half_load_uses_nero_v121_bytes() -> None:
    assert payload_config_data("half") == bytes.fromhex("00 00 00 AE 01 00 00 00")


def test_protocol_levels_are_not_piper_offset_values() -> None:
    assert payload_config_data("empty")[4] == 0x00
    assert payload_config_data("half")[4] == 0x01
    assert payload_config_data("full")[4] == 0x02


def test_invalid_level_is_rejected_before_can_write() -> None:
    with pytest.raises(ValueError, match="empty, half, full"):
        payload_config_data("1010g")


def test_socketcan_frame_round_trip() -> None:
    data = payload_config_data("half")
    frame = pack_standard_can_frame(PAYLOAD_CONFIG_CAN_ID, data)
    assert len(frame) == 16
    assert unpack_standard_can_frame(frame) == (PAYLOAD_CONFIG_CAN_ID, data)


@pytest.mark.parametrize("can_id", [-1, 0x800])
def test_pack_rejects_non_standard_can_ids(can_id: int) -> None:
    with pytest.raises(ValueError, match="11-bit"):
        pack_standard_can_frame(can_id, b"")


def test_pack_rejects_oversize_classic_can_payload() -> None:
    with pytest.raises(ValueError, match="must not exceed 8"):
        pack_standard_can_frame(0x477, b"123456789")


def test_unpack_rejects_extended_frame_and_bad_length() -> None:
    extended = CAN_FRAME_STRUCT.pack(CAN_EFF_FLAG | 0x477, 1, b"x".ljust(8, b"\x00"))
    with pytest.raises(ValueError, match="standard CAN"):
        unpack_standard_can_frame(extended)

    invalid_length = struct.pack("=IB3x8s", 0x477, 9, b"12345678")
    with pytest.raises(ValueError, match="data length"):
        unpack_standard_can_frame(invalid_length)


def test_only_payload_instruction_ack_is_accepted() -> None:
    assert is_payload_setting_ack(
        SET_INSTRUCTION_ACK_CAN_ID,
        bytes.fromhex("77 00 00 00 00 00 00 00"),
    )
    assert not is_payload_setting_ack(
        SET_INSTRUCTION_ACK_CAN_ID,
        bytes.fromhex("75 00 00 00 00 00 00 00"),
    )
    assert not is_payload_setting_ack(PAYLOAD_CONFIG_CAN_ID, b"\x77")
