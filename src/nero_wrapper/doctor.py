"""Read-only host and SocketCAN diagnostics."""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from .config import NeroConfig


@dataclass(frozen=True, slots=True)
class CheckResult:
    name: str
    ok: bool
    detail: str


Runner = Callable[[Sequence[str]], subprocess.CompletedProcess[str]]


def _run(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, check=False, capture_output=True, text=True)


def inspect_can_interfaces(
    config: NeroConfig,
    *,
    runner: Runner = _run,
) -> list[CheckResult]:
    results: list[CheckResult] = []
    if shutil.which("ip") is None and runner is _run:
        return [CheckResult("ip", False, "iproute2 is not installed")]

    for endpoint in (*config.arms, *config.hands):
        completed = runner(["ip", "-details", "link", "show", endpoint.channel])
        output = f"{completed.stdout}\n{completed.stderr}".strip()
        if completed.returncode != 0:
            results.append(CheckResult(endpoint.name, False, f"missing {endpoint.channel}"))
            continue
        is_up = "state UP" in output or "<UP," in output or ",UP>" in output
        has_bitrate = f"bitrate {config.bitrate}" in output
        detail = f"{endpoint.channel}: state={'UP' if is_up else 'DOWN'}, bitrate="
        detail += str(config.bitrate) if has_bitrate else "unexpected/unknown"
        results.append(CheckResult(endpoint.name, is_up and has_bitrate, detail))
    return results


def inspect_commands(
    commands: Sequence[str] = ("git", "python3", "docker", "candump"),
) -> list[CheckResult]:
    return [
        CheckResult(
            command, shutil.which(command) is not None, shutil.which(command) or "not found"
        )
        for command in commands
    ]
