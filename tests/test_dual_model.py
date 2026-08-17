import math
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from nero_wrapper.dual_model import (
    ARM_NAMES,
    HARDWARE_TO_MODEL_JOINT_OFFSETS,
    HARDWARE_TO_MODEL_JOINT_SIGNS,
    LAB_DUAL_BENCH_BASE_TRANSFORMS,
    BaseTransform,
    build_dual_nero_urdf,
    collision_pairs,
)


def test_lab_hanging_gantry_transform_contract() -> None:
    arm_a = LAB_DUAL_BENCH_BASE_TRANSFORMS["arm_a"]
    arm_b = LAB_DUAL_BENCH_BASE_TRANSFORMS["arm_b"]

    assert arm_a.xyz == pytest.approx((0.0, -0.24, 0.0))
    assert arm_a.rpy == pytest.approx((math.pi / 2.0, math.pi / 2.0, 0.0))
    assert arm_b.xyz == pytest.approx((0.0, 0.24, 0.0))
    assert arm_b.rpy == pytest.approx((-math.pi / 2.0, math.pi / 2.0, 0.0))
    assert arm_b.xyz[1] - arm_a.xyz[1] == pytest.approx(0.48)
    assert HARDWARE_TO_MODEL_JOINT_OFFSETS["arm_a"] == pytest.approx(
        (0.0, -math.pi / 2.0, -math.pi / 2.0, 0.0, 0.0, 0.0, 0.0)
    )
    assert HARDWARE_TO_MODEL_JOINT_OFFSETS["arm_b"] == pytest.approx(
        (0.0, -math.pi / 2.0, math.pi / 2.0, 0.0, 0.0, 0.0, 0.0)
    )
    assert HARDWARE_TO_MODEL_JOINT_SIGNS["arm_a"] == pytest.approx(
        (1.0, -1.0, 1.0, 1.0, 1.0, 1.0, 1.0)
    )
    assert HARDWARE_TO_MODEL_JOINT_SIGNS["arm_b"] == pytest.approx(
        (1.0, -1.0, 1.0, 1.0, 1.0, 1.0, 1.0)
    )


