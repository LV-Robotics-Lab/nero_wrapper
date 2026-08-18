#!/usr/bin/env python3
"""Preview the photographed dual-NERO + DM-TacClaw assembly in MuJoCo.

The arm meshes come from the official NERO URDF.  The TacClaw geometry is a
visual approximation derived from the DM-TacClaw V1.0 manual dimensions and
the installed photographs; it is not vendor CAD and must not be used as a
validated collision model.
"""

from __future__ import annotations

import argparse
import math
import os
import time
from pathlib import Path

import numpy as np

WORKSPACE = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = WORKSPACE / "previews" / "nero_tacclaw_assembly_mujoco.png"

ZERO_JOINTS = {
    "arm_a": np.zeros(7, dtype=np.float64),
    "arm_b": np.zeros(7, dtype=np.float64),
}
IK_READY_JOINTS = {
    "arm_a": np.asarray([0.0, 0.0, 0.0, math.pi / 2.0, 0.0, 0.0, 0.0]),
    "arm_b": np.asarray([0.0, 0.0, 0.0, math.pi / 2.0, 0.0, 0.0, 0.0]),
}

# Read-only feedback captured on 2026-08-11. It is retained only for explicit
# reproduction; the assembly preview defaults to the accepted hardware zero.
CAPTURED_JOINTS = {
    "arm_a": np.asarray(
        [
            0.1460316985,
            -0.0631634656,
            0.0297927703,
            -0.1116138057,
            -0.2539279529,
            -0.2245017017,
            0.0714712329,
        ],
        dtype=np.float64,
    ),
    "arm_b": np.asarray(
        [
            -0.0246789556,
            -0.0036826447,
            -0.1307775209,
            0.0450469480,
            -0.3996629454,
            0.2477669406,
            -0.0244695161,
        ],
        dtype=np.float64,
    ),
}

ARM_COLORS = {
    "base_link": [0.08, 0.09, 0.11, 1.0],
    "link1": [0.78, 0.80, 0.82, 1.0],
    "link2": [0.11, 0.12, 0.14, 1.0],
    "link3": [0.68, 0.70, 0.72, 1.0],
    "link4": [0.10, 0.11, 0.13, 1.0],
    "link5": [0.66, 0.68, 0.70, 1.0],
    "link6": [0.10, 0.11, 0.13, 1.0],
    "link7": [0.08, 0.09, 0.11, 1.0],
}

CHARCOAL = [0.085, 0.095, 0.11, 1.0]
DARK_PANEL = [0.16, 0.17, 0.18, 1.0]
CAMERA_BLACK = [0.015, 0.018, 0.022, 1.0]
LENS_BLUE = [0.025, 0.11, 0.16, 1.0]
TACTILE_ORANGE = [1.0, 0.34, 0.035, 1.0]
MOUNT_SILVER = [0.46, 0.48, 0.50, 1.0]


def _joint_vector(value: str) -> np.ndarray:
    try:
        result = np.asarray([float(item) for item in value.split(",")], dtype=np.float64)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "joint values must be comma-separated numbers"
        ) from exc
    if result.shape != (7,) or not np.all(np.isfinite(result)):
        raise argparse.ArgumentTypeError("exactly seven finite joint values are required")
    return result


def _unit_interval(value: str) -> float:
    try:
        result = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("value must be a number in [0, 1]") from exc
    if not math.isfinite(result) or not 0.0 <= result <= 1.0:
        raise argparse.ArgumentTypeError("value must be a number in [0, 1]")
    return result


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Preview the dual-NERO assembly with approximate DM-TacClaw tools."
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="open the interactive MuJoCo viewer instead of saving a snapshot",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"snapshot path (default: {DEFAULT_OUTPUT})",
    )
    parser.add_argument(
        "--urdf",
        required=True,
        type=Path,
        help="path to the official single-arm NERO URDF",
    )
    parser.add_argument(
        "--base-spacing-m",
        type=float,
        default=0.260,
        help="visual-only base_link spacing (default: measured S11 value 0.260 m)",
    )
    parser.add_argument(
        "--gripper-opening",
        type=_unit_interval,
        default=0.42,
        help="fixed visual opening, 0=closed and 1=100 mm full stroke (default: 0.42)",
    )
    parser.add_argument(
        "--pose",
        choices=("zero", "ik-ready", "captured"),
        default="zero",
        help="named initial hardware pose (default: zero)",
    )
    parser.add_argument(
        "--arm-a",
        type=_joint_vector,
        default=None,
        metavar="J1,J2,J3,J4,J5,J6,J7",
        help="raw arm_a feedback in radians; overrides --pose for arm_a",
    )
    parser.add_argument(
        "--arm-b",
        type=_joint_vector,
        default=None,
        metavar="J1,J2,J3,J4,J5,J6,J7",
        help="raw arm_b feedback in radians; overrides --pose for arm_b",
    )
    args = parser.parse_args()
    if not math.isfinite(args.base_spacing_m) or args.base_spacing_m <= 0.0:
        parser.error("--base-spacing-m must be finite and positive")
    named_pose = {
        "zero": ZERO_JOINTS,
        "ik-ready": IK_READY_JOINTS,
        "captured": CAPTURED_JOINTS,
    }[args.pose]
    if args.arm_a is None:
        args.arm_a = named_pose["arm_a"].copy()
    if args.arm_b is None:
        args.arm_b = named_pose["arm_b"].copy()
    return args


