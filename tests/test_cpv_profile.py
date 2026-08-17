from __future__ import annotations

import pytest

from nero_wrapper.cpv_profile import (
    audit_position_gain_profiles,
    audit_responsive_acceleration_profiles,
    apply_responsive_acceleration_profiles,
    apply_staged_acceleration_profiles,
    apply_staged_parameter,
    apply_staged_position_gain_profiles,
    read_joint_acceleration_limits,
    read_loop_gains,
    read_motion_profile,
    validate_staged_acceleration,
    validate_staged_position_gain,
)


@pytest.fixture(autouse=True)
def _skip_hardware_flash_settle_in_unit_tests(monkeypatch) -> None:
    monkeypatch.setattr(
        "nero_wrapper.cpv_profile.FLASH_SETTLE_DELAY_S",
        0.0,
    )
    monkeypatch.setattr(
        "nero_wrapper.cpv_profile.JOINT_LIMIT_SETTLE_DELAY_S",
        0.0,
    )


class FakeCpvRobot:
    def __init__(
        self,
        *,
        enabled: bool = False,
        fail_once: tuple[str, int] | None = None,
        write_bias: float = 0.0,
        read_timeouts_after_first_write: int = 0,
        acceleration_limits: tuple[float, ...] = (0.30,) * 7,
        fail_limit_once: tuple[int, float] | None = None,
    ) -> None:
        self.enabled = enabled
        self.fail_once = fail_once
        self.write_bias = write_bias
        self.read_timeouts_after_first_write = read_timeouts_after_first_write
        self.read_timeouts_remaining = 0
        self.first_write_seen = False
        self.acceleration_limits = list(acceleration_limits)
        self.fail_limit_once = fail_limit_once
        self.limit_failed = False
        self.limit_writes: list[tuple[int, float]] = []
        self.failed = False
        self.values = {
            "acc": [0.03] * 7,
            "dcc": [0.03] * 7,
            "cv": [1.50] * 7,
            "pp": [5.0] * 7,
            "kp": [0.8] * 7,
            "ki": [40.0] * 7,
        }
        self.writes: list[tuple[str, int, float]] = []

    def get_joints_enable_status_list(self):
        return [self.enabled] * 7

    def get_joint_acc_limits(self, joint: int, **_kwargs):
        return FakeJointLimitMessage(self.acceleration_limits[joint - 1])

    def set_joint_acc_limits(
        self,
        joint: int,
        *,
        max_joint_acc: float,
        **_kwargs,
    ) -> bool:
        self.limit_writes.append((joint, max_joint_acc))
        self.acceleration_limits[joint - 1] = max_joint_acc
        if (
            self.fail_limit_once == (joint, max_joint_acc)
            and not self.limit_failed
        ):
            self.limit_failed = True
            return False
        return True

    def __getattr__(self, name: str):
        if name.startswith("get_cpv_"):
            field = name.removeprefix("get_cpv_")

            def get_value(joint: int, **_kwargs):
                if self.read_timeouts_remaining > 0:
                    self.read_timeouts_remaining -= 1
                    return None
                return self.values[field][joint - 1]

            return get_value
        if name.startswith("set_cpv_"):
            field = name.removeprefix("set_cpv_")

            def set_value(joint: int, value: float, **_kwargs):
                self.writes.append((field, joint, value))
                if self.fail_once == (field, joint) and not self.failed:
                    self.failed = True
                    return False
                self.values[field][joint - 1] = round(
                    (value + self.write_bias) * 100.0
                ) / 100.0
                if not self.first_write_seen:
                    self.first_write_seen = True
                    self.read_timeouts_remaining = (
                        self.read_timeouts_after_first_write
                    )
                return True

            return set_value
        raise AttributeError(name)


class FakeJointLimitMessage:
    def __init__(self, value: float) -> None:
        self.msg = type("Limit", (), {"max_joint_acc": value})()


def test_read_joint_acceleration_limits_keeps_joint_order() -> None:
    class FakeLimitRobot:
        @staticmethod
        def get_joint_acc_limits(joint: int, **_kwargs):
            return FakeJointLimitMessage(joint / 10.0)

    assert read_joint_acceleration_limits(FakeLimitRobot()) == pytest.approx(
        [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7]
    )


