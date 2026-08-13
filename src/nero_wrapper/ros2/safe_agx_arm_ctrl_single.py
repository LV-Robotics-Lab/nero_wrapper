from __future__ import annotations

import threading
import time

import rclpy
from agx_arm_ctrl.agx_arm_ctrl_single_node import AgxArmRosNode
from agx_arm_msgs.msg import MoveMITMsg
from rclpy.executors import ExternalShutdownException
from std_srvs.srv import SetBool


class SafeAgxArmRosNode(AgxArmRosNode):
    """Vendor driver with an explicitly stoppable feedback publisher thread."""

    def __init__(self) -> None:
        # AgxArmRosNode.__init__ starts a thread using self._publish_thread, so
        # the event must exist before entering the vendor constructor.
        self._publisher_stop = threading.Event()
        self._enabled_by_this_process = False
        super().__init__()

    def _enable_callback(
        self,
        request: SetBool.Request,
        response: SetBool.Response,
    ) -> SetBool.Response:
        result = super()._enable_callback(request, response)
        if result.success:
            self._enabled_by_this_process = bool(request.data)
        return result

    def _publish_thread(self) -> None:
        period = 1.0 / float(self.pub_rate)
        next_tick = time.monotonic()
        while not self._publisher_stop.is_set() and rclpy.ok():
            try:
                if self.agx_arm.is_ok():
                    if not self.control_ready and self._check_arm_ready():
                        self.control_ready = True
                        if not self._control_ready_logged:
                            gate_state = "open" if self.control_enabled else "closed"
                            motor_state = "enabled" if self.enable_flag else "disabled"
                            self.get_logger().info(
                                "Agx_arm feedback publishing is ready; external "
                                f"control gate is {gate_state}; motors were detected "
                                f"as {motor_state}"
                            )
                            self._control_ready_logged = True
                    self._publish_joint_states()
                    self._publish_pose()
                    self._publish_arm_status()
                    self._publish_effector_status()
                    self._publish_leader_joint_states()
            except Exception:
                # rclpy's SIGINT handler can invalidate publishers while this
                # high-rate thread is between calls.  That is normal shutdown;
                # unexpected runtime failures still propagate.
                if self._publisher_stop.is_set() or not rclpy.ok():
                    break
                raise
            next_tick += period
            delay = max(0.0, next_tick - time.monotonic())
            if self._publisher_stop.wait(delay):
                break
            if delay == 0.0:
                next_tick = time.monotonic()

    def _move_mit_callback(self, msg: MoveMITMsg) -> None:
        """Send one MIT mode frame per handover, then one frame per joint.

        The vendor callback calls ``move_mit`` seven times while automatic mode
        selection remains enabled.  NERO V112 therefore emits seven redundant
        mode frames for every ROS command, which can starve the CAN feedback
        stream.  Keep automatic mode selection for all other vendor callbacks,
        but suppress it inside this already-batched MIT update.
        """
        if not self._check_can_control():
            return
        arrays = [msg.joint_index, msg.p_des, msg.v_des, msg.kp, msg.kd, msg.torque]
        if len(set(len(values) for values in arrays)) > 1:
            self.get_logger().error("MoveMITMsg arrays have inconsistent lengths")
            return
        if not msg.joint_index:
            self.get_logger().warn("Received empty MoveMITMsg")
            return

        automatic_mode = self.agx_arm.get_auto_set_motion_mode_enabled()
        try:
            if not self.is_mit_mode:
                self.agx_arm.set_motion_mode("mit")
            self.agx_arm.set_auto_set_motion_mode_enabled(False)
            for index, joint_index in enumerate(msg.joint_index):
                self.agx_arm.move_mit(
                    joint_index=joint_index,
                    p_des=msg.p_des[index],
                    v_des=msg.v_des[index],
                    kp=msg.kp[index],
                    kd=msg.kd[index],
                    t_ff=msg.torque[index],
                )
        finally:
            self.agx_arm.set_auto_set_motion_mode_enabled(automatic_mode)
        self.is_mit_mode = True

    def stop_publisher(self, timeout_s: float = 2.0) -> None:
        self._publisher_stop.set()
        thread = getattr(self, "publisher_thread", None)
        if thread is None or thread is threading.current_thread():
            return
        thread.join(timeout=timeout_s)
        if thread.is_alive():
            self.get_logger().warn(
                "Feedback publisher did not stop within 2 seconds"
            )

    def disable_for_shutdown(self, timeout_s: float = 8.0) -> None:
        """Fail-safe: disable an arm enabled through this process before exit."""

        if not self._enabled_by_this_process:
            return
        try:
            if self._enable_arm(False, timeout_s):
                self._enabled_by_this_process = False
                self.get_logger().info("Arm disabled during driver shutdown")
            else:
                self.get_logger().error(
                    "Arm was enabled by this process but shutdown disable failed; "
                    "use the physical emergency stop"
                )
        except Exception as exc:
            self.get_logger().error(
                f"Exception while disabling arm during shutdown: {exc}; "
                "use the physical emergency stop"
            )


def main(args: list[str] | None = None) -> None:
    # Retain rclpy's SIGINT handler so a blocking executor wakes immediately.
    # Unlike the vendor entry point, the guarded publisher exits if that handler
    # invalidates the context and shutdown is never called a second time.
    rclpy.init(args=args)
    node: SafeAgxArmRosNode | None = None
    try:
        node = SafeAgxArmRosNode()
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        if node is not None:
            node.stop_publisher()
            node.disable_for_shutdown()
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()