def _add_geom(body, mujoco, *, name: str, geom_type, rgba, **kwargs):
    return body.add_geom(
        name=name,
        type=geom_type,
        rgba=rgba,
        group=1,
        contype=0,
        conaffinity=0,
        **kwargs,
    )


def _add_approximate_tacclaw(mujoco, link7, *, arm: str, opening: float) -> None:
    """Attach a fixed, manual-dimension visual approximation to NERO link7."""
    flange = link7.add_body(
        name=f"{arm}_tacclaw_flange",
        pos=[0.031, 0.0, -0.0235],
        quat=[0.5, -0.5, 0.5, -0.5],
    )
    tool = flange.add_body(
        name=f"{arm}_tacclaw",
        quat=[math.sqrt(0.5), 0.0, 0.0, math.sqrt(0.5)],
    )

    # Manual figure 1.2: 72.8 x 40.8 x 4 mm mounting plate.
    _add_geom(
        tool,
        mujoco,
        name=f"{arm}_tacclaw_mount",
        geom_type=mujoco.mjtGeom.mjGEOM_BOX,
        pos=[0.0, 0.0, 0.002],
        size=[0.0364, 0.0204, 0.002],
        rgba=MOUNT_SILVER,
    )

    # The front drawing gives a 77 mm body. The 177.01 mm side envelope is
    # represented by the camera and connector lobes, not one oversized cuboid.
    _add_geom(
        tool,
        mujoco,
        name=f"{arm}_tacclaw_body",
        geom_type=mujoco.mjtGeom.mjGEOM_BOX,
        pos=[0.0, 0.0, 0.040],
        size=[0.0385, 0.040, 0.034],
        rgba=CHARCOAL,
    )
    _add_geom(
        tool,
        mujoco,
        name=f"{arm}_tacclaw_front_panel",
        geom_type=mujoco.mjtGeom.mjGEOM_BOX,
        pos=[0.0, -0.041, 0.040],
        size=[0.034, 0.003, 0.027],
        rgba=DARK_PANEL,
    )
    _add_geom(
        tool,
        mujoco,
        name=f"{arm}_tacclaw_camera_housing",
        geom_type=mujoco.mjtGeom.mjGEOM_ELLIPSOID,
        pos=[0.0, -0.064, 0.041],
        size=[0.025, 0.025, 0.022],
        rgba=CAMERA_BLACK,
    )
    _add_geom(
        tool,
        mujoco,
        name=f"{arm}_tacclaw_camera_lens",
        geom_type=mujoco.mjtGeom.mjGEOM_CYLINDER,
        pos=[0.0, -0.088, 0.041],
        euler=[math.pi / 2.0, 0.0, 0.0],
        size=[0.014, 0.003],
        rgba=LENS_BLUE,
    )
    _add_geom(
        tool,
        mujoco,
        name=f"{arm}_tacclaw_rear_connector",
        geom_type=mujoco.mjtGeom.mjGEOM_ELLIPSOID,
        pos=[0.0, 0.064, 0.039],
        size=[0.022, 0.025, 0.020],
        rgba=CAMERA_BLACK,
    )
    _add_geom(
        tool,
        mujoco,
        name=f"{arm}_tacclaw_neck",
        geom_type=mujoco.mjtGeom.mjGEOM_BOX,
        pos=[0.0, 0.0, 0.079],
        size=[0.029, 0.027, 0.014],
        rgba=CHARCOAL,
    )

    # At full stroke, 124.45 mm outer width minus two 24 mm fingers gives
    # about 100 mm clear opening. The fixed preview follows that envelope.
    tip_center_x = 0.012 + 0.0382 * opening
    for sign, side in ((-1.0, "negative"), (1.0, "positive")):
        base = np.asarray([sign * 0.022, 0.0, 0.082])
        middle = np.asarray([sign * (0.024 + 0.45 * tip_center_x), 0.0, 0.132])
        tip = np.asarray([sign * tip_center_x, 0.0, 0.1825])
        inner_shift = np.asarray([-sign * 0.010, -0.001, 0.0])

        _add_geom(
            tool,
            mujoco,
            name=f"{arm}_tacclaw_{side}_finger_lower",
            geom_type=mujoco.mjtGeom.mjGEOM_CAPSULE,
            fromto=[*base, *middle],
            size=[0.015],
            rgba=CHARCOAL,
        )
        _add_geom(
            tool,
            mujoco,
            name=f"{arm}_tacclaw_{side}_finger_upper",
            geom_type=mujoco.mjtGeom.mjGEOM_CAPSULE,
            fromto=[*middle, *tip],
            size=[0.012],
            rgba=CHARCOAL,
        )
        _add_geom(
            tool,
            mujoco,
            name=f"{arm}_tacclaw_{side}_tactile_lower",
            geom_type=mujoco.mjtGeom.mjGEOM_CAPSULE,
            fromto=[*(base + inner_shift), *(middle + inner_shift)],
            size=[0.0055],
            rgba=TACTILE_ORANGE,
        )
        _add_geom(
            tool,
            mujoco,
            name=f"{arm}_tacclaw_{side}_tactile_upper",
            geom_type=mujoco.mjtGeom.mjGEOM_CAPSULE,
            fromto=[*(middle + inner_shift), *(tip + inner_shift)],
            size=[0.005],
            rgba=TACTILE_ORANGE,
        )

    tool.add_site(
        name=f"{arm}_tacclaw_tcp",
        pos=[0.0, 0.0, 0.19448],
        type=mujoco.mjtGeom.mjGEOM_SPHERE,
        size=[0.008, 0.0, 0.0],
        rgba=[0.2, 1.0, 0.35, 0.85],
        group=2,
    )


