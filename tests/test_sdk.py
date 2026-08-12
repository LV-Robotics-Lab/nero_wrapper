from __future__ import annotations

from dataclasses import dataclass

import pytest

from nero_wrapper import NeroArm, NeroConfig


@dataclass
class FakeFeedback:
    msg: list[float]
    hz: float = 200.0
    timestamp: int = 123


class FakeRobot:
    def __init__(self, feedback: FakeFeedback) -> None:
        self.feedback = feedback
        self.connected = False
        self.disconnected = False

    def connect(self) -> None:
        self.connected = True

    def disconnect(self) -> None:
        self.disconnected = True

    def has_comm_error(self) -> bool:
        return False

    def get_joint_angles(self) -> FakeFeedback:
        return self.feedback

    def get_tcp_pose(self) -> FakeFeedback:
        return FakeFeedback([0.1, 0.2, 0.3])

    def get_arm_status(self) -> FakeFeedback:
        return FakeFeedback([0])


class FailingRobot(FakeRobot):
    def connect(self) -> None:
        raise RuntimeError("connection failed")


class FakeFactory:
    robot: FakeRobot
    expected_channel = "can_arm_b"

    @classmethod
    def create_arm(cls, config: object) -> FakeRobot:
        assert config == {"channel": cls.expected_channel, "firmware": "fw-v112"}
        return cls.robot


class FakeSdk:
    class ArmModel:
        NERO = "nero"

    class NeroFW:
        DEFAULT = "fw-default"
        V111 = "fw-v111"
        V112 = "fw-v112"
        V120 = "fw-v120"

    AgxArmFactory = FakeFactory

    @staticmethod
    def create_agx_arm_config(**kwargs: object) -> dict[str, object]:
        assert kwargs["robot"] == "nero"
        assert kwargs["interface"] == "socketcan"
        return {"channel": kwargs["channel"], "firmware": kwargs["firmeware_version"]}


def test_context_manager_reads_snapshot_and_disconnects() -> None:
    robot = FakeRobot(FakeFeedback([0.0] * 7))
    FakeFactory.robot = robot
    FakeFactory.expected_channel = "can_arm_b"
    config = NeroConfig.from_env({})

    with NeroArm("arm_b", config=config, sdk=FakeSdk) as arm:
        snapshot = arm.wait_for_snapshot(timeout=0.1, poll_period=0.001)

    assert robot.connected
    assert robot.disconnected
    assert snapshot.arm == "arm_b"
    assert snapshot.channel == "can_arm_b"
    assert snapshot.joint_angles_rad == (0.0,) * 7
    assert snapshot.feedback_hz == 200.0


def test_invalid_feedback_times_out() -> None:
    robot = FakeRobot(FakeFeedback([0.0] * 6))
    FakeFactory.robot = robot
    FakeFactory.expected_channel = "can_arm_a"
    config = NeroConfig.from_env({})

    with NeroArm("arm_a", config=config, sdk=FakeSdk) as arm:
        with pytest.raises(TimeoutError, match="no valid 7-joint feedback"):
            arm.wait_for_snapshot(timeout=0.01, poll_period=0.001)


def test_connect_failure_releases_vendor_handle() -> None:
    robot = FailingRobot(FakeFeedback([0.0] * 7))
    FakeFactory.robot = robot
    FakeFactory.expected_channel = "can_arm_a"
    config = NeroConfig.from_env({})

    with pytest.raises(RuntimeError, match="connection failed"):
        NeroArm("arm_a", config=config, sdk=FakeSdk).connect()

    assert robot.disconnected
