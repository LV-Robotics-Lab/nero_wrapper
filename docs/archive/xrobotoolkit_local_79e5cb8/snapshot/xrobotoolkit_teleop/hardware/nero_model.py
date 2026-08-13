from __future__ import annotations

import copy
import json
import math
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Tuple


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_NERO_URDF_PATH = (
    REPOSITORY_ROOT
    / "dependencies"
    / "agx_arm_ros"
    / "src"
    / "agx_arm_description"
    / "agx_arm_urdf"
    / "nero"
    / "urdf"
    / "nero_description.urdf"
)


@dataclass(frozen=True)
class BaseTransform:
    xyz: Tuple[float, float, float]
    rpy: Tuple[float, float, float]


# Physical opposed-base layout. The shared lab_world origin is Arm A's base
# center, +X points from Arm A to Arm B, and +Z points upward. With the
# hardware-to-model joint2=-90 degree calibration below, the two shoulder
# assemblies stay on the outer sides and both first arm segments point down.
BENCH_BASE_TRANSFORMS: Dict[str, BaseTransform] = {
    "arm_a": BaseTransform((0.0, 0.0, 0.0), (math.pi, math.pi / 2.0, 0.0)),
    "arm_b": BaseTransform((0.260, 0.0, 0.0), (0.0, math.pi / 2.0, 0.0)),
}
# Simulation-only OpenArm-style display. These are not the mounting transforms
# of the current physical NERO rig.
OPENARM_BASE_TRANSFORMS: Dict[str, BaseTransform] = {
    "arm_a": BaseTransform((0.0, -0.24, 0.95), (math.pi, 0.0, 0.0)),
    "arm_b": BaseTransform((0.0, 0.24, 0.95), (math.pi, 0.0, math.pi)),
}
DEFAULT_BASE_TRANSFORMS = BENCH_BASE_TRANSFORMS


def dual_nero_collision_pairs() -> list[tuple[str, str]]:
    """Collision pairs that can represent a real dual-arm self collision.

    PlaCo enables every geometry pair by default, including directly connected
    links. Those adjacent meshes overlap by construction (link5/link6 does so
    even at neutral), and checking all of their triangle contacts dominates the
    teleoperation cycle. Exclude only parent/child pairs; retain every
    non-adjacent same-arm pair and every cross-arm pair.
    """
    links = [
        (
            arm_name,
            link_number,
            f"{arm_name}_{'base_link' if link_number == 0 else f'link{link_number}'}",
        )
        for arm_name in ("arm_a", "arm_b")
        for link_number in range(8)
    ]
    pairs = []
    for first_index, (first_arm, first_number, first_name) in enumerate(links):
        for second_arm, second_number, second_name in links[first_index + 1 :]:
            if first_arm == second_arm and abs(first_number - second_number) <= 1:
                continue
            pairs.append((first_name, second_name))
    return pairs


def configure_dual_nero_collision_pairs(model) -> None:
    """Load the filtered pair set through PlaCo's supported JSON API."""
    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".json",
        encoding="utf-8",
    ) as collision_file:
        json.dump(dual_nero_collision_pairs(), collision_file)
        collision_file.flush()
        model.load_collision_pairs(collision_file.name)

# The installed arms hang with their first articulated segment down and the
# elbow rolled into the humanoid plane while the firmware reports joint2=0 and
# joint3=0.  In the official URDF that mechanical pose is joint2=-90 degrees
# and |joint3|=90 degrees, so hardware feedback must be translated into the
# model coordinate system (and model commands translated back before CAN
# output).
#
# The joint3 term rotates each elbow axis from world Y onto world X so the
# elbow folds fore/aft rather than sideways.  BENCH_BASE_TRANSFORMS mirrors the
# two bases (Arm A is roll-flipped by pi), so the joint3 signs must be OPPOSITE
# for both elbows to fold toward the same side of the rig.  FRONT_AXIS below
# records which way that is: with these signs a positive joint4 (elbow flex)
# moves both wrists toward -Y, like a person bending both elbows forward.
HARDWARE_TO_MODEL_JOINT_OFFSETS: Dict[str, Tuple[float, ...]] = {
    "arm_a": (0.0, -math.pi / 2.0, -math.pi / 2.0, 0.0, 0.0, 0.0, 0.0),
    "arm_b": (0.0, -math.pi / 2.0, math.pi / 2.0, 0.0, 0.0, 0.0, 0.0),
}

