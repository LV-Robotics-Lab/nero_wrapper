"""Strict device-timestamp freshness tracking for the NERO ROS driver."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum


class SourceObservation(str, Enum):
    FRESH = "fresh"
    DUPLICATE = "duplicate"
    OUT_OF_ORDER = "out_of_order"
    INVALID = "invalid"


@dataclass
class SourceStampTracker:
    """Advance freshness only when a positive device timestamp increases."""

    last_source_stamp_ns: int | None = None
    first_fresh_monotonic_ns: int | None = None
    last_fresh_monotonic_ns: int | None = None
    fresh_count: int = 0
    duplicate_count: int = 0
    out_of_order_count: int = 0
    invalid_count: int = 0

    def observe(
        self,
        source_stamp_ns: int,
        received_monotonic_ns: int,
    ) -> SourceObservation:
        if source_stamp_ns <= 0 or received_monotonic_ns <= 0:
            self.invalid_count += 1
            return SourceObservation.INVALID
        if self.last_source_stamp_ns is not None:
            if source_stamp_ns == self.last_source_stamp_ns:
                self.duplicate_count += 1
                return SourceObservation.DUPLICATE
            if source_stamp_ns < self.last_source_stamp_ns:
                self.out_of_order_count += 1
                return SourceObservation.OUT_OF_ORDER
        self.last_source_stamp_ns = source_stamp_ns
        if self.first_fresh_monotonic_ns is None:
            self.first_fresh_monotonic_ns = received_monotonic_ns
        self.last_fresh_monotonic_ns = received_monotonic_ns
        self.fresh_count += 1
        return SourceObservation.FRESH

    def age_s(self, now_monotonic_ns: int) -> float | None:
        if self.last_fresh_monotonic_ns is None or now_monotonic_ns <= 0:
            return None
        return max(
            0.0,
            float(now_monotonic_ns - self.last_fresh_monotonic_ns)
            / 1_000_000_000.0,
        )

    def is_fresh(self, now_monotonic_ns: int, timeout_s: float) -> bool:
        if not math.isfinite(timeout_s) or timeout_s <= 0.0:
            raise ValueError("timeout_s must be positive and finite")
        age = self.age_s(now_monotonic_ns)
        return age is not None and age <= timeout_s


__all__ = ["SourceObservation", "SourceStampTracker"]
