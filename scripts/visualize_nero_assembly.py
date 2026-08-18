#!/usr/bin/env python3
"""Compare nominal, passive-gravity and configured NERO poses in MuJoCo.

Green geometry uses the raw driver joint angles in the vendor's nominal FK.
Cyan geometry lets the same URDF settle passively under gravity. Transparent
red geometry uses the current model offsets from ``nero_wrapper.dual_model``. All
three copies share the same configured bench base frames.
"""

from __future__ import annotations

import argparse
import os
import time
from pathlib import Path

import numpy as np

WORKSPACE = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = WORKSPACE / "previews" / "nero_assembly_mujoco.png"

# Read-only feedback captured on 2026-08-11 while diagnosing the Cartesian
# retargeter.  Override these with --arm-a/--arm-b after capturing a newer pose.
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

ZERO_OFFSETS = {"arm_a": (0.0,) * 7, "arm_b": (0.0,) * 7}
IDENTITY_SIGNS = {"arm_a": (1.0,) * 7, "arm_b": (1.0,) * 7}


def _joint_vector(value: str) -> np.ndarray:
    try:
        result = np.asarray(
            [float(item) for item in value.split(",")], dtype=np.float64
        )
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "joint values must be comma-separated numbers"
        ) from exc
    if result.shape != (7,) or not np.all(np.isfinite(result)):
        raise argparse.ArgumentTypeError("exactly seven finite joint values are required")
    return result


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Overlay the nominal raw-driver FK (green), a passive gravity "
            "settle (cyan), and the current cuRobo offset model (red)."
        )
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="open the interactive MuJoCo viewer instead of saving a comparison image",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"snapshot path (default: {DEFAULT_OUTPUT})",
    )
    parser.add_argument(
        "--arm-a",
        type=_joint_vector,
        default=CAPTURED_JOINTS["arm_a"],
        metavar="J1,J2,J3,J4,J5,J6,J7",
        help="raw arm_a feedback in radians",
    )
    parser.add_argument(
        "--arm-b",
        type=_joint_vector,
        default=CAPTURED_JOINTS["arm_b"],
        metavar="J1,J2,J3,J4,J5,J6,J7",
        help="raw arm_b feedback in radians",
    )
    parser.add_argument(
        "--gravity-seconds",
        type=float,
        default=15.0,
        help="passive settling time for the cyan model (default: 15 seconds)",
    )
    parser.add_argument(
        "--gravity-damping",
        type=float,
        default=2.0,
        help="passive joint damping in N*m*s/rad (default: 2.0)",
    )
    parser.add_argument(
        "--gravity-friction",
        type=float,
        default=0.2,
        help="passive joint friction loss in N*m (default: 0.2)",
    )
    parser.add_argument(
        "--urdf",
        required=True,
        type=Path,
        help="path to the official single-arm NERO URDF",
    )
    args = parser.parse_args()
    if (
        args.gravity_seconds < 0.0
        or args.gravity_damping < 0.0
        or args.gravity_friction < 0.0
    ):
        parser.error("gravity settling parameters must be non-negative")
    return args


def _child_spec(
    mujoco,
    build_dual_nero_urdf,
    urdf_path,
    base_transforms,
    offsets,
    signs,
    rgba,
    group,
):
    xml = build_dual_nero_urdf(
        urdf_path,
        base_transforms=base_transforms,
        joint_offsets=offsets,
        joint_signs=signs,
    )
    child = mujoco.MjSpec.from_string(xml)
    for geom in child.geoms:
        geom.rgba = rgba
        geom.group = group
        geom.contype = 0
        geom.conaffinity = 0
    for arm in ("arm_a", "arm_b"):
        child.body(f"{arm}_link7").add_site(
            name=f"{arm}_tcp_marker",
            type=mujoco.mjtGeom.mjGEOM_SPHERE,
            size=[0.028, 0.0, 0.0],
            rgba=rgba,
            group=group,
        )
    return child


