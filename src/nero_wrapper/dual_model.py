"""Build a prefixed dual-NERO URDF without opening a robot or solver."""

from __future__ import annotations

import copy
import json
import math
import tempfile
import xml.etree.ElementTree as ET
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ARM_NAMES = ("arm_a", "arm_b")


@dataclass(frozen=True)
class BaseTransform:
    xyz: tuple[float, float, float]
    rpy: tuple[float, float, float]

    def __post_init__(self) -> None:
        if len(self.xyz) != 3 or len(self.rpy) != 3:
            raise ValueError("BaseTransform requires xyz and rpy triples")
        if not all(math.isfinite(float(value)) for value in (*self.xyz, *self.rpy)):
            raise ValueError("BaseTransform values must be finite")


# 2026-08-13 photographed hanging-gantry layout: lab +X forward, +Y left and
# +Z up, with arm_a on the right and arm_b on the left. The base cylinders are
# horizontal and their local -Z mounting bottoms point inward. The 480 mm
# spacing is an installation estimate, not a generic default.
LAB_DUAL_BENCH_BASE_TRANSFORMS = {
    "arm_a": BaseTransform(
        (0.0, -0.240, 0.0), (math.pi / 2.0, math.pi / 2.0, 0.0)
    ),
    "arm_b": BaseTransform(
        (0.0, 0.240, 0.0), (-math.pi / 2.0, math.pi / 2.0, 0.0)
    ),
}

# Hardware reports J2=J3=0 in the photographed hanging posture. The official
# URDF represents that posture with J2=-90 degrees and mirrored J3 values.
# Commands are converted back by the IK wrapper before publication.
HARDWARE_TO_MODEL_JOINT_OFFSETS = {
    "arm_a": (0.0, -math.pi / 2.0, -math.pi / 2.0, 0.0, 0.0, 0.0, 0.0),
    "arm_b": (0.0, -math.pi / 2.0, math.pi / 2.0, 0.0, 0.0, 0.0, 0.0),
}

# The 2026-08-14 Execute trace supplied the missing dynamic calibration: a
# positive hardware J2 moved both installed distal chains toward the centre,
# while the official URDF at the accepted zero-pose offsets moves them away.
# A constant offset cannot express that axis reversal.  Keep the model's
# positive J2 direction as the collision/IK "outward" coordinate and reflect
# hardware J2 explicitly in both feedback and command conversions.
HARDWARE_TO_MODEL_JOINT_SIGNS = {
    "arm_a": (1.0, -1.0, 1.0, 1.0, 1.0, 1.0, 1.0),
    "arm_b": (1.0, -1.0, 1.0, 1.0, 1.0, 1.0, 1.0),
}

# Hardware-coordinate parity that maps an arm_a pose to the reflected arm_b
# pose in the photographed installation. This is a kinematic mirror contract,
# not an additional hardware zero offset.
HARDWARE_MIRROR_JOINT_PARITY = (-1.0, 1.0, -1.0, 1.0, -1.0, -1.0, 1.0)


def _format_vector(values: Iterable[float]) -> str:
    return " ".join(f"{float(value):.10g}" for value in values)


def _rewrite_mesh_paths(element: ET.Element, mesh_root: Path) -> None:
    prefix = "package://agx_arm_description/agx_arm_urdf/nero/meshes/"
    for mesh in element.findall(".//mesh"):
        filename = mesh.get("filename", "")
        if filename.startswith(prefix):
            mesh.set("filename", str((mesh_root / filename[len(prefix) :]).resolve()))


def _prefix_element(element: ET.Element, prefix: str, mesh_root: Path) -> ET.Element:
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


def _arm_mapping(
    values: Mapping[str, Any],
    *,
    name: str,
) -> None:
    if set(values) != set(ARM_NAMES):
        raise ValueError(f"{name} must contain exactly arm_a and arm_b")


