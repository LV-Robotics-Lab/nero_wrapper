from __future__ import annotations

import math
import time
import unittest
from types import SimpleNamespace

import numpy as np

from xrobotoolkit_teleop.hardware.interface.nero import (
    NERO_JOINT_LIMITS,
    NeroArmInterface,
    NeroSafetyError,
    resolve_nero_firmware_selector,
    validate_joint_target,
)


class Feedback:
    def __init__(self, msg, hz: float = 200.0):
        self.msg = msg
        self.hz = hz
        self.timestamp = time.time()


class FakeRobot:
    def __init__(self, missing_motor: int | None = None):
        self.joints = np.zeros(7)
        self.missing_motor = missing_motor
        self.connected = False
        self.enabled = False
        self.moves = []
        self.speed_percent = None
        errors = SimpleNamespace(
            joint_1_angle_limit=False,
            communication_status_joint_1=False,
        )
        self.status = SimpleNamespace(
            ctrl_mode=1,
            arm_status=0,
            motion_status=0,
            err_status=errors,
        )

    def connect(self):
        self.connected = True

    def disconnect(self):
        self.connected = False

    def has_comm_error(self):
        return False

    def get_joint_angles(self):
        return Feedback(self.joints.copy(), hz=50.0)

    def get_arm_status(self):
        return Feedback(self.status)

    def get_motor_states(self, index):
        if index == self.missing_motor:
            return None
        return Feedback(SimpleNamespace(position=float(self.joints[index - 1])))

    def get_flange_pose(self):
        return Feedback(np.zeros(6))

    def get_joint_enable_status(self, index):
        if index == 255:
            return self.enabled
        return self.enabled

    def set_speed_percent(self, value):
        self.speed_percent = value

    def enable(self, timeout=1.5):
        self.enabled = True
        return True

    def disable(self, timeout=1.5):
        self.enabled = False
        return True

    def move_j(self, target):
        self.joints = np.asarray(target, dtype=np.float64)
        self.moves.append(self.joints.copy())


class DelayedArmStatusRobot(FakeRobot):
    def __init__(self, delay_reads: int, stuck: bool = False):
        super().__init__()
        self.delay_reads = delay_reads
        self.stuck = stuck
        self.post_enable_reads = 0

    def enable(self, timeout=1.5):
        self.enabled = True
        self.status.arm_status = 6
        return True

    def get_arm_status(self):
        if self.enabled:
            self.post_enable_reads += 1
            if not self.stuck and self.post_enable_reads > self.delay_reads:
                self.status.arm_status = 0
        return Feedback(self.status)


class CurrentHoldClearsEmergencyStopRobot(FakeRobot):
    def enable(self, timeout=1.5):
        self.enabled = True
        self.status.arm_status = 1
        return True

    def move_j(self, target):
        super().move_j(target)
        self.status.arm_status = 0


class ValidateJointTargetTests(unittest.TestCase):
    def test_accepts_bounded_target(self):
        current = np.zeros(7)
        target = np.full(7, math.radians(0.25))
        actual = validate_joint_target(
            current,
            target,
            joint_limit_margin_rad=math.radians(3.0),
            max_joint_step_rad=math.radians(0.75),
        )
        np.testing.assert_allclose(actual, target)

    def test_rejects_large_step(self):
        with self.assertRaisesRegex(NeroSafetyError, "per-command limit"):
            validate_joint_target(
                np.zeros(7),
                np.array([math.radians(1.0), 0, 0, 0, 0, 0, 0]),
                joint_limit_margin_rad=0.0,
                max_joint_step_rad=math.radians(0.75),
            )

    def test_rejects_guarded_joint_limit(self):
        target = np.zeros(7)
        target[5] = NERO_JOINT_LIMITS[5, 1] - math.radians(1.0)
        with self.assertRaisesRegex(NeroSafetyError, "guarded interval"):
            validate_joint_target(
                np.zeros(7),
                target,
                joint_limit_margin_rad=math.radians(3.0),
                max_joint_step_rad=2.0,
            )


class FirmwareSelectorTests(unittest.TestCase):
    def test_resolves_official_driver_families(self):
        self.assertEqual(resolve_nero_firmware_selector("1.10"), "default")
        self.assertEqual(resolve_nero_firmware_selector("1.11"), "v111")
        self.assertEqual(resolve_nero_firmware_selector("1.12"), "v112")
        self.assertEqual(resolve_nero_firmware_selector("1.121"), "v112")
        self.assertEqual(resolve_nero_firmware_selector("1.20"), "v120")
        self.assertEqual(resolve_nero_firmware_selector("1.201"), "v120")

    def test_rejects_malformed_version(self):
        with self.assertRaisesRegex(NeroSafetyError, "version string"):
            resolve_nero_firmware_selector("unknown")