def _photo_base_transforms(spacing_m: float):
    from nero_wrapper.dual_model import BaseTransform

    half_spacing = spacing_m / 2.0
    return {
        "arm_a": BaseTransform(
            (0.0, -half_spacing, 0.0),
            (math.pi / 2.0, math.pi / 2.0, 0.0),
        ),
        "arm_b": BaseTransform(
            (0.0, half_spacing, 0.0),
            (-math.pi / 2.0, math.pi / 2.0, 0.0),
        ),
    }


def _style_nero_geoms(child) -> None:
    for geom in child.geoms:
        mesh_name = str(geom.meshname)
        for link_name, rgba in ARM_COLORS.items():
            if mesh_name.endswith(link_name):
                geom.rgba = rgba
                break
        geom.group = 1
        geom.contype = 0
        geom.conaffinity = 0


def _build_model(mujoco, urdf_path: Path, *, base_spacing_m: float, opening: float):
    from nero_wrapper.dual_model import (
        HARDWARE_TO_MODEL_JOINT_OFFSETS,
        HARDWARE_TO_MODEL_JOINT_SIGNS,
        build_dual_nero_urdf,
    )

    base_transforms = _photo_base_transforms(base_spacing_m)
    xml = build_dual_nero_urdf(
        urdf_path,
        base_transforms=base_transforms,
        joint_offsets=HARDWARE_TO_MODEL_JOINT_OFFSETS,
        joint_signs=HARDWARE_TO_MODEL_JOINT_SIGNS,
    )
    spec = mujoco.MjSpec.from_string(xml)
    spec.modelname = "nero_tacclaw_photo_assembly"
    spec.compiler.discardvisual = False
    spec.visual.global_.offwidth = 1280
    spec.visual.global_.offheight = 800
    spec.visual.headlight.ambient = [0.32, 0.32, 0.32]
    spec.visual.headlight.diffuse = [0.72, 0.72, 0.72]
    _style_nero_geoms(spec)

    for arm in ("arm_a", "arm_b"):
        link7 = spec.body(f"{arm}_link7")
        if link7 is None:
            raise RuntimeError(f"NERO body is missing: {arm}_link7")
        _add_approximate_tacclaw(mujoco, link7, arm=arm, opening=opening)

    spec.worldbody.add_light(
        name="key",
        type=mujoco.mjtLightType.mjLIGHT_DIRECTIONAL,
        pos=[0.0, -2.0, 3.0],
        dir=[0.0, 0.5, -1.0],
        diffuse=[0.85, 0.85, 0.85],
    )
    spec.worldbody.add_light(
        name="fill",
        type=mujoco.mjtLightType.mjLIGHT_DIRECTIONAL,
        pos=[-2.0, 1.5, 1.0],
        dir=[1.0, -0.5, -0.4],
        diffuse=[0.42, 0.44, 0.48],
    )
    _add_geom(
        spec.worldbody,
        mujoco,
        name="floor",
        geom_type=mujoco.mjtGeom.mjGEOM_PLANE,
        pos=[0.0, 0.0, -1.02],
        size=[2.0, 2.0, 0.05],
        rgba=[0.14, 0.15, 0.17, 1.0],
    )
    for name, endpoint, rgba in (
        ("world_x", [0.30, 0.0, 0.0], [1.0, 0.15, 0.15, 1.0]),
        ("world_y", [0.0, 0.30, 0.0], [0.15, 1.0, 0.15, 1.0]),
        ("world_z", [0.0, 0.0, 0.30], [0.2, 0.4, 1.0, 1.0]),
    ):
        _add_geom(
            spec.worldbody,
            mujoco,
            name=name,
            geom_type=mujoco.mjtGeom.mjGEOM_CYLINDER,
            fromto=[0.0, 0.0, 0.0, *endpoint],
            size=[0.005],
            rgba=rgba,
        )

    return (
        spec.compile(),
        HARDWARE_TO_MODEL_JOINT_OFFSETS,
        HARDWARE_TO_MODEL_JOINT_SIGNS,
    )