def build_dual_nero_urdf(
    source_urdf_path: str | Path,
    *,
    base_transforms: Mapping[str, BaseTransform],
    joint_offsets: Mapping[str, Sequence[float]] = HARDWARE_TO_MODEL_JOINT_OFFSETS,
    joint_signs: Mapping[str, Sequence[float]] = HARDWARE_TO_MODEL_JOINT_SIGNS,
    tcp_offsets: Mapping[str, BaseTransform] | None = None,
) -> str:
    """Build a dual-arm model in ``lab_world`` from one official NERO URDF."""

    _arm_mapping(base_transforms, name="base_transforms")
    _arm_mapping(joint_offsets, name="joint_offsets")
    _arm_mapping(joint_signs, name="joint_signs")
    if tcp_offsets is not None:
        _arm_mapping(tcp_offsets, name="tcp_offsets")
    source_path = Path(source_urdf_path).expanduser().resolve()
    if not source_path.is_file():
        raise FileNotFoundError(f"NERO URDF not found: {source_path}")
    source_root = ET.parse(source_path).getroot()
    source_links = [
        element
        for element in source_root.findall("link")
        if element.get("name") != "world"
    ]
    source_joints = [
        element
        for element in source_root.findall("joint")
        if element.get("name") != "world_to_base_link"
    ]
    if len(source_joints) != 7:
        raise ValueError("official NERO URDF must contain exactly seven arm joints")

    mesh_root = source_path.parent.parent / "meshes"
    result = ET.Element("robot", {"name": "nero_dual"})
    ET.SubElement(result, "link", {"name": "lab_world"})
    resolved_tcp_offsets = tcp_offsets or {
        arm: BaseTransform((0.0, 0.0, 0.0), (0.0, 0.0, 0.0))
        for arm in ARM_NAMES
    }

    for arm in ARM_NAMES:
        transform = base_transforms[arm]
        offsets = tuple(float(value) for value in joint_offsets[arm])
        if len(offsets) != 7 or not all(math.isfinite(value) for value in offsets):
            raise ValueError(f"{arm} joint offset must contain seven finite values")
        signs = tuple(float(value) for value in joint_signs[arm])
        if len(signs) != 7 or any(value not in (-1.0, 1.0) for value in signs):
            raise ValueError(f"{arm} joint signs must contain seven +1/-1 values")
        prefix = f"{arm}_"
        mount = ET.SubElement(
            result,
            "joint",
            {"name": f"{prefix}world_to_base_link", "type": "fixed"},
        )
        ET.SubElement(mount, "parent", {"link": "lab_world"})
        ET.SubElement(mount, "child", {"link": f"{prefix}base_link"})
        ET.SubElement(
            mount,
            "origin",
            {"xyz": _format_vector(transform.xyz), "rpy": _format_vector(transform.rpy)},
        )

        for link in source_links:
            result.append(_prefix_element(link, prefix, mesh_root))
        for index, joint in enumerate(source_joints):
            prefixed = _prefix_element(joint, prefix, mesh_root)
            limit = prefixed.find("limit")
            if limit is not None:
                raw_lower = limit.get("lower")
                raw_upper = limit.get("upper")
                if (raw_lower is None) != (raw_upper is None):
                    raise ValueError(
                        f"official NERO joint{index + 1} has an incomplete limit"
                    )
                if raw_lower is not None and raw_upper is not None:
                    transformed = (
                        offsets[index] + signs[index] * float(raw_lower),
                        offsets[index] + signs[index] * float(raw_upper),
                    )
                    limit.set("lower", f"{min(transformed):.10g}")
                    limit.set("upper", f"{max(transformed):.10g}")
            result.append(prefixed)

        tcp_offset = resolved_tcp_offsets[arm]
        ET.SubElement(result, "link", {"name": f"{prefix}tcp_link"})
        tcp_joint = ET.SubElement(
            result,
            "joint",
            {"name": f"{prefix}tcp_joint", "type": "fixed"},
        )
        ET.SubElement(tcp_joint, "parent", {"link": f"{prefix}link7"})
        ET.SubElement(tcp_joint, "child", {"link": f"{prefix}tcp_link"})
        ET.SubElement(
            tcp_joint,
            "origin",
            {
                "xyz": _format_vector(tcp_offset.xyz),
                "rpy": _format_vector(tcp_offset.rpy),
            },
        )

    return ET.tostring(result, encoding="unicode")


def collision_pairs() -> list[tuple[str, str]]:
    """Return all cross-arm and non-adjacent same-arm collision pairs."""

    links = [
        (arm, number, f"{arm}_{'base_link' if number == 0 else f'link{number}'}")
        for arm in ARM_NAMES
        for number in range(8)
    ]
    result: list[tuple[str, str]] = []
    for first_index, (first_arm, first_number, first_name) in enumerate(links):
        for second_arm, second_number, second_name in links[first_index + 1 :]:
            if first_arm == second_arm and abs(first_number - second_number) <= 1:
                continue
            result.append((first_name, second_name))
    return result


def load_dual_nero_model(
    source_urdf_path: str | Path,
    *,
    base_transforms: Mapping[str, BaseTransform],
    joint_offsets: Mapping[str, Sequence[float]] = HARDWARE_TO_MODEL_JOINT_OFFSETS,
    joint_signs: Mapping[str, Sequence[float]] = HARDWARE_TO_MODEL_JOINT_SIGNS,
    tcp_offsets: Mapping[str, BaseTransform] | None = None,
) -> Any:
    """Load the generated model through optional Placo after explicit request."""

    try:
        import placo
    except ImportError as exc:
        raise RuntimeError("Placo is required to load the dual-NERO model") from exc
    source_path = Path(source_urdf_path).expanduser().resolve()
    content = build_dual_nero_urdf(
        source_path,
        base_transforms=base_transforms,
        joint_offsets=joint_offsets,
        joint_signs=joint_signs,
        tcp_offsets=tcp_offsets,
    )
    model = placo.RobotWrapper(str(source_path), 0, content)
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", encoding="utf-8"
    ) as collision_file:
        json.dump(collision_pairs(), collision_file)
        collision_file.flush()
        model.load_collision_pairs(collision_file.name)
    return model
