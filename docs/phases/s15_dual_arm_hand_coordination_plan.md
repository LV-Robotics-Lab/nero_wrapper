# S15 Dual Arm + Dual Hand Coordination Plan

Date: 2026-06-30

Last updated: 2026-07-02

## Decision

Use a hybrid control architecture for the next stage:

- NERO arms: ROS2 through the existing `agx_arm_ros` driver and the accepted
  `/arm_a` and `/arm_b` namespaces.
- LinkerHand L6 hands: the validated local `upstream/linkerhand_wrapper` path through
  project safety wrappers on `can1` and `can2`.

Do not switch the arms back to SDK-only as the primary path for dual-arm
manipulation experiments. Keep arm SDK as a diagnostic/fallback path.

## Why Arms Should Use ROS Next

ROS is the better primary route for the arms because:

- The project has already accepted dual-arm ROS read-only and motion gates from
  S8 through S13.
- The arms already have stable namespaces:
  `/arm_a/...` and `/arm_b/...`.
- ROS gives the manipulation stack access to joint states, arm status, TCP pose,
  TF, RViz, and eventually MoveIt/planning integration.
- The S11 `lab_world` frame and dual-arm RViz alignment are ROS assets; using
  SDK-only arm control would bypass that context.
- ROS topic logging and snapshot scripts are already part of the project
  evidence chain.
- Dual-arm experiments need state visibility and coordination more than the
  lowest-level CAN access.

Arm SDK remains useful for:

- low-level diagnostics;
- reproducing simple single-arm checks outside ROS;
- emergency/fallback comparisons if ROS behavior is unclear.

## Why Hands Should Stay SDK For Now

The LinkerHand SDK is the better route for the hands because:

- Direct hand control through `can1` and `can2` is already validated.
- The local tuned SDK repo provides correct left/right IDs, side-specific open
  presets, and L6 joint order.
- The earlier ROS/Revo2 hand path did not produce usable hand feedback or motion
  for these LinkerHand L6 hands.
- The hand CAN interfaces are separate from the arm CAN interfaces, so SDK hand
  control does not contend with ROS arm control.

Longer-term, wrap the hand SDK as a ROS2 node or service so future algorithms
can call one ROS interface for both arms and hands. That is a software
integration task after the current safety gates are complete.

## Control Ownership

During S15:

| Device | CAN / Interface | Controller owner |
| --- | --- | --- |
| Arm A | `can_arm_a`, USB bus-info `1-3.4.1:1.0` | ROS2 `agx_arm_ros` under namespace `/arm_a` |
| Arm B | `can_arm_b`, USB bus-info `1-3.4.3:1.0` | ROS2 `agx_arm_ros` under namespace `/arm_b` |
| Left hand | `can1`, USB bus-info `1-3.4.4:1.0` | LinkerHand SDK safety wrappers |
| Right hand | `can2`, USB bus-info `1-3.4.2:1.0` | LinkerHand SDK safety wrappers |

Do not run arm SDK motion scripts while ROS arm control is active. Do not run
LinkerHand GUI/demo/gesture scripts while project hand wrappers are active.

2026-07-02 USB-C hub topology update:

- Arm A official USB-CAN moved to bus-info `1-3.4.1:1.0`; temporary kernel
  interface observed as `can3`.
- Arm B official USB-CAN moved to bus-info `1-3.4.3:1.0`; temporary kernel
  interface observed as `can0`.
- Left and right hand CAN paths stayed at `can1`/`1-3.4.4:1.0` and
  `can2`/`1-3.4.2:1.0`.
- Re-activation passed on 2026-07-02; see
  `docs/results/s15_usb_c_can_activation_result_20260702.md`.

## S15.0 No-Motion Integration Health

Goal: prove arm ROS feedback and hand SDK health can run in the same session
without command conflicts.

Checks:

```bash
bash scripts/s10_control_source_audit.sh

# Terminal 1: start accepted dual-arm ROS read-only/control driver as used in S13.
bash scripts/run_humble_container.sh \
  bash /workspace/nero/scripts/launch_dual_ros_readonly.sh

# Terminal 2: verify arm ROS topics and rates.
NERO_CONTAINER_NAME=nero-humble-s15-tools \
  bash scripts/run_humble_container.sh ros2 topic list

# Terminal 3: verify hand SDK health.
.venv/nero-sdk/bin/python scripts/s14_linkerhand_l6_sdk_health.py \
  --can can1 \
  --side left

.venv/nero-sdk/bin/python scripts/s14_linkerhand_l6_sdk_health.py \
  --can can2 \
  --side right
```

Acceptance:

- Arm feedback topics exist for both arms.
- Arm faults remain zero.
- Hand faults remain zero.
- No unexpected motion occurs.
- No stale SDK/GUI/demo processes are running.

## S15.1 Static Coordination Dry Run

Goal: prepare a single operator-facing sequence that does not move the arms and
only dry-runs the hands.