def _build_comparison_model(mujoco, urdf_path: Path):
    from nero_wrapper.dual_model import (
        HARDWARE_TO_MODEL_JOINT_OFFSETS,
        HARDWARE_TO_MODEL_JOINT_SIGNS,
        LAB_DUAL_BENCH_BASE_TRANSFORMS,
        build_dual_nero_urdf,
    )

    master = mujoco.MjSpec.from_string(
        """
        <mujoco model="nero_assembly_comparison">
          <compiler angle="radian"/>
          <option gravity="0 0 0"/>
          <visual>
            <global offwidth="1280" offheight="800"/>
            <headlight ambient="0.35 0.35 0.35" diffuse="0.8 0.8 0.8"/>
          </visual>
          <worldbody>
            <light name="key" directional="true" pos="0 -2 3" dir="0 0.5 -1"/>
            <geom name="floor" type="plane" pos="0 0 -0.82" size="2 2 0.05"
                  rgba="0.16 0.17 0.19 1" group="0" contype="0" conaffinity="0"/>
            <geom name="world_x" type="cylinder" fromto="0 0 0 0.30 0 0"
                  size="0.006" rgba="1 0.15 0.15 1" group="0"/>
            <geom name="world_y" type="cylinder" fromto="0 0 0 0 0.30 0"
                  size="0.006" rgba="0.15 1 0.15 1" group="0"/>
            <geom name="world_z" type="cylinder" fromto="0 0 0 0 0 0.30"
                  size="0.006" rgba="0.2 0.4 1 1" group="0"/>
          </worldbody>
        </mujoco>
        """
    )

    raw = _child_spec(
        mujoco,
        build_dual_nero_urdf,
        urdf_path,
        LAB_DUAL_BENCH_BASE_TRANSFORMS,
        ZERO_OFFSETS,
        IDENTITY_SIGNS,
        [0.10, 0.90, 0.25, 0.92],
        1,
    )
    configured = _child_spec(
        mujoco,
        build_dual_nero_urdf,
        urdf_path,
        LAB_DUAL_BENCH_BASE_TRANSFORMS,
        HARDWARE_TO_MODEL_JOINT_OFFSETS,
        HARDWARE_TO_MODEL_JOINT_SIGNS,
        [1.00, 0.10, 0.12, 0.34],
        2,
    )
    gravity = _child_spec(
        mujoco,
        build_dual_nero_urdf,
        urdf_path,
        LAB_DUAL_BENCH_BASE_TRANSFORMS,
        ZERO_OFFSETS,
        IDENTITY_SIGNS,
        [0.10, 0.62, 1.00, 0.82],
        3,
    )
    raw_frame = master.worldbody.add_frame(name="raw_driver_frame")
    configured_frame = master.worldbody.add_frame(name="configured_offset_frame")
    gravity_frame = master.worldbody.add_frame(name="passive_gravity_frame")
    master.attach(raw, prefix="raw_", frame=raw_frame)
    master.attach(configured, prefix="configured_", frame=configured_frame)
    master.attach(gravity, prefix="gravity_", frame=gravity_frame)
    return (
        master.compile(),
        HARDWARE_TO_MODEL_JOINT_OFFSETS,
        HARDWARE_TO_MODEL_JOINT_SIGNS,
    )


def _set_joint_pose(mujoco, model, data, joints, offsets, signs) -> None:
    assemblies = (
        ("raw_", ZERO_OFFSETS, IDENTITY_SIGNS),
        ("configured_", offsets, signs),
        ("gravity_", ZERO_OFFSETS, IDENTITY_SIGNS),
    )
    for prefix, applied_offsets, applied_signs in assemblies:
        for arm in ("arm_a", "arm_b"):
            values = np.asarray(applied_offsets[arm], dtype=np.float64) + np.asarray(
                applied_signs[arm], dtype=np.float64
            ) * joints[arm]
            for index, value in enumerate(values, 1):
                joint_name = f"{prefix}{arm}_joint{index}"
                joint_id = mujoco.mj_name2id(
                    model, mujoco.mjtObj.mjOBJ_JOINT, joint_name
                )
                if joint_id < 0:
                    raise RuntimeError(f"MuJoCo joint is missing: {joint_name}")
                data.qpos[model.jnt_qposadr[joint_id]] = value
    mujoco.mj_forward(model, data)


