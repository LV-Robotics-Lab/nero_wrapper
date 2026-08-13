import math

import numpy as np
import pytest

from nero_wrapper.dual_model import ARM_NAMES, HARDWARE_TO_MODEL_JOINT_OFFSETS
from nero_wrapper.payload_gravity import PayloadGravityCompensator


class FakeGravity:
    def __init__(self) -> None:
        self.linear = np.zeros(3)


class FakeModel:
    nq = 7
    nv = 7

    def __init__(self) -> None:
        self.gravity = FakeGravity()
        self.has_payload = False

    def __deepcopy__(self, memo):
        result = FakeModel()
        result.gravity.linear = self.gravity.linear.copy()
        result.has_payload = self.has_payload
        return result

    def getJointId(self, name):
        return 7 if name == "joint7" else 0

    def appendBodyToJoint(self, joint_id, inertia, placement):
        assert joint_id == 7
        self.has_payload = True
        self.payload_mass = inertia.mass
        self.payload_translation = placement.translation.copy()

    def createData(self):
        return object()


class FakeInertia:
    def __init__(self, mass, lever, inertia):
        self.mass = mass


class FakeSE3:
    def __init__(self, rotation, translation):
        self.translation = translation


class FakePin:
    Inertia = FakeInertia
    SE3 = FakeSE3

    @staticmethod
    def buildModelFromUrdf(path):
        return FakeModel()

    @staticmethod
    def computeGeneralizedGravity(model, data, q):
        if not model.has_payload:
            return np.asarray(q, dtype=float) * 0.1
        # Deterministic payload-only delta large enough to exercise clipping.
        return np.asarray(q, dtype=float) * 0.1 + model.payload_mass * np.arange(1, 8)


def rotations():
    return {arm: np.eye(3) for arm in ARM_NAMES}


def compensator(**overrides):
    values = {
        "mass_kg": 1.0,
        "com_xyz_m": [0.0, 0.0, 0.075],
        "world_from_base_rotations": rotations(),
        "joint_offsets": HARDWARE_TO_MODEL_JOINT_OFFSETS,
        "max_abs_torque_nm": 6.0,
        "max_torque_step_nm": 0.25,
        "pin_backend": FakePin,
    }
    values.update(overrides)
    return PayloadGravityCompensator("fixture.urdf", **values)


def test_payload_delta_is_clipped_without_duplicate_bare_gravity() -> None:
    subject = compensator()
    raw = subject.raw_torque("arm_a", [0.5] * 7)
    np.testing.assert_allclose(raw, [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 6.0])


def test_torque_slew_prevents_startup_step_and_reset_clears_history() -> None:
    subject = compensator(max_torque_step_nm=0.25)
    first = subject.torque("arm_a", [0.0] * 7)
    assert np.max(np.abs(first)) <= 0.25
    for _ in range(30):
        reached = subject.torque("arm_a", [0.0] * 7)
    np.testing.assert_allclose(reached, subject.raw_torque("arm_a", [0.0] * 7))
    subject.reset("arm_a")
    np.testing.assert_allclose(subject.last_torque["arm_a"], 0.0)


def test_payload_model_receives_mass_and_com() -> None:
    subject = compensator(mass_kg=1.01, com_xyz_m=[0.0, 0.0, 0.075])
    for arm in ARM_NAMES:
        assert subject.payload_models[arm].payload_mass == pytest.approx(1.01)
        np.testing.assert_allclose(
            subject.payload_models[arm].payload_translation,
            [0.0, 0.0, 0.075],
        )


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"mass_kg": 0.0}, "mass_kg"),
        ({"com_xyz_m": [0.0, 0.0]}, "com_xyz_m"),
        ({"max_abs_torque_nm": -1.0}, "max_abs_torque_nm"),
        (
            {"world_from_base_rotations": {"arm_a": np.eye(3)}},
            "arm_a and arm_b",
        ),
        (
            {
                "world_from_base_rotations": {
                    "arm_a": np.diag([1.0, 1.0, -1.0]),
                    "arm_b": np.eye(3),
                }
            },
            "rigid 3x3",
        ),
    ],
)
def test_invalid_payload_model_is_rejected(overrides, message) -> None:
    with pytest.raises(ValueError, match=message):
        compensator(**overrides)


def test_invalid_arm_and_joint_vector_are_rejected() -> None:
    subject = compensator()
    with pytest.raises(ValueError, match="unknown arm"):
        subject.raw_torque("arm_c", [0.0] * 7)
    with pytest.raises(ValueError, match="seven finite"):
        subject.raw_torque("arm_a", [0.0] * 6 + [math.nan])
