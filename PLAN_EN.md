# NERO Dual-Arm Dual-Hand Workflow Plan

This is the English delivery workflow. It compresses the S0-S15 route and locks the defaults needed for project handoff, revalidation, and continued work.

## Current State

- Hardware: two NERO 7-DOF arms with two installed LinkerHand L6 dexterous hands.
- Topology: Arm A = right hand = `/arm_a` + `can_arm_a` + hand `can2`; Arm B = left hand = `/arm_b` + `can_arm_b` + hand `can1`.
- Architecture: arms use ROS2 `agx_arm_ros`; hands use LinkerHand SDK wrappers.
- Completed: S10 dual-arm low-speed motion, S11 `lab_world` baseline, S12 control isolation, S13 low-risk dual-arm primitive, S14 low-risk dual-hand bring-up, S15 elbow-curl/fist demo.
- Next gate: run zero-return revalidation with `ros_s15_return_to_initial.py` default `--pose zero`, record evidence, then close S15.

## Phase Flow

| Phase | State | Delivery output |
| --- | --- | --- |
| S0 Data baseline | Complete | Manuals, CAN protocol, CAD/STEP, and key images archived under `docs/assets/` and `docs/evidence/` |
| S1 Safety/site | Complete for planning | Site, power, mounting, emergency stop path, and operator boundary recorded |
| S2 Host environment | Complete | Ubuntu 20.04 host SDK/CAN-only + Docker ROS2 Humble |
| S3 Offline model | Complete | NERO URDF/xacro/RViz checks passed |
| S4-S5 Power/Web | Complete | Dual-arm Web checks, identities, versions, and status passed |
| S6-S8 CAN/SDK/ROS read-only | Complete | Dual CAN, SDK read-state, ROS feedback/RViz follow passed |
| S9 Calibration/config | Complete | Installation pose, load, TCP, and snapshots recorded |
| S10 First low-speed motion | Complete | A/B Web, SDK, and ROS single-joint low-speed motion passed |
| S11 Dual-arm baseline | Complete | `lab_world`, static TF, accepted RViz screenshot, post-TF snapshot |
| S12 Control isolation | Complete | A/B active arm with passive monitor arm passed |
| S13 Dual-arm low-risk primitive | Complete | Dual active/hold and non-contact joint-space synchronization passed |
| S14 End effectors | Complete | Dual LinkerHand L6 health/open/index micro/dual gates passed |
| S15 Arm-hand coordination | Accepted by operator report | Elbow-curl/fist demo ran through; zero-return closure pending |

## Fixed Work Cycle

Every step follows this loop:

1. Read `docs/status/current_bringup_status.md` and the relevant `docs/phases/` document.
2. State the phase and why the action is allowed.
3. Run dry-run first, then execute.
4. Verify with ROS topics, CAN state, RViz, script output, or operator report.
5. Update `docs/status/deployment_log.md`.
6. If phase state, device mapping, safety boundaries, or acceptance changed, update `docs/status/current_bringup_status.md`, `config/nero.env`, and the relevant phase document.

## S15 Standard Revalidation Flow

1. Environment and control-source audit:

```bash
source config/nero.env
bash scripts/check_environment.sh
bash scripts/s10_control_source_audit.sh
```

2. Prepare the four CAN interfaces:

```bash
bash scripts/activate_can.sh can_arm_a 1000000 "1-3.4.1:1.0"
bash scripts/activate_can.sh can_arm_b 1000000 "1-3.4.3:1.0"
bash scripts/activate_can.sh can1 1000000 "1-3.4.4:1.0"
bash scripts/activate_can.sh can2 1000000 "1-3.4.2:1.0"
```

3. Start readonly observe:

```bash
NERO_CONTAINER_NAME=nero-humble-s15-observe \
  bash scripts/run_humble_container.sh --allow-xhost \
    bash /workspace/nero/scripts/launch_s15_dual_arm_hand_observe.sh --readonly
```

4. Run zero-return dry-run:

```bash
NERO_CONTAINER_NAME=nero-humble-s15-init \
  bash scripts/run_humble_container.sh \
    python3 /workspace/nero/scripts/ros_s15_return_to_initial.py
```

5. After RViz, clearance, and active-driver confirmation, restart active observe:

```bash
NERO_CONTAINER_NAME=nero-humble-s15-observe \
  bash scripts/run_humble_container.sh --allow-xhost \
    bash /workspace/nero/scripts/launch_s15_dual_arm_hand_observe.sh --active
```

6. Execute zero-return:

```bash
NERO_CONTAINER_NAME=nero-humble-s15-init \
  bash scripts/run_humble_container.sh \
    python3 /workspace/nero/scripts/ros_s15_return_to_initial.py \
      --execute \
      --allow-wide-motion \
      --confirm-clearance \
      --confirm-rviz-visible
```

7. To reproduce the accepted S15 demo, use the accepted parameters. Dry-run first:

```bash
NERO_CONTAINER_NAME=nero-humble-s15-elbow-demo \
  bash scripts/run_humble_container.sh \
    python3 /workspace/nero/scripts/ros_s15_elbow_curl_demo.py \
      --side both \
      --left-j1-delta-deg -10 \
      --right-j1-delta-deg -20 \
      --left-j4-delta-deg 15 \
      --right-j4-delta-deg 15 \
      --arm-profile single-target \
      --hand-timing during-curl \
      --hand-close-fraction 0.5
```

The execute version must add `--execute --allow-wide-motion --confirm-clearance --confirm-rviz-visible`. Full fist or larger motions require a separate gate.

## Troubleshooting Rules

- After USB/CAN or power reconnect, wait about 20 seconds before judging CAN/ROS feedback.
- If an arm interface is UP but `candump` or the ROS driver has no response, check cable seating and power first, then reactivate CAN.
- If `/arm_a/feedback/joint_states` or `/arm_b/feedback/joint_states` is about 400 Hz, check for duplicate ROS publishers first.
- If RViz does not match the physical posture, run:

```bash
NERO_CONTAINER_NAME=nero-humble-s15-diagnostics \
  bash scripts/run_humble_container.sh \
    bash /workspace/nero/scripts/s15_rviz_pose_diagnostics.sh
```

- `docs/evidence/ros_snapshots` is the ROS read-only snapshot archive. The snapshot script writes to this path.

## Follow-Up Plan

- Close S15 with zero-return revalidation, post-motion snapshot, logs, and status updates.
- Add a ROS2 hand service/action wrapper around the LinkerHand SDK.
- Add one unified arm/hand timeline logger.
- Before any grasping, contact, handoff, or close-proximity dual-arm manipulation, create a separate safety gate, collision-space review, and rollback script.

## Acceptance Checks

- `python -m pip install -e '.[dev]'`
- `ruff check src tests examples/nero_read_state.py`
- `pytest`
- `python -m compileall -q src examples scripts`
- `bash -n config/nero.env setup.sh scripts/*.sh docker/humble/entrypoint.sh`
- `bash scripts/check_environment.sh`
- Use `rg 'docs/' README.md README_EN.md PLAN.md PLAN_EN.md CONTRIBUTING.md config scripts docs --glob '!docs/vendor/**'` to spot-check paths.
- `git status --short` should only show expected directory moves, document additions/updates, and cleanup of accidental files.