def write_single_nero(
    path: Path,
    *,
    joint_count: int = 7,
    lower: float = -1.0,
    upper: float = 1.0,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    robot = ET.Element("robot", {"name": "nero"})
    ET.SubElement(robot, "link", {"name": "world"})
    ET.SubElement(robot, "link", {"name": "base_link"})
    world_joint = ET.SubElement(
        robot,
        "joint",
        {"name": "world_to_base_link", "type": "fixed"},
    )
    ET.SubElement(world_joint, "parent", {"link": "world"})
    ET.SubElement(world_joint, "child", {"link": "base_link"})
    for index in range(1, joint_count + 1):
        link = ET.SubElement(robot, "link", {"name": f"link{index}"})
        visual = ET.SubElement(link, "visual")
        geometry = ET.SubElement(visual, "geometry")
        ET.SubElement(
            geometry,
            "mesh",
            {
                "filename": (
                    "package://agx_arm_description/agx_arm_urdf/nero/meshes/"
                    f"link{index}.STL"
                )
            },
        )
        joint = ET.SubElement(
            robot,
            "joint",
            {"name": f"joint{index}", "type": "revolute"},
        )
        parent = "base_link" if index == 1 else f"link{index - 1}"
        ET.SubElement(joint, "parent", {"link": parent})
        ET.SubElement(joint, "child", {"link": f"link{index}"})
        ET.SubElement(
            joint,
            "limit",
            {"lower": str(lower), "upper": str(upper)},
        )
    path.write_text(ET.tostring(robot, encoding="unicode"), encoding="utf-8")
    return path


def test_dual_builder_prefixes_links_joints_and_tcp(tmp_path: Path) -> None:
    source = write_single_nero(tmp_path / "urdf" / "nero.urdf")
    output = build_dual_nero_urdf(
        source,
        base_transforms=LAB_DUAL_BENCH_BASE_TRANSFORMS,
        tcp_offsets={
            arm: BaseTransform(
                (0.22548, 0.0, -0.0235),
                (0.0, math.pi / 2.0, 0.0),
            )
            for arm in ARM_NAMES
        },
    )
    root = ET.fromstring(output)
    links = {element.get("name") for element in root.findall("link")}
    joints = {element.get("name") for element in root.findall("joint")}
    assert {"lab_world", "arm_a_base_link", "arm_b_base_link"} <= links
    assert {"arm_a_link7", "arm_b_link7", "arm_a_tcp_link", "arm_b_tcp_link"} <= links
    assert {"arm_a_joint1", "arm_b_joint7", "arm_a_tcp_joint", "arm_b_tcp_joint"} <= joints
    assert all("package://" not in mesh.get("filename", "") for mesh in root.findall(".//mesh"))
    tcp_origin = root.find("./joint[@name='arm_a_tcp_joint']/origin")
    assert tcp_origin is not None
    assert [float(value) for value in tcp_origin.get("xyz", "").split()] == pytest.approx(
        [0.22548, 0.0, -0.0235]
    )
    assert [float(value) for value in tcp_origin.get("rpy", "").split()] == pytest.approx(
        [0.0, math.pi / 2.0, 0.0]
    )


def test_dual_builder_applies_explicit_joint_offsets(tmp_path: Path) -> None:
    source = write_single_nero(tmp_path / "nero.urdf", lower=-2.0, upper=1.0)
    output = build_dual_nero_urdf(
        source,
        base_transforms=LAB_DUAL_BENCH_BASE_TRANSFORMS,
        joint_offsets={
            "arm_a": (0.1,) + (0.0,) * 6,
            "arm_b": HARDWARE_TO_MODEL_JOINT_OFFSETS["arm_b"],
        },
        joint_signs={
            "arm_a": (-1.0,) + (1.0,) * 6,
            "arm_b": HARDWARE_TO_MODEL_JOINT_SIGNS["arm_b"],
        },
    )
    root = ET.fromstring(output)
    limit_a = root.find("./joint[@name='arm_a_joint1']/limit")
    limit_b = root.find("./joint[@name='arm_b_joint1']/limit")
    assert limit_a is not None
    assert float(limit_a.get("lower")) == pytest.approx(-0.9)
    assert float(limit_a.get("upper")) == pytest.approx(2.1)
    assert limit_b is not None
    assert float(limit_b.get("lower")) == pytest.approx(-2.0)
    assert float(limit_b.get("upper")) == pytest.approx(1.0)


def test_dual_builder_requires_seven_joints_and_both_arms(tmp_path: Path) -> None:
    source = write_single_nero(tmp_path / "nero.urdf", joint_count=6)
    with pytest.raises(ValueError, match="seven"):
        build_dual_nero_urdf(
            source,
            base_transforms=LAB_DUAL_BENCH_BASE_TRANSFORMS,
        )
    valid = write_single_nero(tmp_path / "valid.urdf")
    with pytest.raises(ValueError, match="arm_a and arm_b"):
        build_dual_nero_urdf(
            valid,
            base_transforms={"arm_a": LAB_DUAL_BENCH_BASE_TRANSFORMS["arm_a"]},
        )


def test_collision_pairs_include_cross_arm_and_exclude_adjacent_same_arm() -> None:
    pairs = set(collision_pairs())
    assert ("arm_a_base_link", "arm_b_base_link") in pairs
    assert ("arm_a_link1", "arm_a_link3") in pairs
    assert ("arm_a_link1", "arm_a_link2") not in pairs


def test_base_transform_rejects_nonfinite_values() -> None:
    with pytest.raises(ValueError, match="finite"):
        BaseTransform((0.0, 0.0, float("nan")), (0.0, 0.0, 0.0))


def test_dual_builder_rejects_non_binary_joint_signs(tmp_path: Path) -> None:
    source = write_single_nero(tmp_path / "nero.urdf")
    with pytest.raises(ValueError, match=r"seven \+1/-1"):
        build_dual_nero_urdf(
            source,
            base_transforms=LAB_DUAL_BENCH_BASE_TRANSFORMS,
            joint_signs={
                "arm_a": (1.0, 0.0) + (1.0,) * 5,
                "arm_b": HARDWARE_TO_MODEL_JOINT_SIGNS["arm_b"],
            },
        )
