# NERO Agent Operating Rules

Last updated: 2026-07-02

This file defines how any agent, operator, or collaborator should continue the
NERO arm deployment work in this repository.

## Core Principle

Be faithful to documents, facts, and observed results.

Do not invent missing hardware facts, software versions, wiring details, launch
arguments, firmware behavior, or safety status. If something is unknown, write it
as unknown and define how it will be verified.

## Source Of Truth Order

Use sources in this order:

1. Local project documents and assets:
   - `docs/phases/机器人部署与调试行动路线.md`
   - `docs/status/current_bringup_status.md`
   - `docs/status/bringup_checklist.md`
   - `docs/status/setup_framework.md`
   - `docs/phases/s2_hybrid_host_container_plan.md`
   - `docs/phases/s9_configuration_review.md`
   - `docs/phases/s11_dual_arm_experiment_baseline.md`
   - `docs/phases/s12_control_isolation_plan.md`
   - `docs/assets/manuals/nero 用户手册.md`
   - `docs/assets/manuals/机械臂通信协议V1.2.1.xlsx`
   - `docs/evidence/pics/`
   - `config/nero.env`
2. Direct observations from this machine:
   - terminal output
   - installed package versions
   - ROS topic output
   - CAN captures
   - Web UI screenshots or user-provided observations
3. Official upstream project sources:
   - `agx_arm_ros`
   - `pyAgxArm`
   - `piper_ros`
   - official AgileX documentation or repositories
4. User-provided现场事实, with date and context recorded.

If two sources conflict, stop and document the conflict before acting. Prefer
the local manual/protocol for hardware facts, and prefer live machine output for
current environment state.

## Upstream Repository Roles

Do not treat the three cloned GitHub repositories as interchangeable. Their
roles are different:

| Repository | Local evidence path | Role | How to use later |
| --- | --- | --- | --- |
| `agilexrobotics/agx_arm_ros` | `upstream/agx_arm_ros` | Main ROS integration and control workspace. It is the current ROS2 path for NERO. | Use for S2B ROS host setup, S3 ROS2 model display, S8 ROS read-only feedback, and later MoveIt/application integration after safety gates. Clone branch `ros2` with submodules in the real ROS workspace. |
| `agilexrobotics/pyAgxArm` | `upstream/pyAgxArm` | Python SDK and hardware access layer over CAN. It is usable without ROS and is also used by the ROS driver. | Use for S2A SDK/CAN-only preparation and S7 read-only status checks. Firmware selector must be chosen from observed robot firmware. Do not use SDK motion APIs before the motion gates. |
| `agilexrobotics/piper_ros` | `upstream/piper_ros` | Reference source for the user-provided NERO URDF path on branch `humble_beta1`. It is a model/description reference, not the current NERO control route. | Use to cross-check NERO model files, meshes, joint naming, and historical URDF differences. Do not make it the default ROS control workspace unless a separate validation plan is written. |

The `agx_arm_ros` submodule `agx_arm_urdf` is the model set used by the current
ROS2 driver. Prefer it for the runtime ROS2 workspace unless a documented model
comparison shows a reason to use the older `piper_ros` description package.

The `upstream/` directory is an evidence cache in this project. Runtime builds
should happen in the selected deployment workspace, normally `~/agx_arm_ws`, on
the selected ROS2 host.

## Phase Discipline

Follow the route in `docs/phases/机器人部署与调试行动路线.md`.

Do not skip phase gates. A later phase may be prepared offline, but it must not
be marked complete until its acceptance criteria are satisfied.

Current phase state is tracked in `docs/status/current_bringup_status.md`.

## Mandatory Work Cycle

For every deployment step, use this cycle:

1. Read the current status and relevant phase section.
2. State the intended action and why it belongs to the current phase.
3. Execute the smallest useful step.
4. Verify the result with a command, file check, screenshot, CAN capture, ROS
   output, or explicit user现场确认.
5. Record the step in `docs/status/deployment_log.md`.
6. Update `docs/status/current_bringup_status.md` if phase status, assumptions,
   blockers, or confirmed configuration changed.
7. Update and correct `docs/phases/机器人部署与调试行动路线.md` after the step:
   - add newly learned facts
   - correct wrong assumptions
   - refine acceptance criteria
   - add safety notes or blockers
   - keep phase ordering consistent