class NeroArmInterfaceTests(unittest.TestCase):
    def test_connect_requires_complete_motor_and_flange_feedback(self):
        robot = FakeRobot()
        arm = NeroArmInterface(arm_name="arm_a", channel="vcan0", robot=robot)
        state = arm.connect(timeout_s=0.1)
        self.assertEqual(state.joints.shape, (7,))
        arm.close(hold_if_armed=False)
        self.assertFalse(robot.connected)

    def test_connect_rejects_partial_sdk_aggregate(self):
        robot = FakeRobot(missing_motor=4)
        arm = NeroArmInterface(arm_name="arm_a", channel="vcan0", robot=robot)
        with self.assertRaisesRegex(TimeoutError, "joint4 motor-state"):
            arm.connect(timeout_s=0.03)
        arm.close(hold_if_armed=False)

    def test_live_command_is_armed_guarded_and_disabled_on_close(self):
        robot = FakeRobot()
        arm = NeroArmInterface(
            arm_name="arm_a",
            channel="vcan0",
            execute=True,
            robot=robot,
        )
        arm.connect(timeout_s=0.1)
        arm.arm()
        self.assertTrue(robot.enabled)
        self.assertEqual(robot.speed_percent, 5)

        target = np.full(7, math.radians(0.25))
        arm.command(target)
        np.testing.assert_allclose(robot.moves[-1], target)

        arm.close()
        self.assertFalse(robot.enabled)
        self.assertFalse(robot.connected)

    def test_close_still_disables_after_hold_failure(self):
        robot = FakeRobot()
        arm = NeroArmInterface(
            arm_name="arm_a",
            channel="vcan0",
            execute=True,
            robot=robot,
        )
        arm.connect(timeout_s=0.1)
        arm.arm()

        def fail_hold():
            raise NeroSafetyError("simulated feedback loss")

        arm.hold = fail_hold
        with self.assertRaisesRegex(NeroSafetyError, "shutdown failures"):
            arm.close()
        self.assertFalse(robot.enabled)
        self.assertFalse(robot.connected)

    def test_arm_waits_for_delayed_normal_status(self):
        robot = DelayedArmStatusRobot(delay_reads=2)
        arm = NeroArmInterface(
            arm_name="arm_a",
            channel="vcan0",
            execute=True,
            robot=robot,
        )
        arm.connect(timeout_s=0.1)
        arm.arm(timeout_s=0.3)
        self.assertTrue(arm.armed)
        self.assertTrue(robot.enabled)
        arm.close(hold_if_armed=False)
        self.assertFalse(robot.enabled)

    def test_arm_sends_current_position_hold_before_requiring_normal_status(self):
        robot = CurrentHoldClearsEmergencyStopRobot()
        robot.joints = np.array([0.1, -0.1, 0.2, 0.0, -0.2, 0.1, 0.0])
        arm = NeroArmInterface(
            arm_name="arm_a",
            channel="vcan0",
            execute=True,
            robot=robot,
        )
        arm.connect(timeout_s=0.1)
        arm.arm(timeout_s=0.3)
        self.assertTrue(arm.armed)
        np.testing.assert_allclose(robot.moves[0], robot.joints)
        arm.close(hold_if_armed=False)

    def test_failed_post_enable_status_is_always_disabled(self):
        robot = DelayedArmStatusRobot(delay_reads=100, stuck=True)
        arm = NeroArmInterface(
            arm_name="arm_b",
            channel="vcan1",
            execute=True,
            robot=robot,
        )
        arm.connect(timeout_s=0.1)
        with self.assertRaisesRegex(NeroSafetyError, "motion-safe state"):
            arm.arm(timeout_s=0.08)
        self.assertFalse(robot.enabled)
        self.assertFalse(arm.armed)
        arm.close(hold_if_armed=False)

    def test_arm_lets_enable_claim_can_control_from_ethernet_mode(self):
        # The official V112 enable() re-sends the 0x151 mode frame to take CAN
        # control back from an Ethernet client. arm() must therefore reach
        # enable() while ctrl_mode is still ETHERNET_CONTROL_MODE instead of
        # rejecting it up front -- gating earlier would block the only fix.
        class EthernetOwnedRobot(FakeRobot):
            def __init__(self):
                super().__init__()
                self.status.ctrl_mode = 3  # ETHERNET_CONTROL_MODE
                self.status.arm_status = 6  # JOINT_BRAKE_NOT_RELEASED

            def enable(self, timeout=1.5):
                # Mirror the official driver: claiming CAN control is part of
                # enabling, not a precondition for it.
                self.status.ctrl_mode = 1
                self.status.arm_status = 0
                self.enabled = True
                return True

        robot = EthernetOwnedRobot()
        arm = NeroArmInterface(
            arm_name="arm_b",
            channel="vcan1",
            execute=True,
            robot=robot,
        )
        arm.connect(timeout_s=0.1)
        arm.arm(timeout_s=0.5)
        self.assertTrue(arm.armed)
        self.assertEqual(robot.status.ctrl_mode, 1)
        arm.close(hold_if_armed=False)

    def test_arm_refuses_when_status_error_flags_are_set(self):
        robot = FakeRobot()
        robot.status.err_status.joint_1_angle_limit = True
        arm = NeroArmInterface(
            arm_name="arm_a",
            channel="vcan0",
            execute=True,
            robot=robot,
        )
        arm.connect(timeout_s=0.1)
        with self.assertRaisesRegex(NeroSafetyError, "error flags before enable"):
            arm.arm(timeout_s=0.2)
        self.assertFalse(robot.enabled)
        self.assertIsNone(robot.speed_percent)
        arm.close(hold_if_armed=False)

    def test_ctrl_mode_error_names_both_modes_and_the_owning_channel(self):
        # Post-arming this check still guards command(): once we hold CAN
        # control, losing it mid-session must be reported with the mode names
        # and who took it, not a bare integer.
        robot = FakeRobot()
        robot.status.ctrl_mode = 3
        arm = NeroArmInterface(arm_name="arm_b", channel="vcan1", robot=robot)
        arm.connect(timeout_s=0.1)
        with self.assertRaises(NeroSafetyError) as ctx:
            arm._require_motion_safe_status(robot.get_arm_status())
        message = str(ctx.exception)
        self.assertIn("3/ETHERNET_CONTROL_MODE", message)
        self.assertIn("1/CAN_CTRL", message)
        self.assertIn("owned over Ethernet", message)
        arm.close(hold_if_armed=False)

    def test_teaching_mode_still_asks_the_operator_to_leave_it(self):
        # Teaching mode is pendant-driven; enable() must not silently yank the
        # arm out from under someone hand-guiding it.
        robot = FakeRobot()
        robot.status.ctrl_mode = 2
        arm = NeroArmInterface(arm_name="arm_a", channel="vcan0", robot=robot)
        arm.connect(timeout_s=0.1)
        with self.assertRaises(NeroSafetyError) as ctx:
            arm._require_motion_safe_status(robot.get_arm_status())
        self.assertIn("leave teaching mode", str(ctx.exception))
        arm.close(hold_if_armed=False)

    def test_partial_enable_failure_names_the_stuck_joints(self):
        class PartialEnableRobot(FakeRobot):
            def get_joints_enable_status_list(self):
                return [True, True, False, True, True, True, False]

        robot = PartialEnableRobot()
        arm = NeroArmInterface(
            arm_name="arm_a",
            channel="vcan0",
            execute=True,
            robot=robot,
        )
        arm.connect(timeout_s=0.1)
        with self.assertRaises(NeroSafetyError) as ctx:
            arm.arm(timeout_s=0.08)
        message = str(ctx.exception)
        self.assertIn("joint3", message)
        self.assertIn("joint7", message)
        self.assertFalse(arm.armed)
        arm.close(hold_if_armed=False)

    def test_move_to_pose_ramps_in_bounded_steps_out_of_the_singularity(self):
        robot = FakeRobot()
        arm = NeroArmInterface(
            arm_name="arm_a",
            channel="vcan0",
            execute=True,
            robot=robot,
        )
        arm.connect(timeout_s=0.1)
        arm.arm()
        robot.moves.clear()

        target = np.zeros(7)
        target[3] = math.radians(90.0)
        reached = arm.move_to_pose(target, timeout_s=30.0)

        np.testing.assert_allclose(reached, target, atol=math.radians(0.5))
        # Every ramp step must respect the same per-command bound as teleop, so
        # the startup move can never be faster than an operator command.
        previous = np.zeros(7)
        for move in robot.moves:
            self.assertLessEqual(
                float(np.max(np.abs(move - previous))),
                arm.max_joint_step_rad + 1e-9,
            )
            previous = move
        self.assertGreater(len(robot.moves), 100)
        arm.close(hold_if_armed=False)

    def test_move_to_pose_rejects_target_outside_guarded_limits(self):
        robot = FakeRobot()
        arm = NeroArmInterface(
            arm_name="arm_a",
            channel="vcan0",
            execute=True,
            robot=robot,
        )
        arm.connect(timeout_s=0.1)
        arm.arm()
        robot.moves.clear()

        target = np.zeros(7)
        target[3] = NERO_JOINT_LIMITS[3, 1]  # exactly on the hard limit
        with self.assertRaisesRegex(NeroSafetyError, "guarded joint interval for joint4"):
            arm.move_to_pose(target)
        # Rejected up front: nothing was sent to the arm.
        self.assertEqual(robot.moves, [])
        arm.close(hold_if_armed=False)

    def test_move_to_pose_requires_an_armed_interface(self):
        robot = FakeRobot()
        arm = NeroArmInterface(arm_name="arm_a", channel="vcan0", robot=robot)
        arm.connect(timeout_s=0.1)
        with self.assertRaisesRegex(NeroSafetyError, "not armed"):
            arm.move_to_pose(np.zeros(7))
        self.assertEqual(robot.moves, [])
        arm.close(hold_if_armed=False)

    def test_move_to_pose_reports_the_remaining_error_on_timeout(self):
        class StuckRobot(FakeRobot):
            def move_j(self, target):
                # Accept the command but never actually move.
                self.moves.append(np.asarray(target, dtype=np.float64))

        robot = StuckRobot()
        arm = NeroArmInterface(
            arm_name="arm_a",
            channel="vcan0",
            execute=True,
            robot=robot,
        )
        arm.connect(timeout_s=0.1)
        arm.arm()
        target = np.zeros(7)
        target[3] = math.radians(90.0)
        with self.assertRaisesRegex(NeroSafetyError, "did not reach the startup pose"):
            arm.move_to_pose(target, timeout_s=0.2)
        arm.close(hold_if_armed=False)

    def test_describe_status_decodes_enum_names(self):
        robot = FakeRobot()
        robot.status.arm_status = 6
        robot.status.ctrl_mode = 1
        arm = NeroArmInterface(arm_name="arm_a", channel="vcan0", robot=robot)
        arm.connect(timeout_s=0.1)
        summary = arm.describe_status()
        self.assertIn("JOINT_BRAKE_NOT_RELEASED", summary)
        self.assertIn("CAN_CTRL", summary)
        self.assertIn("enabled=0/7", summary)
        arm.close(hold_if_armed=False)


