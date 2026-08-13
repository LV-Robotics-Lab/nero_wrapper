# nero_wrapper

The base package remains configuration-first and does not import ROS or open
hardware automatically. Optional field adapters live under
`nero_wrapper.ros2`; they run only through their explicit console entry points.
The optional cuRobo source is pinned as `submodules/curobo`; initialize it only
on CUDA hosts that need the cuRobo backend.

A safe Python wrapper and field-operations repository for two AgileX NERO 7-DOF arms with two LinkerHand L6 hands. It adds typed ROS-independent configuration, read-only state access, host/CAN diagnostics, and reusable safety gates. Field-accepted ROS2 and motion entry points remain under `scripts/` so the refactor does not silently change their real-robot behavior.

The package API intentionally exposes no motion method. Real motion must continue through accepted scripts with dry-run, emergency-stop, clearance, exclusive-control, and visible-feedback gates.

Chinese entry: [README.md](README.md)  
Full workflow: [PLAN.md](PLAN.md) / [PLAN_EN.md](PLAN_EN.md)

## Important Documents

- [Contributing and real-robot safety](CONTRIBUTING.md): Code boundaries, validation, and hardware gates.
- [Documentation map](docs/README.md): Boundary between current guidance and historical evidence.
- [Current Bring-Up Status](docs/status/current_bringup_status.md): Current configuration, accepted results, and next step.
- [Deployment Log](docs/status/deployment_log.md): Actual commands, evidence, decisions, risks, and next actions.
- [Bring-Up Checklist](docs/status/bringup_checklist.md): Field checklist for revalidation.
- [Setup Framework](docs/status/setup_framework.md): Engineering layers, hardware facts, and defaults.
- [Deployment Route](docs/phases/机器人部署与调试行动路线.md): Archived phase route and detailed notes.

## Repository Layout

```text
.
├── src/nero_wrapper/       # Installable, ROS-independent read-only wrapper
├── tests/                  # Config, SDK lifecycle, doctor, and safety tests
├── config/                 # Non-secret defaults and local configuration template
├── docker/                 # ROS2 Humble container
├── examples/               # Package compatibility entry points
├── rviz/                   # RViz configuration
├── scripts/                # Accepted field scripts and historical development entry points
├── docs/
│   ├── status/             # Current status, logs, checklist, framework
│   ├── phases/             # Archived phase plans, designs, procedures
│   ├── results/            # Accepted results, audits, diagnostics
│   ├── evidence/           # Image evidence and ROS snapshots
│   ├── assets/             # Manuals, protocol sheets, CAD/STEP/STL
│   └── upstream/           # Upstream analysis and reviews
└── upstream/               # Ignored local upstream source cache
```

## Install And Run Read-Only Checks

```bash
./setup.sh
source .venv/bin/activate
source config/nero.env

nero-config
nero-doctor --skip-can
nero-read-state --arm arm_a
```

`nero-read-state` prints configuration without connecting by default. Add `--connect` only after SocketCAN is active and the vendor `pyAgxArm` SDK is installed; the command still never enables or moves the arm. Copy `config/nero.local.env.example` to the gitignored `config/nero.local.env` for workstation-only settings.

## Fixed Control Architecture

| Device | Interface | Control path |
| --- | --- | --- |
| Arm A / right side | `can_arm_a`, USB `1-3.4.1:1.0`, ROS `/arm_a` | ROS2 `agx_arm_ros` |
| Arm B / left side | `can_arm_b`, USB `1-3.4.3:1.0`, ROS `/arm_b` | ROS2 `agx_arm_ros` |
| Left hand | `can1`, USB `1-3.4.4:1.0` | LinkerHand SDK wrapper |
| Right hand | `can2`, USB `1-3.4.2:1.0` | LinkerHand SDK wrapper |

Do not run arm SDK motion while the ROS arm driver is active. Do not run LinkerHand GUI/demo/gesture scripts while the project hand wrappers are active.

## Getting Started

Goal: a new operator can start from power-on and run the dual-arm dual-hand elbow-curl/fist demo. Use two terminals: Terminal 1 keeps the ROS driver and RViz running; Terminal 2 sends the demo command.

### 1. Power On And Site Check

1. Confirm both arm bases are fixed, the workspace is clear, and no cable can be pulled by J6/J7 or the hands.
2. Confirm the emergency stop or power cutoff path is immediately reachable.
3. Connect the aviation connector and power. Align the red dots on the aviation connector and seat the XT30 keyed connectors fully.
4. Power both arms and both hands.
5. Check each arm base status light: green or flashing green can continue; red means an abnormal state, so check the Web home page first and do not continue.
6. Let the hardware settle before judging CAN or ROS state.

### 2. Enable Each Arm In Web Control

The host's built-in Wi-Fi can connect to only one arm hotspot at a time, so do Arm A and Arm B one by one. The default Web address is `http://192.168.31.1/`. Obtain credentials from the lab credential store and keep them only in `config/nero.local.env`; never commit them.