8. Update `config/nero.env`, scripts, or checklists if a deployment choice became
   durable.

The route document must remain a living plan, not a stale plan.

## Documentation Requirements

Every step record must preserve:

- date and phase
- goal
- action taken
- commands or tools used
- key output or observed result
- deployment choice made
- files changed
- verification result
- blockers or residual risk
- next step

Use this minimum format in `docs/status/deployment_log.md`:

```markdown
## YYYY-MM-DD - Sx.y Short Title

Phase: Sx phase name
Goal:
Action:
Commands / evidence:
Result:
Deployment choices:
Files changed:
Verification:
Route updates:
Open risks:
Next:
```

Do not paste huge logs unless needed. Summarize key lines and point to saved log
files when appropriate.

## Safety Rules

The default state is no motion.

Before any real robot motion:

- S0-S9 must be completed or explicitly scoped for the motion being attempted.
- The base must be physically fixed.
- Only one control source may be active.
- The power cutoff / emergency stop path must be assigned to a person.
- The arm workspace must be clear.
- Feedback must be sane through Web/CAN/SDK/ROS as required by the current phase.

High-risk actions require an explicit route entry and operator confirmation:

- first real robot motion in a new control path
- zero calibration
- firmware upgrade
- MIT control
- master-slave mode
- collision-level changes
- joint limit or max-speed changes
- raw CAN motion commands
- dexterous hand installation and first actuation

## Current Project Defaults

These are the current deployment assumptions. Update them only when verified.

| Item | Current value |
| --- | --- |
| Current end effector | Dual LinkerHand L6 dexterous hands installed; Arm A right hand, Arm B left hand |
| Planned end effector | S15 dual-arm + dual-hand bring-up demo; not contact manipulation |
| Physical arm count | `2`, independent power |
| Arm A | Web verified; hotspot `agx-7ax-armA`; CAN `can_arm_a`; namespace `arm_a`; USB bus `1-3.4.1:1.0` |
| Arm B | Web verified; hotspot `agx-7ax-armB`; CAN `can_arm_b`; namespace `arm_b`; USB bus `1-3.4.3:1.0` |
| Left hand | LinkerHand L6 on `can1`; USB bus `1-3.4.4:1.0` |
| Right hand | LinkerHand L6 on `can2`; USB bus `1-3.4.2:1.0` |
| Initial ROS `effector_type` | `none` |
| Installation pose | Table upright |
| Power supply | Factory adapter |
| CAN ports | Arms: `can_arm_a`, `can_arm_b`; hands: `can1`, `can2` |
| CAN bitrate | `1000000` |
| Initial TCP offset | `[0.0, 0.0, 0.0, 0.0, 0.0, 0.0]` |
| Deployment mode | Ubuntu 20.04 host SDK/CAN-only + Docker ROS2 Humble |
| Current live state | S15 elbow-curl/fist gate accepted by operator report; zero-return revalidation is the next closure gate |
| Observed Web model | `7ax`, interpreted as one NERO 7-axis arm/controller per physical arm |
| Observed Web footer version | `v1.121`; current SDK firmware selector is `v112` |
| Current next phase | S15 closure and post-bring-up integration planning |

Current Web evidence shows one set of joint tabs, `关节1` through `关节7`.
Treat this as normal for one NERO 7-axis arm/controller. The physical setup has
two arms, so each arm is treated as a separate controller/IP/CAN device with its
own ROS namespace.

Dual-arm safety rule: unique Wi-Fi names and independent CAN paths are verified.
Do not place both arms on the same CAN bus unless a separate bus-design review is
completed. For ROS read-only launches, explicitly use `auto_enable:=false` and
`control_enabled:=false`, because the upstream single-arm launch defaults both
to `true`.

S10 dual-arm first motion is accepted and closed. Arm A and Arm B both passed
the staged Web, SDK, and ROS low-speed single-joint checks. Final S10.8 audit
`docs/results/s10_8_control_source_audit_live_20260625_155538.txt` reported both CAN
interfaces UP/ERROR-ACTIVE at 1 Mbps, no NERO Docker container, and no NERO host
process.