def _joint_addresses(mujoco, model, prefix: str) -> tuple[np.ndarray, np.ndarray]:
    qpos_addresses = []
    dof_addresses = []
    for arm in ("arm_a", "arm_b"):
        for index in range(1, 8):
            joint_id = mujoco.mj_name2id(
                model,
                mujoco.mjtObj.mjOBJ_JOINT,
                f"{prefix}{arm}_joint{index}",
            )
            qpos_addresses.append(int(model.jnt_qposadr[joint_id]))
            dof_addresses.append(int(model.jnt_dofadr[joint_id]))
    return np.asarray(qpos_addresses), np.asarray(dof_addresses)


def _settle_passive_gravity(
    mujoco,
    model,
    data,
    *,
    seconds: float,
    damping: float,
    friction: float,
) -> None:
    """Settle only the cyan copy while keeping nominal and configured FK fixed."""
    if seconds <= 0.0:
        return
    fixed_qpos = []
    fixed_dofs = []
    for prefix in ("raw_", "configured_"):
        qpos_addresses, dof_addresses = _joint_addresses(mujoco, model, prefix)
        fixed_qpos.extend(qpos_addresses.tolist())
        fixed_dofs.extend(dof_addresses.tolist())
    fixed_qpos_array = np.asarray(fixed_qpos)
    fixed_dof_array = np.asarray(fixed_dofs)
    fixed_values = data.qpos[fixed_qpos_array].copy()

    _, gravity_dofs = _joint_addresses(mujoco, model, "gravity_")
    model.dof_damping[gravity_dofs] = damping
    model.dof_frictionloss[gravity_dofs] = friction
    model.opt.gravity[:] = [0.0, 0.0, -9.81]
    model.opt.timestep = 0.002
    for _ in range(int(round(seconds / model.opt.timestep))):
        data.qpos[fixed_qpos_array] = fixed_values
        data.qvel[fixed_dof_array] = 0.0
        mujoco.mj_step(model, data)

    data.qpos[fixed_qpos_array] = fixed_values
    data.qvel[:] = 0.0
    model.opt.gravity[:] = [0.0, 0.0, 0.0]
    mujoco.mj_forward(model, data)


def _tcp_positions(mujoco, model, data):
    result = {}
    for prefix in ("raw_", "gravity_", "configured_"):
        result[prefix] = {}
        for arm in ("arm_a", "arm_b"):
            site_id = mujoco.mj_name2id(
                model,
                mujoco.mjtObj.mjOBJ_SITE,
                f"{prefix}{arm}_tcp_marker",
            )
            result[prefix][arm] = data.site_xpos[site_id].copy()
    return result


def _camera(mujoco, *, azimuth: float, elevation: float, distance: float):
    camera = mujoco.MjvCamera()
    camera.type = mujoco.mjtCamera.mjCAMERA_FREE
    camera.lookat[:] = [0.13, 0.0, -0.25]
    camera.azimuth = azimuth
    camera.elevation = elevation
    camera.distance = distance
    return camera


