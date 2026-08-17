import math
from importlib import resources

import numpy as np
import pytest
import yaml

from nero_wrapper.curobo_ik import (
    CuroboDualNeroIk,
    IkCollisionBlockedError,
    IkNoProgressError,
    IkSafetyError,
    balanced_elbow_seed_configs,
    balanced_elbow_seed_patterns,
    bounded_joint_candidate,
    bounded_joint_candidate_by_groups,
    candidate_ranking_score,
    cross_arm_pair_clearance_m,
    limit_elbow_step,
    load_tool_collision_spheres,
    normalized_joint_motion_rms,
    self_collision_pair_escape_allowed,
    self_collision_pair_tolerance_m,
    shallow_collision_escape_allowed,
)
from nero_wrapper.dual_model import (
    HARDWARE_TO_MODEL_JOINT_OFFSETS,
    HARDWARE_TO_MODEL_JOINT_SIGNS,
)


def test_bounded_candidate_freezes_inactive_arm_and_scales_coordinately() -> None:
    current = np.zeros(14)
    requested = np.arange(1.0, 15.0)
    limit = math.radians(0.5)
    bounded, scale = bounded_joint_candidate(current, requested, range(7), limit)
    assert np.max(np.abs(bounded[:7])) == pytest.approx(limit)
    np.testing.assert_allclose(bounded[:7], requested[:7] * scale)
    np.testing.assert_allclose(bounded[7:], 0.0)


def test_bounded_candidate_scales_each_arm_independently() -> None:
    current = np.zeros(14)
    requested = np.zeros(14)
    requested[:7] = 10.0
    requested[7:] = 0.25

    bounded, scales = bounded_joint_candidate_by_groups(
        current,
        requested,
        (range(7), range(7, 14)),
        1.0,
    )

    np.testing.assert_allclose(bounded[:7], 1.0)
    np.testing.assert_allclose(bounded[7:], 0.25)
    assert scales == pytest.approx((0.1, 1.0))


def test_bounded_candidate_groups_reject_overlap() -> None:
    with pytest.raises(ValueError, match="must not overlap"):
        bounded_joint_candidate_by_groups(
            np.zeros(4),
            np.ones(4),
            ((0, 1), (1, 2)),
            1.0,
        )


def test_normalized_joint_motion_scores_only_active_joint_travel() -> None:
    current = np.zeros(14)
    candidate = np.zeros(14)
    candidate[0] = math.radians(1.0)
    candidate[1] = math.radians(0.5)
    candidate[7:] = math.radians(10.0)

    score = normalized_joint_motion_rms(
        current,
        candidate,
        range(7),
        math.radians(1.0),
    )

    assert score == pytest.approx(math.sqrt((1.0 + 0.25) / 7.0))


def test_candidate_score_prefers_smoother_near_equivalent_pose() -> None:
    smoother = candidate_ranking_score(
        1.10,
        0.0,
        0.10,
        elbow_posture_weight=0.10,
        joint_motion_weight=0.20,
        solver_success=True,
    )
    larger_step = candidate_ranking_score(
        1.00,
        0.0,
        1.00,
        elbow_posture_weight=0.10,
        joint_motion_weight=0.20,
        solver_success=True,
    )

    assert smoother < larger_step


def test_candidate_scoring_rejects_invalid_motion_weight() -> None:
    ik = object.__new__(CuroboDualNeroIk)

    with pytest.raises(ValueError, match="joint motion weight"):
        ik.configure_candidate_scoring(joint_motion_weight=1.01)


def test_candidate_score_requires_material_improvement_before_seed_switch() -> None:
    retained = candidate_ranking_score(
        1.00,
        0.0,
        0.0,
        elbow_posture_weight=0.10,
        joint_motion_weight=0.20,
        solver_success=True,
        seed_switch_penalty=0.20,
        switching_seed=False,
    )
    small_improvement_from_other_seed = candidate_ranking_score(
        0.85,
        0.0,
        0.0,
        elbow_posture_weight=0.10,
        joint_motion_weight=0.20,
        solver_success=True,
        seed_switch_penalty=0.20,
        switching_seed=True,
    )
    material_improvement_from_other_seed = candidate_ranking_score(
        0.75,
        0.0,
        0.0,
        elbow_posture_weight=0.10,
        joint_motion_weight=0.20,
        solver_success=True,
        seed_switch_penalty=0.20,
        switching_seed=True,
    )

    assert retained < small_improvement_from_other_seed
    assert material_improvement_from_other_seed < retained