S11 dual-arm experiment baseline is accepted and closed. The accepted shared
frame is `lab_world`: origin at Arm A base center projection, `+X` from Arm A
to Arm B, `+Y` left when facing `+X`, and `+Z` up. Accepted runtime static TF
values are:

- `lab_world -> arm_a/world`: `x=0.000`, `y=0.000`, `z=0.000`,
  `roll=0`, `pitch=-1.5707963`, `yaw=0`.
- `lab_world -> arm_b/world`: `x=0.260`, `y=0.000`, `z=0.000`,
  `roll=3.1415926`, `pitch=-1.5707963`, `yaw=0`.

S11 evidence: successful RViz screenshot
`docs/evidence/pics/S11_RViz_accepted_dual_arm_layout.png`; post-TF read-only snapshot
`docs/evidence/ros_snapshots/20260626_055339/` with `Failed capture commands: 0`,
A/B joint-state feedback at about 200 Hz, A/B `err_status: 0`, no joint-limit
flags, and no joint communication flags. X11 cleanup was confirmed by `xhost`
showing access control enabled and only `SI:localuser:lv-robotics`.

S12 should verify control isolation and logging before any coordinated
manipulation: when Arm A receives a small command, Arm B must remain still and
vice versa; namespace, CAN interface, command logs, feedback logs, snapshots,
and git commit linkage must be unambiguous. Do not run Cartesian, MoveIt,
MIT/JS, raw CAN motion, dexterous-hand actuation, or dual-arm coordinated
motion until their later gates are explicitly accepted.

S12 prepared path: use `docs/phases/s12_control_isolation_plan.md`.
For visible field observation, the current S12 test target is a bounded J1
`30 deg` move at `speed_percent=5`, still one active arm at a time. The inferred
signs for a `lab_world -Y` sweep are Arm A `joint1 +30 deg` and Arm B
`joint1 -30 deg`. Treat the sign as inferred from URDF/S11 TF until dry-run and
operator observation confirm it. If direction is uncertain, run the optional
`5 deg` sign gate before the `30 deg` acceptance move. Passive arm tolerance is
`1.0 deg`; target return tolerance is `0.7 deg`.

S12.1 Arm A is accepted and closed. Evidence: dry-run accepted in commit
`c6a92eb`, execution core recorded in commit `3e4e2a0`, and post-motion
snapshot `docs/evidence/ros_snapshots/20260626_080809/` is clean. Arm A
`joint1 +30 deg` matched the intended visible direction, Arm B did not visibly
move, max passive deviation was `0.005 deg`, and A/B post-motion read-only
status had `err_status: 0` with no joint-limit or joint-communication flags.
S12.2 Arm B dry-run is accepted: target changes only Arm B `joint1` from
`-1.988 deg` to `-31.988 deg`, Arm A is passive read-only, and both statuses
had `err_status: 0`. S12.2 Arm B execution core also passed: Arm B
`joint1 -30 deg` matched the expected direction, Arm A did not visibly move,
max passive deviation was `0.008 deg`, and A/B final statuses had
`err_status: 0`. Post-motion snapshot
`docs/evidence/ros_snapshots/20260626_083210/` is clean.

S12 is accepted and closed. Arm A isolation evidence is in commits `c6a92eb`,
`3e4e2a0`, and snapshot `docs/evidence/ros_snapshots/20260626_080809/`. Arm B
isolation evidence is in commits `19e007e`, `64fe5a4`, and snapshot
`docs/evidence/ros_snapshots/20260626_083210/`. S12 accepted script output and
read-only snapshots as equivalent logging evidence; no rosbag was recorded in
S12. Intentional emergency-stop testing was not performed. Next phase is S13:
simultaneous read-only stability, enable/hold, and very small non-contact
joint-space dual-arm primitives only.

S13 prepared path: use `docs/phases/s13_low_risk_dual_arm_primitives_plan.md`.
The first planned primitive keeps the same visible J1 amplitude from S12:
Arm A `joint1 +30 deg`, Arm B `joint1 -30 deg`, `speed_percent=5`. The S13
driver pair sets both arms `auto_enable=true` and `control_enabled=true`, but
the first command must be a dry-run plus `3 s` hold check. Execution requires
operator confirmation that both swept areas and cables are clear. S13 still
does not authorize Cartesian motion, MoveIt, contact, handoff, close-proximity
bimanual tasks, or dexterous-hand actuation.