def test_read_motion_profile_keeps_acceleration_and_velocity_units() -> None:
    profile = read_motion_profile(FakeCpvRobot())

    assert profile.acc == pytest.approx([0.03] * 7)
    assert profile.dcc == pytest.approx([0.03] * 7)
    assert profile.cv == pytest.approx([1.50] * 7)


def test_read_loop_gains_keeps_joint_order() -> None:
    gains = read_loop_gains(FakeCpvRobot())

    assert gains.pp == pytest.approx([5.0] * 7)
    assert gains.kp == pytest.approx([0.8] * 7)
    assert gains.ki == pytest.approx([40.0] * 7)


def test_launch_audit_accepts_matching_disabled_profile() -> None:
    robot = FakeCpvRobot(acceleration_limits=(2.0,) * 7)
    robot.values["acc"] = [2.0] * 7
    robot.values["dcc"] = [2.0] * 7

    result = audit_responsive_acceleration_profiles({"arm_a": robot}, 2.0)

    assert result["arm_a"]["motors_disabled"] is True
    assert result["arm_a"]["joint_acceleration_limits"] == pytest.approx(
        [2.0] * 7
    )


def test_launch_audit_rejects_stale_persistent_profile_without_writing() -> None:
    robot = FakeCpvRobot(
        acceleration_limits=(0.035, 0.035) + (0.037,) * 5
    )

    with pytest.raises(RuntimeError, match="launch audit failed"):
        audit_responsive_acceleration_profiles({"arm_a": robot}, 2.0)

    assert robot.limit_writes == []
    assert robot.writes == []


def test_launch_audit_requires_disabled_motors() -> None:
    robot = FakeCpvRobot(enabled=True, acceleration_limits=(2.0,) * 7)
    robot.values["acc"] = [2.0] * 7
    robot.values["dcc"] = [2.0] * 7

    with pytest.raises(RuntimeError, match="motors are not all disabled"):
        audit_responsive_acceleration_profiles({"arm_a": robot}, 2.0)


def test_position_gain_launch_audit_accepts_matching_disabled_profile() -> None:
    robot = FakeCpvRobot()
    robot.values["pp"] = [10.0] * 7

    result = audit_position_gain_profiles({"arm_a": robot}, 10.0)

    assert result["arm_a"]["motors_disabled"] is True
    assert result["arm_a"]["position_gains"] == pytest.approx([10.0] * 7)
    assert robot.writes == []


def test_position_gain_launch_audit_rejects_stale_profile_without_writing() -> None:
    robot = FakeCpvRobot()

    with pytest.raises(RuntimeError, match="position gain launch audit failed"):
        audit_position_gain_profiles({"arm_a": robot}, 10.0)

    assert robot.writes == []


def test_staged_write_requires_every_motor_disabled() -> None:
    robot = FakeCpvRobot(enabled=True)

    with pytest.raises(RuntimeError, match="motors must be confirmed disabled"):
        apply_staged_acceleration_profiles({"arm_a": robot}, 0.10)

    assert robot.writes == []


@pytest.mark.parametrize("target", [0.04, 0.10])
def test_staged_write_rejects_target_above_firmware_joint_limit(
    target: float,
) -> None:
    robot = FakeCpvRobot(acceleration_limits=(0.035, 0.035) + (0.037,) * 5)

    with pytest.raises(RuntimeError, match="exceeds joint 1 firmware"):
        apply_staged_acceleration_profiles({"arm_a": robot}, target)

    assert robot.writes == []


def test_dual_arm_staging_writes_acc_and_dcc_then_reads_back() -> None:
    robots = {"arm_a": FakeCpvRobot(), "arm_b": FakeCpvRobot()}

    profiles = apply_staged_acceleration_profiles(robots, 0.10)

    for name, robot in robots.items():
        assert robot.values["acc"] == pytest.approx([0.10] * 7)
        assert robot.values["dcc"] == pytest.approx([0.10] * 7)
        assert robot.values["cv"] == pytest.approx([1.50] * 7)
        assert len(robot.writes) == 14
        assert profiles[name][0].acc == pytest.approx([0.03] * 7)
        assert profiles[name][1].acc == pytest.approx([0.10] * 7)


