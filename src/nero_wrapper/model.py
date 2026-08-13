"""Hardware-defined NERO joint metadata shared by robot integrations."""

from __future__ import annotations

import math
from collections.abc import Sequence

NERO_JOINT_NAMES = tuple(f"joint{index}" for index in range(1, 8))

# Radian limits from the audited NERO dual-arm integration. Retargeting code
# may add a positive safety margin but must not widen these hardware limits.
NERO_JOINT_LIMITS_RAD = (
    (-2.705261, 2.705261),
    (-1.745330, 1.745330),
    (-2.757621, 2.757621),
    (-1.012291, 2.146755),
    (-2.757621, 2.757621),
    (-0.733039, 0.959932),
    (-1.570797, 1.570797),
)


def validate_joint_positions(
    positions_rad: Sequence[float],
    *,
    margin_rad: float = 0.0,
) -> tuple[float, ...]:
    """Validate a seven-joint vector against inward-margined NERO limits."""

    values = tuple(float(value) for value in positions_rad)
    if len(values) != 7:
        raise ValueError("NERO joint positions must contain exactly seven values")
    if not all(math.isfinite(value) for value in values):
        raise ValueError("NERO joint positions must contain only finite values")
    if not math.isfinite(margin_rad) or margin_rad < 0.0:
        raise ValueError("margin_rad must be finite and non-negative")
    for name, value, (lower, upper) in zip(
        NERO_JOINT_NAMES,
        values,
        NERO_JOINT_LIMITS_RAD,
        strict=True,
    ):
        guarded_lower = lower + margin_rad
        guarded_upper = upper - margin_rad
        if guarded_lower > guarded_upper:
            raise ValueError("margin_rad collapses at least one NERO joint interval")
        if not guarded_lower <= value <= guarded_upper:
            raise ValueError(
                f"{name}={value:.6f}rad is outside guarded interval "
                f"[{guarded_lower:.6f}, {guarded_upper:.6f}]"
            )
    return values