S13 dry-run and hold gate is accepted. Dry-run target changed only Arm A
`joint1` from `1.111 deg` to `31.111 deg` and Arm B `joint1` from `-1.988 deg`
to `-31.988 deg`; A/B statuses had `err_status: 0`; hold max deviation was
`0.0 deg` for both arms. The first S13 execution with those same signs completed
numerically and returned safely, with A/B final `err_status: 0` and non-target
joint deviations below `1.0 deg`. Operator observation did not accept the
world-direction semantics: Arm B appeared to move in the same visible direction
as Arm A instead of the expected opposite direction. Treat this as a successful
dual-arm joint-space control-chain test but a failed S13 world-direction
primitive. Next gate is a post-motion read-only snapshot, then corrected J1
direction-sign dry-run; do not repeat Arm A `+30 deg` / Arm B `-30 deg` as an
"opposite direction" primitive.

S13 post-motion read-only snapshot after the direction-semantics mismatch is
accepted: `docs/evidence/ros_snapshots/20260626_090214/` has `Failed capture
commands: 0`, A/B joint-state feedback at about `200 Hz`, A/B `err_status: 0`,
all joint-limit flags `false`, and all joint-communication flags `false`. The
next S13 gate is corrected direction-sign dry-run only, with the current
hypothesis Arm A `joint1 +30 deg` and Arm B `joint1 +30 deg`; execution still
requires a fresh operator safety gate.

S13 corrected direction-sign dry-run is accepted. The no-execute run used Arm A
`joint1 +30 deg` and Arm B `joint1 +30 deg`: Arm A target changed from
`1.110 deg` to `31.110 deg`, Arm B target changed from `-1.988 deg` to
`28.012 deg`, only `joint1` changed on each arm, A/B `err_status: 0`, and
`hold_max_dev_deg` was about `0.008 deg` for Arm A and `0.006 deg` for Arm B.
Next gate is corrected `--execute` with the same signs after fresh operator
safety confirmation.

S13 corrected direction-sign execution core is accepted, but S13 is not closed
until its post-motion read-only snapshot is accepted. The accepted execution
used Arm A `joint1 +30 deg` and Arm B `joint1 +30 deg`; operator observation
confirmed the visible direction matched expectation. After-step J1 values were
Arm A `30.459 deg` and Arm B `27.318 deg`; after-return J1 values were Arm A
`1.737 deg` and Arm B `-1.394 deg`; final A/B `err_status: 0`; non-target
deviations were about `0.006 deg` and `0.007 deg`.

S13 final snapshot attempt `docs/evidence/ros_snapshots/20260626_093414/` is not
accepted for closure. It has `Failed capture commands: 0`, A/B `err_status: 0`,
no joint-limit flags, and no joint-communication flags, but A/B joint-state
frequency is about `400 Hz`, not the expected about `200 Hz`. Treat this as a
likely duplicate-publisher state caused by an extra ROS driver/container still
running. Next gate: stop extra ROS drivers, verify a single feedback source, and
rerun the corrected-execution final read-only snapshot.

S13 is accepted and closed. A second frequency-anomaly snapshot
`docs/evidence/ros_snapshots/20260629_043358/` still showed about `400 Hz`, so it is
recorded as not accepted. The operator then verified `Publisher count: 1` for
both `/arm_a/feedback/joint_states` and `/arm_b/feedback/joint_states`. Final
snapshot `docs/evidence/ros_snapshots/20260629_043441/` is accepted: `Failed capture
commands: 0`, A/B about `200 Hz`, A/B `err_status: 0`, all joint-limit flags
`false`, and all joint-communication flags `false`. The accepted S13 primitive
is Arm A `joint1 +30 deg` and Arm B `joint1 +30 deg`; Arm A `+30 deg` / Arm B
`-30 deg` remains rejected for world-direction semantics. Next phase is S14:
end-effector pre-installation review before any dexterous-hand mounting,
powering, configuration, or actuation.