def test_staging_learns_one_quantum_firmware_write_bias() -> None:
    robot = FakeCpvRobot(write_bias=-0.01)

    profiles = apply_staged_acceleration_profiles({"arm_a": robot}, 0.10)

    assert robot.values["acc"] == pytest.approx([0.10] * 7)
    assert robot.values["dcc"] == pytest.approx([0.10] * 7)
    assert robot.values["cv"] == pytest.approx([1.50] * 7)
    assert robot.writes[:2] == [
        ("acc", 1, pytest.approx(0.10)),
        ("acc", 1, pytest.approx(0.11)),
    ]
    assert profiles["arm_a"][1].acc == pytest.approx([0.10] * 7)


def test_ack_then_readback_timeout_rolls_current_field_back(monkeypatch) -> None:
    monkeypatch.setattr(
        "nero_wrapper.cpv_profile.READBACK_RETRY_DELAY_S",
        0.0,
    )
    robot = FakeCpvRobot(read_timeouts_after_first_write=3)

    with pytest.raises(RuntimeError, match="no finite CPV acc read-back"):
        apply_staged_acceleration_profiles({"arm_a": robot}, 0.10)

    assert robot.values["acc"] == pytest.approx([0.03] * 7)
    assert robot.values["dcc"] == pytest.approx([0.03] * 7)
    assert robot.writes[:2] == [
        ("acc", 1, pytest.approx(0.10)),
        ("acc", 1, pytest.approx(0.03)),
    ]


def test_single_parameter_repair_touches_only_selected_field() -> None:
    robot = FakeCpvRobot(write_bias=-0.01)
    robot.values["acc"][0] = 0.09

    before, after = apply_staged_parameter(
        robot,
        field="acc",
        joint=1,
        value=0.03,
    )

    assert before == pytest.approx(0.09)
    assert after == pytest.approx(0.03)
    assert robot.values["acc"] == pytest.approx([0.03] * 7)
    assert robot.values["dcc"] == pytest.approx([0.03] * 7)
    assert robot.writes == [
        ("acc", 1, pytest.approx(0.03)),
        ("acc", 1, pytest.approx(0.04)),
    ]


def test_responsive_staging_updates_limits_then_cpv_atomically() -> None:
    initial = (0.035, 0.035) + (0.037,) * 5
    robots = {
        "arm_a": FakeCpvRobot(acceleration_limits=initial),
        "arm_b": FakeCpvRobot(acceleration_limits=initial),
    }

    profiles = apply_responsive_acceleration_profiles(robots, 2.0)

    for name, robot in robots.items():
        assert robot.acceleration_limits == pytest.approx([2.0] * 7)
        assert robot.values["acc"] == pytest.approx([2.0] * 7)
        assert robot.values["dcc"] == pytest.approx([2.0] * 7)
        assert robot.values["cv"] == pytest.approx([1.50] * 7)
        assert profiles[name]["joint_limits_after"] == pytest.approx(
            [2.0] * 7
        )
        assert profiles[name]["cpv_before"]["acc"] == pytest.approx(
            [0.03] * 7
        )


def test_responsive_rollback_restores_cpv_after_coupled_limit_write() -> None:
    class CoupledFakeCpvRobot(FakeCpvRobot):
        def set_joint_acc_limits(
            self,
            joint: int,
            *,
            max_joint_acc: float,
            **kwargs,
        ) -> bool:
            result = super().set_joint_acc_limits(
                joint,
                max_joint_acc=max_joint_acc,
                **kwargs,
            )
            # CPV fields have 0.01 resolution even though the lower-level
            # joint limit has 0.0001 resolution.
            coupled = round(max_joint_acc * 100.0) / 100.0
            self.values["acc"][joint - 1] = coupled
            self.values["dcc"][joint - 1] = coupled
            return result

    initial = (0.035, 0.035) + (0.037,) * 5
    arm_a = CoupledFakeCpvRobot(
        acceleration_limits=initial,
        fail_limit_once=(3, 0.05),
    )

    with pytest.raises(RuntimeError, match="responsive acceleration staging"):
        apply_responsive_acceleration_profiles({"arm_a": arm_a}, 0.05)

    assert arm_a.acceleration_limits == pytest.approx(initial)
    assert arm_a.values["acc"] == pytest.approx([0.03] * 7)
    assert arm_a.values["dcc"] == pytest.approx([0.03] * 7)