def _save_snapshot(mujoco, model, data, output: Path) -> None:
    from PIL import Image, ImageDraw, ImageFont

    views = [
        ("All three (overlay)", 135.0, -22.0, 2.05, (1, 2, 3)),
        ("Nominal FK (no gravity)", 90.0, -5.0, 1.95, (1,)),
        ("Passive gravity settle", 90.0, -5.0, 1.95, (3,)),
        ("Current cuRobo offsets", 90.0, -5.0, 1.95, (2,)),
    ]
    panel_width, panel_height = 800, 520
    renderer = mujoco.Renderer(model, height=panel_height, width=panel_width)
    panels = []
    for label, azimuth, elevation, distance, visible_groups in views:
        option = mujoco.MjvOption()
        option.geomgroup[:] = 0
        option.sitegroup[:] = 0
        option.geomgroup[0] = 1
        for group in visible_groups:
            option.geomgroup[group] = 1
            option.sitegroup[group] = 1
        renderer.update_scene(
            data,
            camera=_camera(
                mujoco,
                azimuth=azimuth,
                elevation=elevation,
                distance=distance,
            ),
            scene_option=option,
        )
        image = Image.fromarray(renderer.render())
        panels.append((label, image))
    renderer.close()

    header_height, footer_height = 82, 154
    canvas = Image.new(
        "RGB",
        (panel_width * 2, header_height + panel_height * 2 + footer_height),
        (22, 23, 26),
    )
    draw = ImageDraw.Draw(canvas)
    font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    bold_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    font = ImageFont.truetype(font_path, 25)
    small = ImageFont.truetype(font_path, 21)
    bold = ImageFont.truetype(bold_path, 31)
    draw.text(
        (24, 18),
        "NERO assembly: nominal FK vs passive gravity vs current cuRobo model",
        fill="white",
        font=bold,
    )
    draw.text(
        (24, 54),
        "GREEN = nominal/no gravity   CYAN = passive gravity   RED = current offsets",
        fill=(220, 220, 220),
        font=small,
    )
    for index, (label, image) in enumerate(panels):
        x = (index % 2) * panel_width
        y = header_height + (index // 2) * panel_height
        canvas.paste(image, (x, y))
        draw.rectangle((x + 12, y + 10, x + 335, y + 47), fill=(10, 10, 10))
        draw.text((x + 22, y + 14), label, fill="white", font=font)

    positions = _tcp_positions(mujoco, model, data)
    nominal_gaps = {
        arm: float(
            np.linalg.norm(
                positions["raw_"][arm] - positions["configured_"][arm]
            )
        )
        for arm in ("arm_a", "arm_b")
    }
    gravity_gaps = {
        arm: float(
            np.linalg.norm(
                positions["gravity_"][arm] - positions["configured_"][arm]
            )
        )
        for arm in ("arm_a", "arm_b")
    }
    footer_y = header_height + panel_height * 2 + 20
    draw.text(
        (24, footer_y),
        (
            "Nominal -> configured TCP gap: "
            f"arm_a {nominal_gaps['arm_a']:.3f} m | "
            f"arm_b {nominal_gaps['arm_b']:.3f} m"
        ),
        fill=(255, 220, 120),
        font=font,
    )
    draw.text(
        (24, footer_y + 42),
        (
            "Gravity -> configured TCP gap: "
            f"arm_a {gravity_gaps['arm_a']:.3f} m | "
            f"arm_b {gravity_gaps['arm_b']:.3f} m"
        ),
        fill=(120, 210, 255),
        font=font,
    )
    draw.text(
        (24, footer_y + 84),
        "World axes: X red, Y green, Z blue. Viewer groups: 1 nominal, 2 configured, 3 gravity.",
        fill=(210, 210, 210),
        font=small,
    )
    output = output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output)
    print(f"Saved MuJoCo comparison: {output}")
    print(
        "Nominal -> configured TCP gap: "
        f"arm_a={nominal_gaps['arm_a']:.6f}m "
        f"arm_b={nominal_gaps['arm_b']:.6f}m"
    )
    print(
        "Gravity -> configured TCP gap: "
        f"arm_a={gravity_gaps['arm_a']:.6f}m "
        f"arm_b={gravity_gaps['arm_b']:.6f}m"
    )


def _interactive(mujoco, model, data) -> None:
    import mujoco.viewer

    print(
        "MuJoCo geom groups: 1 = nominal green, 2 = configured red, "
        "3 = passive gravity cyan"
    )
    with mujoco.viewer.launch_passive(model, data) as viewer:
        viewer.cam.lookat[:] = [0.13, 0.0, -0.25]
        viewer.cam.azimuth = 135.0
        viewer.cam.elevation = -22.0
        viewer.cam.distance = 2.05
        while viewer.is_running():
            mujoco.mj_forward(model, data)
            viewer.sync()
            time.sleep(0.02)


def main() -> None:
    args = _arguments()
    os.environ.setdefault("MUJOCO_GL", "glfw" if args.interactive else "egl")
    import mujoco

    joints = {"arm_a": args.arm_a.copy(), "arm_b": args.arm_b.copy()}
    model, offsets, signs = _build_comparison_model(mujoco, args.urdf)
    data = mujoco.MjData(model)
    _set_joint_pose(mujoco, model, data, joints, offsets, signs)
    _settle_passive_gravity(
        mujoco,
        model,
        data,
        seconds=args.gravity_seconds,
        damping=args.gravity_damping,
        friction=args.gravity_friction,
    )
    if args.interactive:
        try:
            _interactive(mujoco, model, data)
        except KeyboardInterrupt:
            pass
    else:
        _save_snapshot(mujoco, model, data, args.output)


if __name__ == "__main__":
    main()
