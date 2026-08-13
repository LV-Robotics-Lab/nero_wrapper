import math
from importlib import resources

import numpy as np
import pytest
import yaml

from nero_wrapper.curobo_ik import (
    IkNoProgressError,
    IkSafetyError,
    bounded_joint_candidate,
    load_tool_collision_spheres,
    self_collision_pair_escape_allowed,
    self_collision_pair_tolerance_m,
    shallow_collision_escape_allowed,
)


def test_bounded_candidate_freezes_inactive_arm_and_scales_coordinately() -> None:
    current = np.zeros(14)
    requested = np.arange(1.0, 15.0)
    limit = math.radians(0.5)
    bounded, scale = bounded_joint_candidate(current, requested, range(7), limit)
    assert np.max(np.abs(bounded[:7])) == pytest.approx(limit)
    np.testing.assert_allclose(bounded[:7], requested[:7] * scale)
    np.testing.assert_allclose(bounded[7:], 0.0)


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


def test_mesh_fit_tolerance_is_limited_to_verified_pairs() -> None:
    tolerance = 0.0005
    assert self_collision_pair_tolerance_m(
        "arm_a_base_link", "arm_a_link2", tolerance
    ) == pytest.approx(tolerance)
    assert self_collision_pair_tolerance_m(
        "arm_a_base_link", "arm_b_link2", tolerance
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