# Unit vector, in lab_world, that both wrists advance along when the elbows
# flex. Used to frame the simulation camera and place the IK mocap targets.
FRONT_AXIS: Tuple[float, float, float] = (0.0, -1.0, 0.0)

# Hardware joint targets to ramp to after arming, before teleoperation starts.
#
# This is a POSE, not a calibration: hardware joint4=0 really is model joint4=0
# (a straight elbow), so this must never be folded into
# HARDWARE_TO_MODEL_JOINT_OFFSETS -- doing so would claim a mechanical offset
# that does not exist and would break the identity-FK check.
#
# A straight elbow at hardware all-zeros is the arm's wrist singularity, which
# the controller reports as arm_status=3/SINGULARITY_POINT and where Cartesian
# IK has no well-conditioned solution. joint4=+90 degrees bends both elbows
# forward along FRONT_AXIS (verified symmetric and level in the bench model),
# clears the singularity, and sits well inside the joint4 limit of
# [-58, +123] degrees.
NERO_BENCH_STARTUP_HARDWARE_POSE: Dict[str, Tuple[float, ...]] = {
    "arm_a": (0.0, 0.0, 0.0, math.pi / 2.0, 0.0, 0.0, 0.0),
    "arm_b": (0.0, 0.0, 0.0, math.pi / 2.0, 0.0, 0.0, 0.0),
}


def _format_vector(values: Iterable[float]) -> str:
    return " ".join(f"{float(value):.10g}" for value in values)


def _rewrite_mesh_paths(element: ET.Element, mesh_root: Path) -> None:
    package_prefix = "package://agx_arm_description/agx_arm_urdf/nero/meshes/"
    for mesh in element.findall(".//mesh"):
        filename = mesh.get("filename", "")
        if filename.startswith(package_prefix):
            relative_path = filename[len(package_prefix) :]
            mesh.set("filename", str((mesh_root / relative_path).resolve()))


def _prefix_arm_element(element: ET.Element, prefix: str, mesh_root: Path) -> ET.Element:
    result = copy.deepcopy(element)
    name = result.get("name")
    if name:
        result.set("name", f"{prefix}{name}")

    for tag in ("parent", "child"):
        for reference in result.findall(f".//{tag}"):
            link = reference.get("link")
            if link:
                reference.set("link", f"{prefix}{link}")

    _rewrite_mesh_paths(result, mesh_root)
    return result