class FeedbackStalenessTests(unittest.TestCase):
    """One late CAN frame is a bus hiccup; a dead bus is a fault.

    Faulting on a single over-age sample latched HOLD for a whole run on
    hardware that was reporting 150 Hz and arm_status=NORMAL.
    """

    def _interface(self, **kwargs):
        return NeroArmInterface(
            arm_name="arm_a", channel="vcan0", robot=FakeRobot(), **kwargs
        )

    def test_single_late_frame_is_tolerated(self):
        arm = self._interface(feedback_timeout_s=0.15, feedback_stale_grace_s=0.5)
        stale = Feedback(np.zeros(7))
        stale.timestamp = time.time() - 0.182
        arm._require_fresh_message(stale, "joint-angle")

    def test_continuously_stale_feedback_still_faults(self):
        arm = self._interface(feedback_timeout_s=0.15, feedback_stale_grace_s=0.05)
        stale = Feedback(np.zeros(7))
        stale.timestamp = time.time() - 0.5
        arm._require_fresh_message(stale, "joint-angle")
        time.sleep(0.06)
        with self.assertRaisesRegex(NeroSafetyError, "has been stale"):
            arm._require_fresh_message(stale, "joint-angle")

    def test_recovery_clears_the_stale_timer(self):
        arm = self._interface(feedback_timeout_s=0.15, feedback_stale_grace_s=0.05)
        stale = Feedback(np.zeros(7))
        stale.timestamp = time.time() - 0.5
        arm._require_fresh_message(stale, "joint-angle")
        arm._require_fresh_message(Feedback(np.zeros(7)), "joint-angle")
        time.sleep(0.06)
        # A fresh frame arrived in between, so the gap must not accumulate.
        arm._require_fresh_message(stale, "joint-angle")

    def test_each_label_tracks_staleness_separately(self):
        arm = self._interface(feedback_timeout_s=0.15, feedback_stale_grace_s=0.05)
        stale = Feedback(np.zeros(7))
        stale.timestamp = time.time() - 0.5
        arm._require_fresh_message(stale, "joint-angle")
        time.sleep(0.06)
        # arm-status just went stale; it must not inherit joint-angle's timer.
        arm._require_fresh_message(stale, "arm-status")

    def test_never_received_feedback_fails_immediately(self):
        arm = self._interface()
        never = Feedback(np.zeros(7))
        never.timestamp = 0.0
        with self.assertRaisesRegex(NeroSafetyError, "never received"):
            arm._require_fresh_message(never, "joint-angle")

    def test_missing_feedback_fails_immediately(self):
        arm = self._interface()
        with self.assertRaisesRegex(NeroSafetyError, "has no joint-angle feedback"):
            arm._require_fresh_message(None, "joint-angle")

    def test_future_timestamp_fails_immediately(self):
        arm = self._interface()
        future = Feedback(np.zeros(7))
        future.timestamp = time.time() + 5.0
        with self.assertRaisesRegex(NeroSafetyError, "in the future"):
            arm._require_fresh_message(future, "joint-angle")


if __name__ == "__main__":
    unittest.main()
