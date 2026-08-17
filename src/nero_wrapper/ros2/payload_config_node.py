"""ROS service that safely applies NERO's firmware payload compensation."""

from __future__ import annotations

import select
import socket
import struct
import time

import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from std_srvs.srv import Trigger

from ..payload_protocol import (
    CAN_EFF_FLAG,
    CAN_RTR_FLAG,
    CAN_SFF_MASK,
    PAYLOAD_CONFIG_CAN_ID,
    SET_INSTRUCTION_ACK_CAN_ID,
    is_payload_setting_ack,
    pack_standard_can_frame,
    payload_config_data,
    unpack_standard_can_frame,
)

SOL_CAN_RAW = 101
CAN_RAW_FILTER = 1


class NeroPayloadConfig(Node):
    """Transmit one coarse NERO payload level under an explicit ACK policy."""

    def __init__(self) -> None:
        super().__init__("nero_payload_config")
        self.declare_parameter("can_port", "can0")
        self.declare_parameter("payload_level", "half")
        self.declare_parameter("payload_mass_kg", 1.010)
        # The supplied protocol defines a 0x477 payload command, but NERO 1.121
        # does not expose Piper's 0x476 response/readback path. Keep strict ACK
        # support available for a future firmware that implements it.
        self.declare_parameter("require_ack", False)
        self.declare_parameter("ack_timeout_s", 0.5)
        self.declare_parameter("attempts", 3)

        self.can_port = str(self.get_parameter("can_port").value)
        self.payload_level = str(self.get_parameter("payload_level").value).lower()
        # Validate the configured level at startup without touching CAN.
        payload_config_data(self.payload_level)
        self.payload_mass_kg = float(self.get_parameter("payload_mass_kg").value)
        self.require_ack = bool(self.get_parameter("require_ack").value)
        self.ack_timeout_s = float(self.get_parameter("ack_timeout_s").value)
        self.attempts = int(self.get_parameter("attempts").value)
        if self.payload_mass_kg < 0.0:
            raise ValueError("payload_mass_kg must be non-negative")
        if self.ack_timeout_s <= 0.0:
            raise ValueError("ack_timeout_s must be positive")
        if self.attempts <= 0:
            raise ValueError("attempts must be positive")

        self.create_service(Trigger, "configure_payload", self._configure)
        self.get_logger().info(
            f"Ready to configure NERO payload: {self.payload_mass_kg:.3f}kg -> "
            f"{self.payload_level!r} on {self.can_port}; no CAN write until "
            "the Execute arming interlock calls this service; verification="
            f"{'0x476 ACK required' if self.require_ack else 'write-only UNVERIFIED'}"
        )

    def _open_socket(self) -> socket.socket:
        can_socket = socket.socket(socket.PF_CAN, socket.SOCK_RAW, socket.CAN_RAW)
        # Only receive the standard 0x476 setting-response frame.
        can_filter = struct.pack(
            "=II",
            SET_INSTRUCTION_ACK_CAN_ID,
            CAN_SFF_MASK | CAN_EFF_FLAG | CAN_RTR_FLAG,
        )
        can_socket.setsockopt(SOL_CAN_RAW, CAN_RAW_FILTER, can_filter)
        can_socket.bind((self.can_port,))
        can_socket.setblocking(False)
        return can_socket

    @staticmethod
    def _drain(can_socket: socket.socket) -> None:
        """Discard any response that predates this service request."""
        while True:
            try:
                can_socket.recv(16)
            except BlockingIOError:
                return

    def _wait_for_ack(self, can_socket: socket.socket, deadline: float) -> bool:
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0.0:
                return False
            readable, _, _ = select.select([can_socket], [], [], remaining)
            if not readable:
                return False
            try:
                can_id, data = unpack_standard_can_frame(can_socket.recv(16))
            except (BlockingIOError, ValueError):
                continue
            if is_payload_setting_ack(can_id, data):
                return True

    def _configure(
        self, _request: Trigger.Request, response: Trigger.Response
    ) -> Trigger.Response:
        command = pack_standard_can_frame(
            PAYLOAD_CONFIG_CAN_ID, payload_config_data(self.payload_level)
        )
        try:
            with self._open_socket() as can_socket:
                self._drain(can_socket)
                for attempt in range(1, self.attempts + 1):
                    can_socket.send(command)
                    if not self.require_ack:
                        response.success = True
                        response.message = (
                            f"{self.can_port} transmitted payload level "
                            f"{self.payload_level} for {self.payload_mass_kg:.3f}kg; "
                            "UNVERIFIED because NERO 1.121 provides no payload "
                            "ACK/readback"
                        )
                        self.get_logger().warn(response.message)
                        return response
                    if self._wait_for_ack(
                        can_socket, time.monotonic() + self.ack_timeout_s
                    ):
                        response.success = True
                        response.message = (
                            f"{self.can_port} acknowledged payload level "
                            f"{self.payload_level} for {self.payload_mass_kg:.3f}kg"
                        )
                        self.get_logger().warn(response.message)
                        return response
                    self.get_logger().warn(
                        f"No 0x476/0x77 payload ACK from {self.can_port} "
                        f"(attempt {attempt}/{self.attempts})"
                    )
        except OSError as exc:
            response.success = False
            response.message = f"failed to configure {self.can_port}: {exc}"
            self.get_logger().error(response.message)
            return response

        response.success = False
        response.message = (
            f"{self.can_port} did not acknowledge NERO payload level "
            f"{self.payload_level} after {self.attempts} attempts"
        )
        self.get_logger().error(response.message)
        return response


def main(args: list[str] | None = None) -> None:
    rclpy.init(args=args)
    node: NeroPayloadConfig | None = None
    try:
        node = NeroPayloadConfig()
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        if node is not None:
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