def test_seed_hysteresis_rejects_invalid_switch_penalty() -> None:
    ik = object.__new__(CuroboDualNeroIk)

    with pytest.raises(ValueError, match="seed switch penalty"):
        ik.configure_seed_hysteresis(switch_penalty=2.01)


def test_seed_continuity_reset_is_scoped_per_arm() -> None:
    ik = object.__new__(CuroboDualNeroIk)
    ik._last_selected_seed_direction = {"arm_a": 1.0, "arm_b": -1.0}
    ik._last_selected_seed_rank = {
        ("arm_a",): 1,
        ("arm_b",): 2,
        ("arm_a", "arm_b"): 3,
    }

    ik.reset_seed_continuity({"arm_a"})

    assert ik._last_selected_seed_direction == {"arm_b": -1.0}
    assert ik._last_selected_seed_rank == {("arm_b",): 2}


def test_fast_path_keeps_safe_candidate_when_solver_flag_is_false() -> None:
    ik = object.__new__(CuroboDualNeroIk)
    ik.solve_attempt_sequence = 0
    ik.last_solve_outcome = "never"
    ik.last_solve_diagnostics = {}
    ik.num_seeds = 5
    calls = []
    fast_result = object()

    def solve_attempt(*_args, use_fast_path, **_kwargs):
        calls.append(use_fast_path)
        ik.last_solve_outcome = "success"
        ik.last_solve_diagnostics = {
            "selected_solver_success": False,
            "solve_time_ms": 1.0,
        }
        return fast_result

    ik._solve_attempt = solve_attempt

    result = ik.solve({}, {"arm_a"})

    assert result is fast_result
    assert calls == [True]
    assert ik.last_solve_diagnostics["fast_path_fallback"] is False


def test_fast_path_falls_back_when_one_seed_makes_no_progress() -> None:
    ik = object.__new__(CuroboDualNeroIk)
    ik.solve_attempt_sequence = 0
    ik.last_solve_outcome = "never"
    ik.last_solve_diagnostics = {}
    ik.num_seeds = 5
    calls = []
    full_result = object()

    def solve_attempt(*_args, use_fast_path, **_kwargs):
        calls.append(use_fast_path)
        if use_fast_path:
            ik.last_solve_outcome = "no_progress"
            raise IkNoProgressError("one seed made no progress")
        ik.last_solve_outcome = "success"
        ik.last_solve_diagnostics = {"solve_time_ms": 4.0}
        return full_result

    ik._solve_attempt = solve_attempt

    result = ik.solve({}, {"arm_a"})

    assert result is full_result
    assert calls == [True, False]
    assert ik.last_solve_diagnostics["fast_path_fallback"] is True
    assert (
        ik.last_solve_diagnostics["fast_path_fallback_reason"]
        == "IkNoProgressError"
    )


def test_per_arm_step_diagnostic_uses_model_arm_slices() -> None:
    ik = object.__new__(CuroboDualNeroIk)
    ik.arm_slices = {"arm_a": slice(0, 7), "arm_b": slice(7, 14)}
    current = np.zeros(14)
    candidate = np.zeros(14)
    candidate[2] = math.radians(1.25)
    candidate[11] = math.radians(-2.5)

    result = ik._joint_step_max_by_arm_deg(
        current,
        candidate,
        ("arm_a", "arm_b"),
    )

    assert result == {"arm_a": 1.25, "arm_b": 2.5}


def test_elbow_seeds_are_deterministic_bounded_and_directionally_balanced() -> None:
    current = np.zeros(14)
    lower = np.full(14, -1.0)
    upper = np.full(14, 0.25)

    seeds = balanced_elbow_seed_configs(
        current,
        (1, 8),
        lower,
        upper,
        math.radians(10.0),
        num_seeds=5,
    )

    assert seeds.shape == (5, 14)
    np.testing.assert_allclose(seeds[0], current)
    assert np.all(seeds <= upper)
    assert np.all(seeds >= lower)
    assert seeds[1, 1] > 0.0 and seeds[1, 8] > 0.0
    assert seeds[2, 1] < 0.0 and seeds[2, 8] < 0.0
    assert seeds[3, 1] > 0.0 and seeds[3, 8] < 0.0
    assert seeds[4, 1] < 0.0 and seeds[4, 8] > 0.0
    np.testing.assert_allclose(seeds[:, 2:7], 0.0)