def _set_joint_pose(mujoco, model, data, joints, offsets, signs) -> None:
    for arm in ("arm_a", "arm_b"):
        values = np.asarray(offsets[arm], dtype=np.float64) + np.asarray(
            signs[arm], dtype=np.float64
        ) * np.asarray(joints[arm], dtype=np.float64)
        for index, value in enumerate(values, 1):
            joint_name = f"{arm}_joint{index}"
            joint_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, joint_name)
            if joint_id < 0:
                raise RuntimeError(f"MuJoCo joint is missing: {joint_name}")
            data.qpos[model.jnt_qposadr[joint_id]] = value
    mujoco.mj_forward(model, data)


def _camera(
    mujoco,
    *,
    lookat: tuple[float, float, float],
    azimuth: float,
    elevation: float,
    distance: float,
):
    camera = mujoco.MjvCamera()
    camera.type = mujoco.mjtCamera.mjCAMERA_FREE
    camera.lookat[:] = lookat
    camera.azimuth = azimuth
    camera.elevation = elevation
    camera.distance = distance
    return camera


def _render_panel(mujoco, renderer, data, view):
    label, lookat, azimuth, elevation, distance, show_tcp = view
    option = mujoco.MjvOption()
    option.sitegroup[:] = 0
    if show_tcp:
        option.sitegroup[2] = 1
    renderer.update_scene(
        data,
        camera=_camera(
            mujoco,
            lookat=lookat,
            azimuth=azimuth,
            elevation=elevation,
            distance=distance,
        ),
        scene_option=option,
    )
    return label, renderer.render().copy()


