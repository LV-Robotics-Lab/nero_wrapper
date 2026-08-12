"""Reusable fail-closed gates for commands that may move real hardware."""

from __future__ import annotations

import math
from dataclasses import dataclass


class SafetyGateError(RuntimeError):
    """Raised when an execution request is missing a required confirmation."""


@dataclass(frozen=True, slots=True)
class MotionGate:
    """Explicit operator confirmations required before any motion API call.

    The current package exposes read-only SDK access. Motion scripts can use
    this gate while they are migrated into the package without weakening their
    existing dry-run-first behavior.
    """

    execute: bool = False
    clearance_confirmed: bool = False
    estop_ready: bool = False
    control_source_exclusive: bool = False
    visualization_confirmed: bool = False

    @property
    def is_dry_run(self) -> bool:
        return not self.execute

    def require_motion(self, *, require_visualization: bool = True) -> None:
        if not self.execute:
            raise SafetyGateError("motion is disabled; run and review dry-run first")
        missing: list[str] = []
        if not self.clearance_confirmed:
            missing.append("workspace clearance")
        if not self.estop_ready:
            missing.append("emergency-stop readiness")
        if not self.control_source_exclusive:
            missing.append("exclusive control source")
        if require_visualization and not self.visualization_confirmed:
            missing.append("RViz/feedback visibility")
        if missing:
            raise SafetyGateError("execution gate incomplete: " + ", ".join(missing))


def validate_joint_delta(delta_deg: float, max_delta_deg: float) -> float:
    """Validate and return a bounded single-joint delta in degrees."""

    if not math.isfinite(max_delta_deg) or max_delta_deg <= 0:
        raise ValueError("max_delta_deg must be finite and positive")
    if not math.isfinite(delta_deg):
        raise SafetyGateError("joint delta must be finite")
    if abs(delta_deg) > max_delta_deg:
        raise SafetyGateError(
            f"refusing {delta_deg:g} deg joint delta; limit is {max_delta_deg:g} deg"
        )
    return float(delta_deg)