def build_dual_nero_urdf(
    source_urdf_path: str | Path = DEFAULT_NERO_URDF_PATH,
    base_transforms: Dict[str, BaseTransform] = DEFAULT_BASE_TRANSFORMS,
    tcp_offsets: Dict[str, BaseTransform] | None = None,
    include_openarm_frame: bool = False,
    joint_zero_offsets: Dict[str, Tuple[float, ...]] | None = None,
) -> str:
    """Build a prefixed dual-NERO URDF from AgileX's official single-arm model."""
    source_path = Path(source_urdf_path).resolve()
    if not source_path.is_file():
        raise FileNotFoundError(
            f"NERO URDF not found at {source_path}. Run setup_conda.sh --install "
            "to fetch the pinned agx_arm_ros dependency."
        )

    source_root = ET.parse(source_path).getroot()
    source_links = [element for element in source_root.findall("link") if element.get("name") != "world"]
    source_joints = [
        element for element in source_root.findall("joint") if element.get("name") != "world_to_base_link"
    ]
    if not source_links or len(source_joints) != 7:
        raise ValueError("Expected the official NERO model to contain seven movable joints")

    mesh_root = source_path.parent.parent / "meshes"
    result_root = ET.Element("robot", {"name": "nero_dual"})
    lab_world = ET.SubElement(result_root, "link", {"name": "lab_world"})
    if include_openarm_frame:
        for name, xyz, size, color in (
            (
                "torso_column",
                (0.08, 0.0, 0.48),
                (0.22, 0.32, 0.90),
                (0.13, 0.16, 0.21, 1.0),
            ),
            (
                "shoulder_bar",
                (0.0, 0.0, 0.94),
                (0.20, 0.58, 0.13),
                (0.20, 0.24, 0.31, 1.0),
            ),
        ):
            visual = ET.SubElement(lab_world, "visual", {"name": name})
            ET.SubElement(
                visual,
                "origin",
                {"xyz": _format_vector(xyz), "rpy": "0 0 0"},
            )
            geometry = ET.SubElement(visual, "geometry")
            ET.SubElement(geometry, "box", {"size": _format_vector(size)})
            material = ET.SubElement(visual, "material", {"name": f"{name}_material"})
            ET.SubElement(material, "color", {"rgba": _format_vector(color)})
    tcp_offsets = tcp_offsets or {}
    joint_zero_offsets = joint_zero_offsets or {}

    for arm_name in ("arm_a", "arm_b"):
        if arm_name not in base_transforms:
            raise ValueError(f"Missing base transform for {arm_name}")
        arm_joint_offsets = tuple(joint_zero_offsets.get(arm_name, (0.0,) * 7))
        if len(arm_joint_offsets) != 7 or not all(math.isfinite(value) for value in arm_joint_offsets):
            raise ValueError(f"{arm_name} joint_zero_offsets must contain seven finite values")
        prefix = f"{arm_name}_"
        transform = base_transforms[arm_name]

        mount = ET.SubElement(result_root, "joint", {"name": f"{prefix}world_to_base_link", "type": "fixed"})
        ET.SubElement(mount, "parent", {"link": "lab_world"})
        ET.SubElement(mount, "child", {"link": f"{prefix}base_link"})
        ET.SubElement(
            mount,
            "origin",
            {"xyz": _format_vector(transform.xyz), "rpy": _format_vector(transform.rpy)},
        )

        for link in source_links:
            result_root.append(_prefix_arm_element(link, prefix, mesh_root))
        for joint_index, joint in enumerate(source_joints):
            prefixed_joint = _prefix_arm_element(joint, prefix, mesh_root)
            offset = arm_joint_offsets[joint_index]
            limit = prefixed_joint.find("limit")
            if limit is not None and offset != 0.0:
                for bound in ("lower", "upper"):
                    if limit.get(bound) is not None:
                        limit.set(bound, f"{float(limit.get(bound)) + offset:.10g}")
            result_root.append(prefixed_joint)

        tcp = tcp_offsets.get(arm_name, BaseTransform((0.0, 0.0, 0.0), (0.0, 0.0, 0.0)))
        ET.SubElement(result_root, "link", {"name": f"{prefix}tcp_link"})
        tcp_joint = ET.SubElement(result_root, "joint", {"name": f"{prefix}tcp_joint", "type": "fixed"})
        ET.SubElement(tcp_joint, "parent", {"link": f"{prefix}link7"})
        ET.SubElement(tcp_joint, "child", {"link": f"{prefix}tcp_link"})
        ET.SubElement(
            tcp_joint,
            "origin",
            {"xyz": _format_vector(tcp.xyz), "rpy": _format_vector(tcp.rpy)},
        )

    return ET.tostring(result_root, encoding="unicode")


def load_dual_nero_placo_model(
    source_urdf_path: str | Path = DEFAULT_NERO_URDF_PATH,
    base_transforms: Dict[str, BaseTransform] = DEFAULT_BASE_TRANSFORMS,
    tcp_offsets: Dict[str, BaseTransform] | None = None,
    include_openarm_frame: bool = False,
    joint_zero_offsets: Dict[str, Tuple[float, ...]] | None = None,
):
    import placo

    source_path = Path(source_urdf_path).resolve()
    urdf_content = build_dual_nero_urdf(
        source_path,
        base_transforms,
        tcp_offsets,
        include_openarm_frame,
        joint_zero_offsets,
    )
    return placo.RobotWrapper(str(source_path), 0, urdf_content)