def _save_snapshot(
    mujoco,
    model,
    data,
    output: Path,
    *,
    base_spacing_m: float,
    opening: float,
    joints: dict[str, np.ndarray],
) -> None:
    from PIL import Image, ImageDraw, ImageFont

    ik_ready = all(
        np.allclose(joints[arm], IK_READY_JOINTS[arm]) for arm in IK_READY_JOINTS
    )
    if ik_ready:
        views = [
            ("Photo-facing front", (0.25, 0.0, -0.38), 180.0, -3.0, 1.65, False),
            ("Three-quarter assembly", (0.25, 0.0, -0.38), 140.0, -16.0, 1.72, False),
            ("TacClaw close-up", (0.50, 0.0, -0.31), 180.0, -4.0, 0.82, True),
            ("Side envelope", (0.50, 0.0, -0.31), 90.0, -6.0, 1.02, False),
        ]
    else:
        views = [
            ("Photo-facing front", (0.0, 0.0, -0.40), 180.0, -3.0, 1.70, False),
            ("Three-quarter assembly", (0.0, 0.0, -0.40), 140.0, -16.0, 1.78, False),
            ("TacClaw close-up", (0.0, 0.0, -0.80), 180.0, -2.0, 0.78, True),
            ("Side envelope", (0.0, 0.0, -0.74), 90.0, -5.0, 1.15, False),
        ]
    panel_width, panel_height = 800, 560
    renderer = mujoco.Renderer(model, height=panel_height, width=panel_width)
    panels = [_render_panel(mujoco, renderer, data, view) for view in views]
    renderer.close()

    header_height, footer_height = 84, 128
    canvas = Image.new(
        "RGB",
        (panel_width * 2, header_height + panel_height * 2 + footer_height),
        (22, 23, 26),
    )
    draw = ImageDraw.Draw(canvas)
    font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    bold_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    font = ImageFont.truetype(font_path, 25)
    small = ImageFont.truetype(font_path, 20)
    bold = ImageFont.truetype(bold_path, 31)
    draw.text(
        (24, 16),
        "Dual NERO + DM-TacClaw assembly preview",
        fill="white",
        font=bold,
    )
    draw.text(
        (24, 53),
        "Official NERO meshes + manual-dimension TacClaw approximation",
        fill=(215, 215, 218),
        font=small,
    )
    for index, (label, panel_array) in enumerate(panels):
        x = (index % 2) * panel_width
        y = header_height + (index // 2) * panel_height
        canvas.paste(Image.fromarray(panel_array), (x, y))
        draw.rectangle((x + 12, y + 10, x + 330, y + 49), fill=(10, 10, 10))
        draw.text((x + 22, y + 14), label, fill="white", font=font)

    footer_y = header_height + panel_height * 2 + 18
    if all(np.allclose(joints[arm], ZERO_JOINTS[arm]) for arm in ZERO_JOINTS):
        pose_label = "hardware joints: all zero"
    elif all(
        np.allclose(joints[arm], IK_READY_JOINTS[arm]) for arm in IK_READY_JOINTS
    ):
        pose_label = "hardware joints: J4 +90 deg IK-ready"
    elif all(
        np.allclose(joints[arm], CAPTURED_JOINTS[arm]) for arm in CAPTURED_JOINTS
    ):
        pose_label = "hardware joints: 2026-08-11 capture"
    else:
        pose_label = "hardware joints: custom"
    draw.text(
        (24, footer_y),
        (
            f"{pose_label} | Base spacing: {base_spacing_m * 1000:.0f} mm | "
            f"TacClaw opening: {opening * 100:.0f}% of 100 mm stroke"
        ),
        fill=(255, 212, 110),
        font=font,
    )
    draw.text(
        (24, footer_y + 42),
        "TacClaw: 194.48 mm long, 124.45 mm max width, 177.01 mm side envelope.",
        fill=(210, 210, 214),
        font=small,
    )
    draw.text(
        (24, footer_y + 74),
        "Approximate visualization only; not CAD-validated collision geometry.",
        fill=(255, 145, 105),
        font=small,
    )

    output = output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output)
    print(f"Saved NERO + TacClaw assembly preview: {output}")


def _interactive(mujoco, model, data) -> None:
    import mujoco.viewer

    print("Approximate DM-TacClaw geometry; green spheres mark nominal fingertip TCPs")
    with mujoco.viewer.launch_passive(model, data) as viewer:
        viewer.cam.lookat[:] = [0.0, 0.0, -0.42]
        viewer.cam.azimuth = 145.0
        viewer.cam.elevation = -14.0
        viewer.cam.distance = 1.75
        while viewer.is_running():
            mujoco.mj_forward(model, data)
            viewer.sync()
            time.sleep(0.02)


def main() -> None:
    args = _arguments()
    os.environ.setdefault("MUJOCO_GL", "glfw" if args.interactive else "egl")
    import mujoco

    joints = {"arm_a": args.arm_a.copy(), "arm_b": args.arm_b.copy()}
    model, offsets, signs = _build_model(
        mujoco,
        args.urdf,
        base_spacing_m=args.base_spacing_m,
        opening=args.gripper_opening,
    )
    data = mujoco.MjData(model)
    _set_joint_pose(mujoco, model, data, joints, offsets, signs)
    if args.interactive:
        try:
            _interactive(mujoco, model, data)
        except KeyboardInterrupt:
            pass
    else:
        _save_snapshot(
            mujoco,
            model,
            data,
            args.output,
            base_spacing_m=args.base_spacing_m,
            opening=args.gripper_opening,
            joints=joints,
        )


if __name__ == "__main__":
    main()
