from __future__ import annotations

import math
import tempfile
import unittest
import xml.etree.ElementTree as ET

import mujoco

from xrobotoolkit_teleop.hardware.nero_model import (
    BENCH_BASE_TRANSFORMS,
    DEFAULT_NERO_URDF_PATH,
    FRONT_AXIS,
    HARDWARE_TO_MODEL_JOINT_OFFSETS,
    NERO_BENCH_STARTUP_HARDWARE_POSE,
    OPENARM_BASE_TRANSFORMS,
    BaseTransform,
    build_dual_nero_urdf,
    configure_dual_nero_collision_pairs,
    dual_nero_collision_pairs,
    load_dual_nero_placo_model,
)
from xrobotoolkit_teleop.simulation.nero_mujoco import (
    build_dual_nero_mujoco_assets,
)


class NeroModelTests(unittest.TestCase):
    def test_official_urdf_is_available(self):
        self.assertTrue(DEFAULT_NERO_URDF_PATH.is_file(), DEFAULT_NERO_URDF_PATH)

    def test_builds_prefixed_dual_arm_model(self):
        root = ET.fromstring(build_dual_nero_urdf(base_transforms=BENCH_BASE_TRANSFORMS))
        joints = {joint.get("name"): joint for joint in root.findall("joint")}

        for arm in ("arm_a", "arm_b"):
            for index in range(1, 8):
                self.assertIn(f"{arm}_joint{index}", joints)
            self.assertIn(f"{arm}_tcp_joint", joints)
            self.assertIn(f"{arm}_world_to_base_link", joints)

        arm_b_origin = joints["arm_b_world_to_base_link"].find("origin")
        self.assertEqual(arm_b_origin.get("xyz"), "0.26 0 0")
        self.assertEqual(
            arm_b_origin.get("rpy"),
            f"0 {math.pi / 2.0:.10g} 0",
        )
        for mesh in root.findall(".//mesh"):
            self.assertTrue(mesh.get("filename").startswith("/"))

    def test_bench_layout_has_opposed_bases_and_downward_joint2_pose(self):
        self.assertEqual(
            BENCH_BASE_TRANSFORMS["arm_a"],
            BaseTransform((0.0, 0.0, 0.0), (math.pi, math.pi / 2.0, 0.0)),
        )
        self.assertEqual(
            BENCH_BASE_TRANSFORMS["arm_b"],
            BaseTransform((0.260, 0.0, 0.0), (0.0, math.pi / 2.0, 0.0)),
        )

        model = load_dual_nero_placo_model(
            base_transforms=BENCH_BASE_TRANSFORMS,
            joint_zero_offsets=HARDWARE_TO_MODEL_JOINT_OFFSETS,
        )
        for arm in ("arm_a", "arm_b"):
            for index, value in enumerate(HARDWARE_TO_MODEL_JOINT_OFFSETS[arm], 1):
                model.set_joint(f"{arm}_joint{index}", value)
        model.update_kinematics()
        arm_a_tcp = model.get_T_world_frame("arm_a_tcp_link")[:3, 3]
        arm_b_tcp = model.get_T_world_frame("arm_b_tcp_link")[:3, 3]
        self.assertLess(arm_a_tcp[2], -0.5)
        self.assertLess(arm_b_tcp[2], -0.5)
        self.assertLess(arm_a_tcp[0], 0.0)
        self.assertGreater(arm_b_tcp[0], 0.260)

    def test_placo_loads_fourteen_actuated_joints(self):
        model = load_dual_nero_placo_model()
        names = set(model.model.names)
        expected = {
            f"{arm}_joint{index}"
            for arm in ("arm_a", "arm_b")
            for index in range(1, 8)
        }
        self.assertTrue(expected.issubset(names))

    def test_collision_pairs_keep_cross_arm_and_non_adjacent_contacts(self):
        pairs = {frozenset(pair) for pair in dual_nero_collision_pairs()}
        self.assertIn(
            frozenset(("arm_a_link7", "arm_b_link7")),
            pairs,
        )
        self.assertIn(
            frozenset(("arm_a_base_link", "arm_a_link2")),
            pairs,
        )
        self.assertNotIn(
            frozenset(("arm_a_link5", "arm_a_link6")),
            pairs,
        )
        self.assertEqual(len(pairs), 106)

    def test_placo_uses_only_filtered_collision_pairs(self):
        model = load_dual_nero_placo_model()
        configure_dual_nero_collision_pairs(model)
        self.assertEqual(
            len(model.collision_model.collisionPairs),
            len(dual_nero_collision_pairs()),
        )

    def test_filtered_pairs_still_detect_non_adjacent_collision(self):
        model = load_dual_nero_placo_model(
            base_transforms=BENCH_BASE_TRANSFORMS,
            joint_zero_offsets=HARDWARE_TO_MODEL_JOINT_OFFSETS,
        )
        configure_dual_nero_collision_pairs(model)
        hardware_joints = (
            (
                0.6991814929,
                0.0492799043,
                -0.0172437604,
                -0.2303799756,
                -2.6925740950,
                -0.4073077499,
                0.6032869588,
            ),
            (
                -1.6198739065,
                -0.4554043820,
                -2.7370257514,
                1.6098679606,
                -1.9057307584,
                -0.2800011378,
                1.1948492130,
            ),
        )
        for arm_name, joints in zip(("arm_a", "arm_b"), hardware_joints):
            for index, (joint, offset) in enumerate(
                zip(joints, HARDWARE_TO_MODEL_JOINT_OFFSETS[arm_name]),
                1,
            ):
                model.set_joint(f"{arm_name}_joint{index}", joint + offset)
        model.update_kinematics()

        collisions = {
            frozenset((collision.bodyA, collision.bodyB))
            for collision in model.self_collisions(False)
        }
        self.assertIn(
            frozenset(("arm_b_base_link_0", "arm_b_link2_0")),
            collisions,
        )

    def test_joint2_and_joint3_hardware_zero_map_to_ninety_degrees(self):
        # Arm A and Arm B carry OPPOSITE joint3 signs: the bench bases are
        # mirrored, so mirrored joint3 offsets are what make both elbows fold
        # toward the same side. Shared signs would splay them apart.
        self.assertEqual(
            HARDWARE_TO_MODEL_JOINT_OFFSETS["arm_a"],
            (0.0, -math.pi / 2.0, -math.pi / 2.0, 0.0, 0.0, 0.0, 0.0),
        )
        self.assertEqual(
            HARDWARE_TO_MODEL_JOINT_OFFSETS["arm_b"],
            (0.0, -math.pi / 2.0, math.pi / 2.0, 0.0, 0.0, 0.0, 0.0),
        )

        root = ET.fromstring(
            build_dual_nero_urdf(
                joint_zero_offsets=HARDWARE_TO_MODEL_JOINT_OFFSETS,
            )
        )
        source_root = ET.parse(DEFAULT_NERO_URDF_PATH).getroot()
        for arm in ("arm_a", "arm_b"):
            for joint_index in (2, 3):
                offset = HARDWARE_TO_MODEL_JOINT_OFFSETS[arm][joint_index - 1]
                source_limit = source_root.find(f"./joint[@name='joint{joint_index}']/limit")
                shifted_limit = root.find(f"./joint[@name='{arm}_joint{joint_index}']/limit")
                for bound in ("lower", "upper"):
                    self.assertAlmostEqual(
                        float(shifted_limit.get(bound)),
                        float(source_limit.get(bound)) + offset,
                    )
                # Hardware zero must remain commandable after the shift.
                self.assertLessEqual(float(shifted_limit.get("lower")), offset)
                self.assertGreaterEqual(float(shifted_limit.get("upper")), offset)

    def test_startup_pose_bends_both_elbows_forward_without_recalibrating(self):
        # The startup pose is a POSE, not a calibration. Hardware joint4=0 really
        # is model joint4=0 (a straight elbow), so folding this into
        # HARDWARE_TO_MODEL_JOINT_OFFSETS would assert a mechanical offset that
        # does not exist and would break the identity-FK check.
        for arm in ("arm_a", "arm_b"):
            self.assertEqual(HARDWARE_TO_MODEL_JOINT_OFFSETS[arm][3], 0.0)
            pose = NERO_BENCH_STARTUP_HARDWARE_POSE[arm]
            self.assertEqual(len(pose), 7)
            self.assertAlmostEqual(pose[3], math.pi / 2.0)
            # Only joint4 is posed; everything else stays at hardware zero.
            for index, value in enumerate(pose):
                if index != 3:
                    self.assertEqual(value, 0.0, f"{arm} joint{index + 1}")

        source_root = ET.parse(DEFAULT_NERO_URDF_PATH).getroot()
        limit = source_root.find("./joint[@name='joint4']/limit")
        lower, upper = float(limit.get("lower")), float(limit.get("upper"))
        margin = math.radians(3.0)
        for arm in ("arm_a", "arm_b"):
            target = NERO_BENCH_STARTUP_HARDWARE_POSE[arm][3]
            self.assertGreater(target, lower + margin)
            self.assertLess(target, upper - margin)

        model = load_dual_nero_placo_model(
            base_transforms=BENCH_BASE_TRANSFORMS,
            joint_zero_offsets=HARDWARE_TO_MODEL_JOINT_OFFSETS,
        )

        def wrists(hardware_pose):
            for arm in ("arm_a", "arm_b"):
                for index, (value, offset) in enumerate(
                    zip(hardware_pose[arm], HARDWARE_TO_MODEL_JOINT_OFFSETS[arm]), 1
                ):
                    model.set_joint(f"{arm}_joint{index}", value + offset)
            model.update_kinematics()
            return {
                arm: model.get_T_world_frame(f"{arm}_tcp_link")[:3, 3].copy()
                for arm in ("arm_a", "arm_b")
            }

        straight = wrists({arm: (0.0,) * 7 for arm in ("arm_a", "arm_b")})
        posed = wrists(NERO_BENCH_STARTUP_HARDWARE_POSE)
        for arm in ("arm_a", "arm_b"):
            advance = sum(
                FRONT_AXIS[axis] * (posed[arm][axis] - straight[arm][axis]) for axis in range(3)
            )
            self.assertGreater(advance, 0.2, f"{arm} did not reach forward from the singularity")
            self.assertGreater(posed[arm][2], straight[arm][2], f"{arm} wrist did not rise")
        # Both wrists end up level with each other, like a person's two arms.
        self.assertAlmostEqual(posed["arm_a"][1], posed["arm_b"][1], places=6)
        self.assertAlmostEqual(posed["arm_a"][2], posed["arm_b"][2], places=6)

    def test_bench_elbow_flex_moves_both_wrists_the_same_way(self):
        model = load_dual_nero_placo_model(
            base_transforms=BENCH_BASE_TRANSFORMS,
            joint_zero_offsets=HARDWARE_TO_MODEL_JOINT_OFFSETS,
        )

        def wrists(elbow_flex):
            for arm in ("arm_a", "arm_b"):
                for index, value in enumerate(HARDWARE_TO_MODEL_JOINT_OFFSETS[arm], 1):
                    model.set_joint(f"{arm}_joint{index}", value)
                model.set_joint(f"{arm}_joint4", HARDWARE_TO_MODEL_JOINT_OFFSETS[arm][3] + elbow_flex)
            model.update_kinematics()
            return {arm: model.get_T_world_frame(f"{arm}_tcp_link")[:3, 3].copy() for arm in ("arm_a", "arm_b")}

        rest = wrists(0.0)
        flexed = wrists(math.radians(60.0))
        front = FRONT_AXIS
        for arm in ("arm_a", "arm_b"):
            advance = sum(front[axis] * (flexed[arm][axis] - rest[arm][axis]) for axis in range(3))
            self.assertGreater(advance, 0.05, f"{arm} elbow did not fold toward FRONT_AXIS")
            self.assertGreater(flexed[arm][2], rest[arm][2], f"{arm} wrist did not rise when flexing")
        # Both wrists stay level with each other, like a person's arms.
        self.assertAlmostEqual(flexed["arm_a"][1], flexed["arm_b"][1], places=6)
        self.assertAlmostEqual(flexed["arm_a"][2], flexed["arm_b"][2], places=6)

    def test_openarm_model_contains_torso_and_shoulder_visuals(self):
        root = ET.fromstring(
            build_dual_nero_urdf(
                base_transforms=OPENARM_BASE_TRANSFORMS,
                include_openarm_frame=True,
            )
        )
        lab_world = root.find("./link[@name='lab_world']")
        self.assertIsNotNone(lab_world)
        visuals = {visual.get("name") for visual in lab_world.findall("visual")}
        self.assertEqual(visuals, {"torso_column", "shoulder_bar"})
        joints = {joint.get("name"): joint for joint in root.findall("joint")}
        self.assertEqual(
            joints["arm_a_world_to_base_link"].find("origin").get("xyz"),
            "0 -0.24 0.95",
        )
        self.assertEqual(
            joints["arm_b_world_to_base_link"].find("origin").get("xyz"),
            "0 0.24 0.95",
        )

    def test_builds_compilable_mujoco_scene(self):
        with tempfile.TemporaryDirectory() as output_dir:
            assets = build_dual_nero_mujoco_assets(output_dir)
            model = mujoco.MjModel.from_xml_path(str(assets.scene_path))
            self.assertEqual(model.nq, 14)
            self.assertEqual(model.nu, 14)
            self.assertGreaterEqual(model.nmocap, 2)
            self.assertNotEqual(model.key("home").id, -1)
            for arm_name in ("arm_a", "arm_b"):
                self.assertNotEqual(model.body(f"{arm_name}_link7").id, -1)
                self.assertNotEqual(model.body(f"{arm_name}_target").id, -1)


if __name__ == "__main__":
    unittest.main()