def test_responsive_staging_rolls_limits_back_after_cpv_failure() -> None:
    initial = (0.035, 0.035) + (0.037,) * 5
    arm_a = FakeCpvRobot(
        acceleration_limits=initial,
        fail_once=("acc", 2),
    )
    arm_b = FakeCpvRobot(acceleration_limits=initial)

    with pytest.raises(RuntimeError, match="responsive acceleration staging"):
        apply_responsive_acceleration_profiles(
            {"arm_a": arm_a, "arm_b": arm_b},
            0.05,
        )

    for robot in (arm_a, arm_b):
        assert robot.acceleration_limits == pytest.approx(initial)
        assert robot.values["acc"] == pytest.approx([0.03] * 7)
        assert robot.values["dcc"] == pytest.approx([0.03] * 7)


def test_late_second_arm_failure_rolls_back_both_arms() -> None:
    arm_a = FakeCpvRobot()
    arm_b = FakeCpvRobot(fail_once=("acc", 2))

    with pytest.raises(RuntimeError, match="did not ACK"):
        apply_staged_acceleration_profiles(
            {"arm_a": arm_a, "arm_b": arm_b},
            0.10,
        )

    for robot in (arm_a, arm_b):
        assert robot.values["acc"] == pytest.approx([0.03] * 7)
        assert robot.values["dcc"] == pytest.approx([0.03] * 7)


def test_dual_arm_position_gain_staging_touches_only_pp() -> None:
    robots = {"arm_a": FakeCpvRobot(), "arm_b": FakeCpvRobot()}

    profiles = apply_staged_position_gain_profiles(robots, 10.0)

    for name, robot in robots.items():
        assert robot.values["pp"] == pytest.approx([10.0] * 7)
        assert robot.values["kp"] == pytest.approx([0.8] * 7)
        assert robot.values["ki"] == pytest.approx([40.0] * 7)
        assert robot.values["acc"] == pytest.approx([0.03] * 7)
        assert robot.values["dcc"] == pytest.approx([0.03] * 7)
        assert robot.writes == [
            ("pp", joint, pytest.approx(10.0)) for joint in range(1, 8)
        ]
        assert profiles[name][0] == pytest.approx([5.0] * 7)
        assert profiles[name][1] == pytest.approx([10.0] * 7)


def test_position_gain_late_failure_rolls_back_both_arms() -> None:
    arm_a = FakeCpvRobot()
    arm_b = FakeCpvRobot(fail_once=("pp", 2))

    with pytest.raises(RuntimeError, match="CPV pp staging failed"):
        apply_staged_position_gain_profiles(
            {"arm_a": arm_a, "arm_b": arm_b},
            10.0,
        )

    for robot in (arm_a, arm_b):
        assert robot.values["pp"] == pytest.approx([5.0] * 7)
        assert robot.values["kp"] == pytest.approx([0.8] * 7)
        assert robot.values["ki"] == pytest.approx([40.0] * 7)


def test_position_gain_staging_requires_disabled_motors() -> None:
    robot = FakeCpvRobot(enabled=True)

    with pytest.raises(RuntimeError, match="motors must be confirmed disabled"):
        apply_staged_position_gain_profiles({"arm_a": robot}, 10.0)

    assert robot.writes == []


@pytest.mark.parametrize("value", [0.02, 2.01, float("nan")])
def test_staged_acceleration_is_bounded(value: float) -> None:
    with pytest.raises(ValueError, match="between 0.03 and 2.00"):
        validate_staged_acceleration(value)


@pytest.mark.parametrize("value", [0.0, 10.01, float("nan")])
def test_staged_position_gain_is_bounded(value: float) -> None:
    with pytest.raises(ValueError, match="between 0.01 and 10.00"):
        validate_staged_position_gain(value)