S14 is active. On 2026-06-29 the operator reported both dexterous hands
are mechanically installed. Current mapping follows the prior decision: Arm A
has the right hand and Arm B has the left hand. Cable routing constrains J6/J7
wrist motion; operator reports bends below about `70 deg` do not interfere, but
larger bends may. Treat this as a field cable-bend constraint, not a calibrated
joint-angle limit. Next gate is S14.0/S14.1 no-motion mechanical/cable/read-only
verification. Do not actuate fingers, do not use Web dexterous hand controls,
and do not command large J6/J7 wrist motions until S14 records the cable-safe
envelope, load/TCP decisions, and a clean no-motion read-only path.

S14.0 mechanical/cable review is accepted. The operator archived cable photos
at `docs/evidence/pics/S14自然状态线束.jpeg` and `docs/evidence/pics/S14手腕弯折状态线束.jpeg`,
confirmed left/right mapping, and confirmed both hands are mechanically stable.
The temporary J6/J7 cable rule remains active: no large wrist motion beyond the
observed about `70 deg` cable-bend envelope. Next gate is S14.1 no-motion ROS
read-only verification with no Web hand controls and no finger actuation.

S14.1 arm read-only verification is accepted with a posture warning. The
operator confirmed `Publisher count: 1` for both A/B joint-state feedback topics.
Snapshot `docs/evidence/ros_snapshots/20260629_074337/` has `Failed capture
commands: 0`, A/B about `200 Hz`, A/B `err_status: 0`, all joint-limit flags
`false`, and all joint-communication flags `false`. A/B `arm_status=3`, which
upstream maps to `SINGULARITY_POINT` / `奇异点`; A/B `motion_status=1`, not
reached target. Treat S14.1 as communication/read-only pass only, not
motion-ready posture approval. Next gate is S14.2 model/parameter decision and
then Revo2 hand read-only; no finger, wrist, Cartesian, or Web hand action yet.

S14.2 model/parameter decision is recorded. Keep the global arm-only regression
default as `effector_type:=none`; use `scripts/launch_s14_dual_revo2_readonly.sh`
for S14 hand read-only with `effector_type:=revo2`,
`auto_enable:=false`, and `control_enabled:=false`. Physical/model mapping is
Arm A right Revo2 and Arm B left Revo2. The first S14.3 hand-topic attempt did
not produce hand topics because both driver logs showed `effector_type: none`.
Treat that as an environment/config propagation issue, not a Revo2 hardware
failure. The next S14.3 retry must first confirm `effector_type: revo2` in A/B
logs before checking `/arm_a/feedback/hand_status` and
`/arm_b/feedback/hand_status`.

S14.3 corrected Revo2 launch exposed A/B hand endpoints, including
`/arm_a/feedback/hand_status`, `/arm_b/feedback/hand_status`, and the matching
`/control/hand` endpoints. This is not yet accepted as physical hand feedback:
raw `ros2 topic echo --once /arm_a/feedback/hand_status` waited without output.
Use `scripts/s14_revo2_hand_status_probe.sh` for bounded read-only probes. Do
not publish to `/control/hand` or `/control/hand_position_time` before a
separate S14.4 motion/safety gate.

New S14 field evidence changes the preferred hand path. The operator provided
the previously used `linkerhand_sdk` source tree, now stored at
`upstream/linkerhand_sdk/` and reviewed in
`docs/upstream/s14_linkerhand_sdk_review.md`. It identifies the installed hands as a
dual LinkerHand L6 setup, not the AgileX Revo2 path: left hand default `can0`,
serial `LHL6-03-253-L-B-1-C`, CAN ID `0x28`; right hand default `can1`,
serial `LHL6-03-240-R-B-1-C`, CAN ID `0x27`; bitrate `1000000`.
S14.3 is reoriented to S14.3L LinkerHand read-only CAN identification. Do not
run `test_hand.py`, `gestures.py`, `diagnose.py`, `dual_gui.py`, or publish
AgileX `/control/hand` before the S14.4 motion gate.
The script passed local syntax checking. A Codex-session run saw no NERO-related
host process but could not see `can_arm_a` or `can_arm_b`; the live
desktop-terminal audit then passed on 2026-06-25 and is saved at
`docs/results/s10_4_control_source_audit_live_20260625_150438.txt`. S10.4 is accepted
with handoff state `handoff_to_arm_b`.