def test_bimanual_seed_patterns_label_each_arm_independently() -> None:
    assert balanced_elbow_seed_patterns(2) == (
        (0.0, 0.0),
        (1.0, 1.0),
        (-1.0, -1.0),
        (1.0, -1.0),
        (-1.0, 1.0),
    )


def test_elbow_limit_is_symmetric_and_leaves_other_joints_unchanged() -> None:
    current = np.zeros(14)
    candidate = np.zeros(14)
    candidate[1] = math.radians(-3.0)
    candidate[8] = math.radians(3.0)
    candidate[3] = math.radians(2.0)

    bounded = limit_elbow_step(
        current,
        candidate,
        (1, 8),
        math.radians(0.5),
    )

    assert bounded[1] == pytest.approx(math.radians(-0.5))
    assert bounded[8] == pytest.approx(math.radians(0.5))
    assert bounded[3] == pytest.approx(math.radians(2.0))


def test_hardware_model_joint_transform_reflects_j2_and_round_trips() -> None:
    ik = object.__new__(CuroboDualNeroIk)
    ik.offsets = {
        arm: np.asarray(values, dtype=np.float64)
        for arm, values in HARDWARE_TO_MODEL_JOINT_OFFSETS.items()
    }
    ik.signs = {
        arm: np.asarray(values, dtype=np.float64)
        for arm, values in HARDWARE_TO_MODEL_JOINT_SIGNS.items()
    }
    ik.arm_slices = {"arm_a": slice(0, 7), "arm_b": slice(7, 14)}
    hardware = {
        "arm_a": np.radians([1.0, 15.0, 3.0, 90.0, 5.0, 6.0, 7.0]),
        "arm_b": np.radians([-1.0, 12.0, -3.0, 90.0, -5.0, -6.0, -7.0]),
    }

    model = ik._pack_model(hardware)

    assert model[1] == pytest.approx(-math.pi / 2.0 - math.radians(15.0))
    assert model[8] == pytest.approx(-math.pi / 2.0 - math.radians(12.0))
    for arm in ("arm_a", "arm_b"):
        np.testing.assert_allclose(
            ik._model_to_hardware(arm, model[ik.arm_slices[arm]]),
            hardware[arm],
            atol=1e-12,
        )


def test_command_reference_sync_preserves_measured_feedback() -> None:
    ik = object.__new__(CuroboDualNeroIk)
    ik.offsets = {
        arm: np.zeros(7, dtype=np.float64)
        for arm in ("arm_a", "arm_b")
    }
    ik.signs = {
        arm: np.ones(7, dtype=np.float64)
        for arm in ("arm_a", "arm_b")
    }
    ik._kinematic_transforms = lambda _q: {
        arm: np.eye(4) for arm in ("arm_a", "arm_b")
    }
    ik.measured_hardware = None
    measured = {
        "arm_a": np.zeros(7),
        "arm_b": np.full(7, 0.1),
    }
    command = {
        "arm_a": np.full(7, 0.05),
        "arm_b": np.full(7, 0.15),
    }

    ik.sync(measured)
    ik.sync_command_reference(command)

    for arm in measured:
        np.testing.assert_allclose(ik.measured_hardware[arm], measured[arm])
        np.testing.assert_allclose(ik.command_reference_hardware[arm], command[arm])
    np.testing.assert_allclose(
        ik.model_q,
        np.concatenate((command["arm_a"], command["arm_b"])),
    )


