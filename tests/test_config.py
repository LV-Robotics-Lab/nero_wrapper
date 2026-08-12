from __future__ import annotations

import pytest

from nero_wrapper import NeroConfig


def test_default_config_has_four_unique_can_channels() -> None:
    config = NeroConfig.from_env({})

    assert config.firmware == "v112"
    assert [endpoint.channel for endpoint in (*config.arms, *config.hands)] == [
        "can_arm_a",
        "can_arm_b",
        "can1",
        "can2",
    ]
    assert config.arm("a").namespace == "arm_a"
    assert "password" not in repr(config.as_dict()).lower()


def test_environment_overrides_are_validated() -> None:
    config = NeroConfig.from_env(
        {
            "NERO_FW": "v120",
            "NERO_CAN_BITRATE": "500000",
            "NERO_ARM_A_ROS_NAMESPACE": "/right_arm",
        }
    )

    assert config.firmware == "v120"
    assert config.bitrate == 500_000
    assert config.arm("arm_a").namespace == "right_arm"


def test_duplicate_channels_fail_closed() -> None:
    with pytest.raises(ValueError, match="CAN channels must be unique"):
        NeroConfig.from_env({"NERO_RIGHT_HAND_CAN_PORT": "can_arm_a"})


def test_invalid_bitrate_has_actionable_error() -> None:
    with pytest.raises(ValueError, match="NERO_CAN_BITRATE must be an integer"):
        NeroConfig.from_env({"NERO_CAN_BITRATE": "fast"})