S10.5 Arm B status: accepted. Pre-motion audit
`docs/results/s10_5_control_source_audit_live_20260625_152039.txt` is clean,
post-Web/read-only snapshot `docs/evidence/ros_snapshots/20260625_072129/` is clean,
and the operator confirmed Arm B Web motion was normal.

S10.6 Arm B status: accepted. SDK dry-run used `can_arm_b`, firmware `v112`,
J1 `+2 deg`, speed `5%`, and target differed only in J1. Operator confirmed SDK
real motion was observed successfully and execution was smooth. Post-SDK
snapshot `docs/evidence/ros_snapshots/20260625_074048/` is clean. Full SDK execute
terminal output was not pasted, so exact `after_step_deg` and `after_return_deg`
values are not recorded.

S10.7 prepared path: use `docs/phases/s10_7_arm_b_ros_motion_plan.md`. Stop the
dual-arm read-only driver, start only the Arm B ROS control driver with
`namespace:=arm_b`, `can_port:=can_arm_b`, `auto_enable:=true`,
`control_enabled:=true`, `speed_percent:=5`, then run the `/arm_b` dry-run
before any ROS execute.

S10.7 Arm B status: accepted. ROS execute moved Arm B `joint1` from about
`32.798 deg` to `34.553 deg`, returned to about `33.026 deg` within script
tolerance, and final status was `ctrl_mode=1`, `arm_status=0`,
`mode_feedback=1`, `motion_status=0`. Post-ROS snapshot
`docs/evidence/ros_snapshots/20260625_074953/` is clean; sampled Arm B J1 is about
`32.797 deg`, consistent with settled return. Next step is S10.8 closure:
stop/account for Arm B ROS control and audit active control sources before any
broader motion phase.

S10.8 status: accepted. Final control-source audit
`docs/results/s10_8_control_source_audit_live_20260625_155538.txt` shows A/B CAN
UP/ERROR-ACTIVE at 1 Mbps, no NERO Docker containers, and no NERO host
processes. S10 is complete. Next phase is S11 dual-arm experiment baseline:
define `lab_world`, measure both base transforms, establish static TF, and
create logging/rosbag rules before any coordinated dual-arm motion.

S11 prepared path: use `docs/phases/s11_dual_arm_experiment_baseline.md`. S11 is a
coordinate, TF, TCP, and logging baseline phase, not a motion-expansion phase.
Keep `effector_type:=none` and TCP offset zero until an end effector is
installed and measured. End-effector installation is now S14, not S11.

S11 measurement state: the operator defined `lab_world` with Arm A base center
projection as origin, `+X` from Arm A to Arm B, `+Y` left when facing `+X`, and
`+Z` up. Arm B translation is recorded as `x=0.260 m, y=0, z=0`. Arm B yaw
candidate is `3.1415926 rad`, inferred from Web-axis observations, but it is not
accepted until RViz confirms the ROS `base_link` orientation. Do not treat Web
coordinate axes as identical to ROS `base_link` without validation.

## Raw CAN Policy

Raw CAN is not the default control path. Use raw CAN first for observation and
diagnostics.

Before sending any raw CAN command:

- write the frame ID, length, byte meaning, unit, and expected response
- confirm the arm mode
- confirm emergency stop behavior
- watch `0x2A1` and the relevant feedback IDs
- record the command and result in `docs/status/deployment_log.md`

Never send undocumented `cansend` commands during bring-up.

## Tooling And File Hygiene

- Prefer read-only checks first.
- Keep changes scoped to the current phase.
- Do not delete or rewrite source documents.
- Do not modify generated CAD/model assets unless explicitly required.
- Do not treat `docs/status/bringup_checklist.md` as a permanent log. It is a reusable
  checklist; durable evidence belongs in `docs/status/deployment_log.md` and
  `docs/status/current_bringup_status.md`.
- If a script or command changes deployment behavior, document the reason and
  update the route.

## Completion Rule

A phase is complete only when:

- its acceptance criteria are met
- evidence is recorded
- the current status file is updated
- the action route has been corrected with what was learned
- the next phase entry is clear