Planned sequence:

1. Verify arm ROS feedback.
2. Dry-run dual-hand open or dual index micro.
3. Record the intended command timing.

Acceptance:

- No arm command is published.
- No hand command is sent unless `--execute` is explicitly supplied.
- Both control domains are visible and separable.

## S15.2 First Hybrid Motion

Goal: one very small arm motion plus one very small hand motion, with explicit
ordering and no object contact.

Recommended first hybrid motion:

1. Move no arms; execute dual-hand index micro once if S15.0/S15.1 are accepted.
2. Then do a known-safe single-arm or dual-arm J1 micro motion using the existing
   ROS gate, while hands stay open.
3. Only after both are accepted separately, combine them in a sequential script:
   hands open -> arm micro motion -> hands index micro -> return hands open.

Do not start with simultaneous arm and hand motion.

## S15.3 Segmented Arm + Hand Coordination Script

Implemented scripts:

- `scripts/launch_s15_dual_arm_hand_observe.sh`
- `scripts/ros_s15_arm_hand_sequence.py`

`launch_s15_dual_arm_hand_observe.sh` defaults to `--readonly`; use that for
RViz validation and dry-run. Relaunch it with `--active` only before execute
gates.

Before either mode, confirm the arm cables are seated and wait about `20 s`
after arm power-on or CAN/power reconnect before judging `candump` or ROS topic
checks. This rule comes from the 2026-07-02 Arm B loose-cable recovery.

If RViz shows the arms horizontal while the physical arms are hanging, stop
before any motion and run `scripts/s15_rviz_pose_diagnostics.sh`. The most
likely causes are missing `robot_state_publisher` subscription to
`/arm_*/feedback/joint_states`, missing S11 static TF, or a stale duplicate
session.

2026-07-02 diagnostic correction:

- The S15 diagnostic run proved that the feedback publishers/subscribers and
  accepted S11 static TF were present.
- The remaining mismatch is a raw joint-state visual-convention mismatch:
  current raw feedback places `link7` horizontally in the URDF even though the
  real arms are hanging.
- `launch_s15_dual_arm_hand_observe.sh` therefore defaults to an RViz-only
  visual anchor that publishes `/arm_a/visual/joint_states` and
  `/arm_b/visual/joint_states` from live feedback plus an S11 accepted visual
  reference offset.
- These visual topics are only for RViz observation. Do not use them for arm
  control, MoveIt planning, joint limits, calibration, or acceptance of real
  controller semantics.
- Use `--raw-rviz` only when deliberately reproducing the raw mismatch.

The first absolute target `joint1=30 deg`, `joint2=90 deg`, `joint3=30 deg`
was useful as a software dry-run, but it did not match the intended
human-like elbow-curl gesture during physical execution. Do not use it as the
gesture definition.

The current operator-observed left-side candidate is delta-based:

```text
left side = Arm B + left hand can1
Arm B joint1: -10 deg
Arm B joint4: +10 deg
hand: open -> close -> open
```

The first execution order is now:

1. run `ros_s15_return_to_initial.py`;
2. dry-run and execute the left-side `2 deg` arm-only probe;
3. dry-run and execute the left-side `10 deg` half-fist demo;
4. only after left-side acceptance, mirror the same process for the right side
   and then both sides.

2026-07-02 single-side result:

- Left-side Arm B + left hand and right-side Arm A + right hand elbow-curl/fist
  demos were accepted by operator observation.
- The smoother mode is `--arm-profile single-target --hand-timing during-curl`.
- Arm A raw J1 sign differed from Arm B in `lab_world X`; this is now handled
  in `ros_s15_elbow_curl_demo.py` by defaulting to `--j1-delta-frame lab-world-x`.

Next dual-arm gate:

```bash
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

In dry-run, verify that Arm B commands raw `joint1=-10 deg` and Arm A commands
raw `joint1=+20 deg`. Execute only after RViz, clearance, and active-driver
state are confirmed.

2026-07-02 dual-arm result:

- The dual-arm/dual-hand elbow-curl/fist gate ran through by operator report.
- The return-to-initial script was then corrected so its default target is the
  accepted all-joint-zero posture, not the older S15 field park.
- Use `--pose s15-park` only when explicitly reproducing older S15 field-park
  checks.

Full procedure and acceptance criteria:
`docs/phases/s15_arm_hand_coordination_sequence_plan.md`.

## Why Not Full Synchronization Yet

The current dual-hand script is good enough for first coordination but is not a
hard real-time synchronizer. It sends commands to two independent CAN adapters
from Python threads and reports millisecond-level send deltas. That is adequate
for bring-up, but not yet for contact-rich manipulation.

For real manipulation experiments, implement a ROS2 coordination layer that:

- subscribes to arm feedback and publishes arm commands;
- wraps LinkerHand SDK commands behind ROS services/actions;
- logs one timeline for arms and hands;
- enforces control-source exclusivity and emergency stop policy.
