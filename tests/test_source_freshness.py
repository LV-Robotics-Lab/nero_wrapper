from nero_wrapper.source_freshness import SourceObservation, SourceStampTracker


def test_cached_sdk_sample_cannot_renew_driver_freshness() -> None:
    tracker = SourceStampTracker()
    assert tracker.observe(100, 1_000_000_000) is SourceObservation.FRESH

    for received_ns in (1_005_000_000, 1_010_000_000, 1_050_000_000):
        assert tracker.observe(100, received_ns) is SourceObservation.DUPLICATE

    assert not tracker.is_fresh(1_050_000_001, 0.05)
    assert tracker.last_fresh_monotonic_ns == 1_000_000_000


def test_driver_tracker_rejects_backward_and_unstamped_samples() -> None:
    tracker = SourceStampTracker()
    tracker.observe(200, 1_000)

    assert tracker.observe(199, 2_000) is SourceObservation.OUT_OF_ORDER
    assert tracker.observe(0, 3_000) is SourceObservation.INVALID
    assert tracker.observe(201, 4_000) is SourceObservation.FRESH
    assert tracker.fresh_count == 2
    assert tracker.out_of_order_count == 1
    assert tracker.invalid_count == 1