def test_cached_command_reference_skips_duplicate_fk() -> None:
    ik = object.__new__(CuroboDualNeroIk)
    ik.offsets = {arm: np.zeros(7) for arm in ("arm_a", "arm_b")}
    ik.signs = {arm: np.ones(7) for arm in ("arm_a", "arm_b")}
    calls = []
    ik._kinematic_transforms = lambda q: calls.append(q.copy()) or {
        arm: np.eye(4) for arm in ("arm_a", "arm_b")
    }
    measured = {arm: np.zeros(7) for arm in ("arm_a", "arm_b")}

    ik.sync(measured)
    ik.sync_command_reference(measured)
    ik.update_measured_feedback(
        {arm: np.full(7, 0.01) for arm in ("arm_a", "arm_b")}
    )
    ik.sync_command_reference(measured)

    assert len(calls) == 1
    assert ik.command_reference_fk_reuse_count == 2
    for arm in measured:
        np.testing.assert_allclose(ik.measured_hardware[arm], 0.01)


def test_physical_lead_bound_is_independent_of_command_reference_step() -> None:
    feedback = np.zeros(14)
    command_reference = np.full(14, math.radians(3.0))
    requested = np.full(14, math.radians(6.0))

    command_step, _ = bounded_joint_candidate(
        command_reference,
        requested,
        range(14),
        math.radians(3.0),
    )
    physically_bounded, _ = bounded_joint_candidate(
        feedback,
        command_step,
        range(14),
        math.radians(4.0),
    )

    assert np.max(np.abs(command_step - command_reference)) == pytest.approx(
        math.radians(3.0)
    )
    assert np.max(np.abs(physically_bounded - feedback)) == pytest.approx(
        math.radians(4.0)
    )


def test_balanced_model_seeds_map_to_both_hardware_j2_directions() -> None:
    ik = object.__new__(CuroboDualNeroIk)
    ik.offsets = {
        arm: np.asarray(values, dtype=np.float64)
        for arm, values in HARDWARE_TO_MODEL_JOINT_OFFSETS.items()
    }
    ik.signs = {
        arm: np.asarray(values, dtype=np.float64)
        for arm, values in HARDWARE_TO_MODEL_JOINT_SIGNS.items()
    }
    current = np.concatenate([ik.offsets["arm_a"], ik.offsets["arm_b"]])
    seeds = balanced_elbow_seed_configs(
        current,
        (1, 8),
        np.full(14, -math.pi),
        np.full(14, math.pi),
        math.radians(10.0),
        num_seeds=5,
    )

    arm_a_hardware = ik._model_to_hardware("arm_a", seeds[1, :7])
    arm_b_hardware = ik._model_to_hardware("arm_b", seeds[1, 7:])
    arm_a_inward = ik._model_to_hardware("arm_a", seeds[2, :7])
    arm_b_inward = ik._model_to_hardware("arm_b", seeds[2, 7:])
    assert math.degrees(arm_a_hardware[1]) == pytest.approx(-10.0)
    assert math.degrees(arm_b_hardware[1]) == pytest.approx(-10.0)
    assert math.degrees(arm_a_inward[1]) == pytest.approx(10.0)
    assert math.degrees(arm_b_inward[1]) == pytest.approx(10.0)


def test_collision_resource_is_packaged_and_symmetric() -> None:
    resource = resources.files("nero_wrapper").joinpath("data/nero_curobo_collision.yaml")
    with resource.open("r", encoding="utf-8") as stream:
        model = yaml.safe_load(stream)["collision_model"]
    for index in range(8):
        suffix = "base_link" if index == 0 else f"link{index}"
        assert (
            model["collision_spheres"][f"arm_a_{suffix}"]
            == model["collision_spheres"][f"arm_b_{suffix}"]
        )


def test_no_progress_is_not_a_hardware_safety_fault() -> None:
    assert issubclass(IkNoProgressError, RuntimeError)
    assert not issubclass(IkNoProgressError, IkSafetyError)


def test_progress_policy_can_disable_strict_frame_rejection() -> None:
    ik = object.__new__(CuroboDualNeroIk)
    ik.require_cartesian_progress = True

    ik.configure_progress_policy(require_cartesian_progress=False)

    assert ik.require_cartesian_progress is False


def test_progress_policy_rejects_non_boolean_values() -> None:
    ik = object.__new__(CuroboDualNeroIk)

    with pytest.raises(ValueError, match="true or false"):
        ik.configure_progress_policy(require_cartesian_progress=1)


