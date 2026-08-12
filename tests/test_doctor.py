from __future__ import annotations

import subprocess

from nero_wrapper.config import NeroConfig
from nero_wrapper.doctor import inspect_can_interfaces


def test_can_doctor_checks_state_and_bitrate() -> None:
    config = NeroConfig.from_env({})

    def runner(command: list[str]) -> subprocess.CompletedProcess[str]:
        channel = command[-1]
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=f"2: {channel}: <NOARP,UP,LOWER_UP> state UP\n    can bitrate 1000000",
            stderr="",
        )

    results = inspect_can_interfaces(config, runner=runner)

    assert len(results) == 4
    assert all(result.ok for result in results)


def test_can_doctor_reports_missing_interface() -> None:
    config = NeroConfig.from_env({})

    def runner(command: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 1, stdout="", stderr="Device not found")

    results = inspect_can_interfaces(config, runner=runner)

    assert not any(result.ok for result in results)
    assert results[0].detail == "missing can_arm_a"