1. Connect Wi-Fi `agx-7ax-armA`, then open `http://192.168.31.1/`.
2. Confirm the home page shows no red fault. If there is a fault, record and resolve it first.
3. Click the top-right `web模式` / Web control button.
4. Click `使能` / Enable and enable all joints.
5. Disconnect Arm A Wi-Fi and connect Wi-Fi `agx-7ax-armB`.
6. Repeat steps 2-4 to enable all joints on Arm B.
7. Return to the host terminal. Real-time dual-arm control uses USB-CAN, so both Wi-Fi hotspots do not need to stay connected at the same time.

### 3. Bind The Four CAN Interfaces

Run from the repository root:

```bash
source config/nero.env
bash scripts/check_environment.sh

bash scripts/activate_can.sh can_arm_a 1000000 "1-3.4.1:1.0"
bash scripts/activate_can.sh can_arm_b 1000000 "1-3.4.3:1.0"
bash scripts/activate_can.sh can1 1000000 "1-3.4.4:1.0"
bash scripts/activate_can.sh can2 1000000 "1-3.4.2:1.0"

ip -details link show can_arm_a
ip -details link show can_arm_b
ip -details link show can1
ip -details link show can2
```

All four interfaces should be `UP` with bitrate `1000000`. If USB-CAN, power, or the arm was just reconnected, wait 20 seconds:

```bash
sleep 20
```

### 4. Terminal 1: Start Driver And RViz

Keep this terminal running. It starts the dual-arm ROS driver, static frames, RViz, and observation chain.

```bash
NERO_CONTAINER_NAME=nero-dual-arm-hand-observe \
  bash scripts/run_humble_container.sh --allow-xhost \
    bash /workspace/nero/scripts/launch_dual_arm_hand_observe.sh --active
```

In RViz, confirm both arms match the physical setup. If RViz shows a horizontal zero pose or does not match the real robot, stop before motion and run:

```bash
NERO_CONTAINER_NAME=nero-rviz-diagnostics \
  bash scripts/run_humble_container.sh \
    bash /workspace/nero/scripts/rviz_pose_diagnostics.sh
```

### 5. Terminal 2: Run The Dual-Arm Dual-Hand Demo

After confirming clearance, RViz visibility, and hand cable safety, run in a second terminal:

```bash
NERO_CONTAINER_NAME=nero-dual-arm-hand-demo \
  bash scripts/run_humble_container.sh \
    python3 /workspace/nero/scripts/dual_arm_hand_elbow_curl_demo.py \
      --side both \
      --left-j1-delta-deg -10 \
      --right-j1-delta-deg -20 \
      --left-j4-delta-deg 15 \
      --right-j4-delta-deg 15 \
      --arm-profile single-target \
      --hand-timing during-curl \
      --hand-close-fraction 0.5 \
      --execute \
      --allow-wide-motion \
      --confirm-clearance \
      --confirm-rviz-visible
```

After the demo, return to the initial posture if needed:

```bash
NERO_CONTAINER_NAME=nero-return-initial \
  bash scripts/run_humble_container.sh \
    python3 /workspace/nero/scripts/return_to_initial.py \
      --execute \
      --allow-wide-motion \
      --confirm-clearance \
      --confirm-rviz-visible
```

Press `Ctrl-C` in Terminal 1 to stop the driver/RViz session when finished.

### Note: Dry-Run

If the site, cables, posture, or operator changed, or the current state is uncertain, run a dry-run first. Remove `--execute --allow-wide-motion --confirm-clearance --confirm-rviz-visible` from the Terminal 2 command; dry-run sends no motion commands.

## Hard Safety Boundaries

- Do not continue if the Web page shows a red light or abnormal status.
- External supply must not exceed 25V and must provide at least 10A. The end XT30 2+2 interface is 24V, 2A MAX.
- The RViz visual anchor is for observation only. It must not be used for control, planning, limits, calibration, or semantic acceptance.
- Any new control path, larger motion, contact task, MoveIt execute, Cartesian motion, raw CAN motion, MIT control, zero calibration, firmware upgrade, or collision-level change requires a separate plan and gate.
- If `/arm_a/feedback/joint_states` or `/arm_b/feedback/joint_states` is near 400 Hz, check for duplicate ROS publishers first.

## Recreating Upstream Evidence

```bash
mkdir -p upstream

git clone https://github.com/agilexrobotics/agx_arm_ros.git upstream/agx_arm_ros
git -C upstream/agx_arm_ros checkout c73d33f2ab377447261423f1b881bd89c6663627

git clone https://github.com/agilexrobotics/pyAgxArm.git upstream/pyAgxArm
git -C upstream/pyAgxArm checkout a226840db0c3d5c5dc7f3ec78d6cef1a6800f9e6

git clone https://github.com/agilexrobotics/piper_ros.git upstream/piper_ros
git -C upstream/piper_ros checkout 2dc30fca68cbf4e04d1d0bc15c123d026380ece7
```

LinkerHand SDK is user-provided or requires private repository access:

```bash
git clone https://github.com/LV-Robotics-Lab/linkerhand_sdk upstream/linkerhand_sdk
```