def test_collision_block_is_safe_but_uses_non_latching_retry_path() -> None:
    assert issubclass(IkCollisionBlockedError, IkNoProgressError)
    assert issubclass(IkCollisionBlockedError, IkSafetyError)


def test_driver_fk_batches_raw_check_with_synchronized_model_state() -> None:
    ik = object.__new__(CuroboDualNeroIk)
    ik.base_world = {arm: np.eye(4) for arm in ("arm_a", "arm_b")}
    ik.offsets = {
        arm: np.full(7, 100.0 if arm == "arm_a" else 200.0)
        for arm in ("arm_a", "arm_b")
    }
    ik.signs = {
        "arm_a": np.ones(7),
        "arm_b": -np.ones(7),
    }
    ik.arm_slices = {"arm_a": slice(0, 7), "arm_b": slice(7, 14)}
    seen = {}

    def kinematics_batch(q):
        seen["q"] = q.copy()
        return [
            {arm: np.eye(4) for arm in ("arm_a", "arm_b")}
            for _ in range(q.shape[0])
        ]

    ik._kinematic_transforms_batch = kinematics_batch
    historical = {
        "arm_a": np.arange(7, dtype=np.float64),
        "arm_b": np.arange(7, 14, dtype=np.float64),
    }
    latest = {
        "arm_a": np.arange(20, 27, dtype=np.float64),
        "arm_b": np.arange(30, 37, dtype=np.float64),
    }
    errors = ik.validate_driver_fk(
        historical,
        {arm: np.eye(4) for arm in ("arm_a", "arm_b")},
        synchronize_hardware=latest,
    )

    assert seen["q"].shape == (2, 14)
    np.testing.assert_allclose(seen["q"][0], np.arange(14, dtype=np.float64))
    expected_latest_model = np.concatenate(
        (
            100.0 + latest["arm_a"],
            200.0 - latest["arm_b"],
        )
    )
    np.testing.assert_allclose(seen["q"][1], expected_latest_model)
    np.testing.assert_allclose(ik.model_q, expected_latest_model)
    for arm in ("arm_a", "arm_b"):
        np.testing.assert_allclose(ik.measured_hardware[arm], latest[arm])
        np.testing.assert_allclose(ik.tcp_world[arm], np.eye(4))
        assert errors[arm] == pytest.approx((0.0, 0.0))


def test_mesh_fit_tolerance_is_limited_to_verified_pairs() -> None:
    tolerance = 0.0005
    assert self_collision_pair_tolerance_m(
        "arm_a_base_link", "arm_a_link2", tolerance
    ) == pytest.approx(tolerance)
    assert self_collision_pair_tolerance_m(
        "arm_a_base_link", "arm_b_link2", tolerance
    ) == 0.0


def test_cross_arm_clearance_applies_only_between_different_arms() -> None:
    margin = 0.01
    assert cross_arm_pair_clearance_m(
        "arm_a_link3", "arm_b_tcp_link", margin
    ) == pytest.approx(margin)
    assert cross_arm_pair_clearance_m(
        "arm_a_link3", "arm_a_tcp_link", margin
    ) == 0.0


def test_shallow_escape_is_limited_to_same_arm_link5_tool_pairs() -> None:
    assert self_collision_pair_escape_allowed("arm_a_link5", "arm_a_tcp_link")
    assert self_collision_pair_escape_allowed("arm_b_tcp_link", "arm_b_link5")
    assert not self_collision_pair_escape_allowed("arm_a_link5", "arm_b_tcp_link")


def test_shallow_escape_requires_no_deepening_new_collision_and_progress() -> None:
    approved = np.asarray([True, False])
    assert shallow_collision_escape_allowed(
        np.asarray([[-0.00015, 0.004], [-0.00010, 0.003], [0.00002, 0.002]]),
        approved,
        0.0005,
    )
    assert not shallow_collision_escape_allowed(
        np.asarray([[-0.00015, 0.004], [-0.00020, 0.003], [0.00002, 0.002]]),
        approved,
        0.0005,
    )
    assert not shallow_collision_escape_allowed(
        np.asarray([[-0.00015, 0.004], [-0.00010, -0.00001], [0.00002, 0.002]]),
        approved,
        0.0005,
    )


def test_shallow_escape_allows_stationary_inactive_overlap() -> None:
    approved = np.asarray([True, False])
    assert shallow_collision_escape_allowed(
        np.asarray([[-0.00010, 0.004], [-0.00010, 0.003], [-0.00010, 0.002]]),
        approved,
        0.0005,
    )
    assert not shallow_collision_escape_allowed(
        np.asarray([[-0.00010, 0.004], [-0.00005, 0.003], [-0.00010, 0.002]]),
        approved,
        0.0005,
    )


def test_recovery_can_require_complete_clearance() -> None:
    approved = np.asarray([True, False])
    assert shallow_collision_escape_allowed(
        np.asarray([[-0.002562, 0.004], [-0.0012, 0.003], [0.0001, 0.002]]),
        approved,
        0.003,
        require_final_clearance=True,
    )
    assert not shallow_collision_escape_allowed(
        np.asarray([[-0.002562, 0.004], [-0.0012, 0.003], [-0.0001, 0.002]]),
        approved,
        0.003,
        require_final_clearance=True,
    )


def test_field_park_recovery_accepts_observed_non_deepening_overlap() -> None:
    approved = np.asarray([True, False])
    captured_path = np.asarray(
        [
            [-0.009933, 0.004],
            [-0.006000, 0.003],
            [-0.001000, 0.002],
            [0.006798, 0.001],
        ]
    )

    assert shallow_collision_escape_allowed(
        captured_path,
        approved,
        0.0105,
        require_final_clearance=True,
    )
    assert not shallow_collision_escape_allowed(
        captured_path,
        approved,
        0.0099,
        require_final_clearance=True,
    )


def test_park_recovery_envelope_cannot_exceed_105mm() -> None:
    uninitialized_ik = object.__new__(CuroboDualNeroIk)
    with pytest.raises(ValueError, match="between 0 and 10.50mm"):
        uninitialized_ik.validate_independent_joint_path(
            {},
            {},
            recovery_escape_max_initial_overlap_m=0.010501,
        )


def test_field_tool_fit_allows_229mm_only_when_overlap_does_not_deepen() -> None:
    approved = np.asarray([True, False])
    field_limit_m = 0.0025

    assert shallow_collision_escape_allowed(
        np.asarray([[-0.00229, 0.004], [-0.00210, 0.003], [-0.00190, 0.002]]),
        approved,
        field_limit_m,
    )
    assert shallow_collision_escape_allowed(
        np.asarray([[-0.00174, 0.004], [-0.00174, 0.003], [-0.00174, 0.002]]),
        approved,
        field_limit_m,
    )
    assert not shallow_collision_escape_allowed(
        np.asarray([[-0.00229, 0.004], [-0.00240, 0.003], [-0.00210, 0.002]]),
        approved,
        field_limit_m,
    )
    assert not shallow_collision_escape_allowed(
        np.asarray([[-0.00251, 0.004], [-0.00230, 0.003], [-0.00210, 0.002]]),
        approved,
        field_limit_m,
    )


def test_tool_collision_spheres_require_tcp_frame_and_positive_geometry(tmp_path) -> None:
    model_path = tmp_path / "tacclaw.yaml"
    model_path.write_text(
        """
collision_model:
  frame: tcp_link
  collision_spheres:
    - center: [0.01, -0.02, -0.03]
      radius: 0.04
""",
        encoding="utf-8",
    )
    assert load_tool_collision_spheres(model_path) == [
        {"center": [0.01, -0.02, -0.03], "radius": 0.04}
    ]
    model_path.write_text(
        """
collision_model:
  frame: link7
  collision_spheres:
    - center: [0.0, 0.0, 0.0]
      radius: -0.01
""",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="tcp_link"):
        load_tool_collision_spheres(model_path)


@pytest.mark.parametrize(
    "clearances",
    [
        np.ones((1, 2)),
        np.asarray([[math.nan], [0.0]]),
    ],
)
def test_escape_rejects_invalid_or_nonfinite_samples(clearances) -> None:
    if clearances.shape[0] < 2:
        with pytest.raises(ValueError):
            shallow_collision_escape_allowed(clearances, np.ones(2, dtype=bool), 0.1)
    else:
        assert not shallow_collision_escape_allowed(
            clearances,
            np.ones(clearances.shape[1], dtype=bool),
            0.1,
        )
