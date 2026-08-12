# NERO Current Bring-Up Status

Last updated: 2026-07-06

## Confirmed Configuration

| Item | Current value |
| --- | --- |
| Current end effector | Dual LinkerHand L6 dexterous hands installed mechanically; Arm A right hand, Arm B left hand |
| Planned end effector state | S15 dual arm + dual hand demo closure and post-bring-up integration planning |
| Physical arm count | Two NERO arms, independently powered |
| Arm A | Web verified; hotspot `agx-7ax-armA`; planned CAN `can_arm_a`; ROS namespace `arm_a` |
| Arm B | Web verified; hotspot `agx-7ax-armB`; planned CAN `can_arm_b`; ROS namespace `arm_b` |
| USB-CAN modules | Two official arm modules plus two hand PEAK/XCAN adapters on the USB-C hub |
| Arm A USB-CAN bus-info | `1-3.4.1:1.0` after USB-C hub move; previous `1-5:1.0` |
| Arm B USB-CAN bus-info | `1-3.4.3:1.0` after USB-C hub move; previous `1-11:1.0` |
| Arm A USB physical port | USB-C hub path `1-3.4.1:1.0`; temporary interface observed as `can3` |
| Arm B USB physical port | USB-C hub path `1-3.4.3:1.0`; temporary interface observed as `can0` |
| Left hand USB-CAN bus-info | `1-3.4.4:1.0`; interface `can1` |
| Right hand USB-CAN bus-info | `1-3.4.2:1.0`; interface `can2` |
| Installation pose | Table upright / horizontal upright |
| Power supply | Original factory adapter |
| Web UI | Reachable at `http://192.168.31.1/#/welcome` |
| Observed Web model | `7ax`, one NERO 7-axis controller/arm per physical arm |
| Observed Web footer version | `v1.121`; current SDK firmware selector is `v112` |
| Workspace | Clear enough for bring-up |
| Power cutoff path | Known and reachable |
| Manual key images | Present under `docs/evidence/pics/` |

## Current Phase

| Phase | Status | Notes |
| --- | --- | --- |
| S0 资料基线 | Complete | Manual text, CAN protocol, CAD files, and key manual images are present. |
| S1 安全与场地 | Complete for planning | Before power-on, perform the final physical checklist again on site. |
| S2 主机环境 | Complete for offline bring-up | Shared Ubuntu 20.04 host has SDK/CAN-only tools; Docker ROS2 Humble image and `agx_arm_ros` workspace build are complete. |
| S3 离线模型 | Complete | NERO URDF/xacro/check_urdf/robot_state_publisher checks pass; desktop RViz GUI verification succeeded. |
| S4 机械与电气连接 | Power-on successful, final wiring evidence pending | Robot powered on through the factory adapter; Web page is reachable. |
| S5 Web 验机 | Complete for both arms | Arm A and Arm B Web checks passed; Wi-Fi hotspots are unique. |
| S6 CAN 只读 | Interface activation passed, feedback capture reported normal | `can_arm_a` and `can_arm_b` are UP, ERROR-ACTIVE, bitrate `1000000`; operator reports normal CAN frames. |
| S7 SDK 只读 | Complete by operator report | SDK read-only checks passed on `can_arm_a` and `can_arm_b`. |
| S8 ROS 只读 | Complete; coordinate alignment deferred to S9 | `/arm_a` and `/arm_b` feedback topics publish at about 200 Hz; arm status has `err_status: 0`; RViz follow is normal after the dual ROS read-only driver terminal is started first. |
| S9 标定与配置 | Complete by operator confirmation and ROS revalidation | Load mode was changed by operator report; Arm A CAN recovered after USB-CAN replug/reactivation; S9.3 snapshot `20260625_054435` has complete A/B feedback, `err_status: 0`, no joint limits, no joint communication errors, and about 200 Hz joint-state feedback. |
| S10 首次低速运动 | Complete for both arms | Web, SDK, and ROS J1 motion passed on Arm A and Arm B. Final S10.8 audit `20260625_155538` shows both CAN interfaces UP/ERROR-ACTIVE at 1 Mbps, no NERO Docker container, and no NERO host process. |
| S11 双臂实验基线 | Complete / accepted | `lab_world` is defined with Arm A center as origin and `+X` from Arm A to Arm B. Accepted static TF values are `lab_world -> arm_a/world: x=0, y=0, z=0, roll=0, pitch=-1.5707963, yaw=0` and `lab_world -> arm_b/world: x=0.260, y=0, z=0, roll=3.1415926, pitch=-1.5707963, yaw=0`. Operator reports RViz matches the physical layout and follows both arms when they move. Post-TF snapshot `20260626_055339` is clean, and X11 access was restored to local-user only. |
| S12 控制隔离与日志闭环 | Complete / accepted | Arm A `joint1 +30 deg` and Arm B `joint1 -30 deg` isolation tests both passed and returned. Passive-arm deviations were `0.005 deg` for Arm B during Arm A motion and `0.008 deg` for Arm A during Arm B motion. Post-motion snapshots `20260626_080809` and `20260626_083210` are clean: failed captures `0`, A/B about `200 Hz`, A/B `err_status: 0`, no joint-limit flags, and no joint-communication flags. |
| S13 低风险双臂协同原语 | Complete / accepted | Corrected Arm A `joint1 +30 deg` / Arm B `joint1 +30 deg` execution passed and operator confirmed visible direction matched expectation. Earlier final-snapshot attempts `20260626_093414` and `20260629_043358` were not accepted because duplicate publishers produced about `400 Hz` feedback. After cleanup, publisher count was `1` for both A/B joint-state topics, and final snapshot `20260629_043441` is clean: failed captures `0`, A/B about `200 Hz`, A/B `err_status: 0`, no joint-limit flags, and no joint-communication flags. |
| S14 末端执行器 | Complete for low-risk dual-hand bring-up; S15 hybrid arm+hand demo accepted by operator report | Both dexterous hands are mechanically installed and stable. Arm A = right hand, Arm B = left hand. Left hand on `can1` and right hand on `can2` passed SDK health, open-anchor, and index micro-motion. Dual open-anchor and dual index-micro gates passed from SDK/software health. The dual index micro used left target `[255,179,235,255,255,255]` and right target `[255,70,235,255,255,255]`, then returned both to open; pre/post faults were all zero and temperature/current were stable. S15 decision: arms should use ROS2 `agx_arm_ros`, hands should keep using LinkerHand SDK wrappers for now. Contact grasping, handoff, close-proximity manipulation, and new full gestures remain blocked until a post-S15 safety gate is written and accepted. |
| S15 USB-C CAN 拓扑 | Activation and ROS read-only revalidation accepted | Arm A official USB-CAN moved to USB-C hub bus-info `1-3.4.1:1.0` and was restored from temporary `can3` to `can_arm_a`. Arm B official USB-CAN moved to `1-3.4.3:1.0` and was restored from temporary `can0` to `can_arm_b`. Left/right hand interfaces remain `can1`/`can2`. All four CAN interfaces are UP and ERROR-ACTIVE at 1 Mbps. A loose Arm B cable caused a no-response failure; after reseating and waiting about 20 s after power/reconnect, A/B ROS joint-state feedback both returned at about 200 Hz. |
| S15 双臂双手协调脚本 | Dual-arm elbow-curl accepted; return-to-zero corrected | New scripts `launch_s15_dual_arm_hand_observe.sh`, `ros_s15_arm_hand_sequence.py`, `ros_s15_return_to_initial.py`, and `ros_s15_elbow_curl_demo.py` provide RViz observation, selectable read-only/active ROS arm drivers, static TF, segmented or single-target arm motion, LinkerHand SDK hand open/close/open, conservative posture guards, dry-run default, and explicit execution confirmations. On 2026-07-02 raw RViz showed horizontal arms while the real arms were hanging; the anchored RViz visual path was added and operator accepted visual pose/follow. Operator returned to the initial posture successfully, found by Web control that left-side Arm B `J1 -10 deg` plus `J4 +10..15 deg` better matches the demo intent, and reported the S15 elbow-curl/fist semantic action matched expectation. The smoother single-target/during-curl mode was added after the segmented mode showed visible stop-start behavior. Arm A reproduction was smooth and semantically acceptable after `J1` was unified to `lab_world X` semantics; Arm A raw J1 is flipped internally. The dual-arm/dual-hand `--side both` elbow-curl/fist gate has run through by operator report. `ros_s15_return_to_initial.py` now defaults to `--pose zero`, commanding both arms to `joint1..joint7 = 0 deg`; legacy field park remains available as `--pose s15-park`. |

## S0 Evidence

Confirmed:

- User manual text: `docs/assets/manuals/nero 用户手册.md`
- CAN protocol: `docs/assets/manuals/机械臂通信协议V1.2.1.xlsx`
- Base model: `docs/assets/cad/nero3d.stp`
- Gripper and dexterous hand models: `docs/assets/cad/nero带夹爪以及带灵巧手模型/`
- Key manual images: `docs/evidence/pics/`

Manual image index:

| Purpose | File | Confirmed information |
| --- | --- | --- |
| Control panel | `docs/evidence/pics/2.1.1控制面板说明.png` | Wi-Fi antenna, aviation connector, status indicator, network port, internal-service port positions. |
| Aviation connector | `docs/evidence/pics/航插接口示意图.jpg` | Connector red dot must align with panel red dot before insertion. |
| End connector | `docs/evidence/pics/2.1.2末端连接电器说明.png` | End XT30 2+2 pinout: upper power `+/-`, lower CAN `H/L`. |
| Base mounting | `docs/evidence/pics/2.3.1 底座安装说明.png` | Base mounting pattern includes 4 x Ø5.4 through holes on a 70 mm x 70 mm pattern, compatible with M5 fastening. |
| CAN wiring | `docs/evidence/pics/3.1can线链接.jpg` | Red/black go to power adapter branch; yellow/blue go to USB-CAN branch. |
| CAN terminal | `docs/evidence/pics/3.1can线链接1.png` | Wire cores must be clamped at the terminal center; yellow is CAN_H, blue is CAN_L, final check follows terminal labels. |
| Power sequence | `docs/evidence/pics/3.2上电使用说明.png` | Physical harness/power connection is completed before USB-CAN host-side setup. |
| Dexterous hand size | `docs/evidence/pics/4 灵巧手示意图.png` | Hand clearance and flange dimensions are available for S14. |
| Dexterous hand flange | `docs/evidence/pics/5 灵巧手法兰安装示意图.png` | Dexterous hand flange mounting details are available for S14. |

S0 result:

- No manual-image blocker remains for S2-S4.
- Dexterous hand images are available and were used as S14 installation
  references.
- Global arm-only ROS default `effector_type` remains `none`; S14 hand read-only
  uses a dedicated `revo2` launch script.
- Initial TCP offset remains zero until a tool is installed and measured.

## S1 Result

Confirmed:

- Table upright installation is planned.
- Original factory adapter will be used.
- Workspace is clear enough.
- Power cutoff path is clear.

Final on-site checks before any power-on or motion:

- Confirm base is physically fixed using the 70 mm x 70 mm M5-compatible pattern.
- Confirm factory adapter label and cable are intact.
- Confirm no person, laptop, tool, or fragile object is under the arm where it can drop if disabled.
- Confirm no cable will be pulled by J6/J7 motion.
- Confirm one person is assigned to power cutoff or emergency stop during first tests.

## S2 Offline Result

S2 offline environment result:

1. S2A host SDK/CAN-only:
   `docker`, `candump`, `cansend`, and `ethtool` are installed; project host venv
   `.venv/nero-sdk` imports `python-can=4.5.0` and `pyAgxArm`.
2. S2B Docker ROS2 Humble:
   Docker image `nero-humble:local` exists; container reports Ubuntu 22.04.5,
   `ROS_DISTRO=humble`, `ros2`, `colcon`, and `python-can=4.6.1`.
3. ROS workspace:
   `~/agx_arm_ws` contains `agx_arm_ros` commit `c73d33f`, `pyAgxArm` commit
   `a226840`, and `agx_arm_urdf` submodule commit `f6642ce`; `colcon build`
   completed with 5 packages.
4. Docker build may leave workspace build artifacts with container-mapped
   ownership. Use `bash scripts/fix_ros_ws_permissions.sh` after container builds
   if host-side file permissions are wrong.
5. Do not choose Noetic as the default route. The cloned current AgileX control
   package is ROS2; Noetic would require a separate legacy ROS1 validation and
   maintenance plan.

## Immediate Next Step

S15 dual-arm/dual-hand elbow-curl/fist reproduction is accepted by operator
report. Keep this workspace focused on the accepted arm-hand control stack,
reproducible demo commands, safety boundaries, and post-S15 revalidation.

Recommended architecture remains unchanged: arms via ROS2 `agx_arm_ros`, hands
via LinkerHand SDK wrappers. This gate is still a bring-up demo, not a contact
manipulation primitive. Do not run Cartesian, MoveIt execute, grasping,
handoff, close-proximity manipulation, or new full-hand gestures until a
separate safety gate is written and accepted.

## S2 Discovery Result

Observed on 2026-06-24:

- OS: Ubuntu 20.04.6 LTS (`focal`).
- `/opt/ros` does not exist.
- Host-native `ros2` and `colcon` are intentionally absent; they are available
  inside the Docker ROS2 Humble container.
- Python in current shell: Miniconda Python 3.13.
- System Python: `/usr/bin/python3`, version 3.8.10.
- Host default Conda `python3` does not import `python-can` or `pyAgxArm`; the
  project venv `.venv/nero-sdk` does import them.
- `~/agx_arm_ws/src/agx_arm_ros` and `~/agx_arm_ws/src/pyAgxArm` exist and build
  in the container.
- Noetic evaluation: compatible with Ubuntu 20.04 as ROS1, but not recommended
  for the default NERO route because the current AgileX package path is ROS2
  Humble/Jazzy-oriented.
- `can-utils` is installed.
- `ethtool` is installed.
- `docker` is installed; current user was not added to the `docker` group.
- Ubuntu Focal apt candidate for `python3-can` is `3.3.2`, below the
  `pyAgxArm` requirement `python-can>=3.3.4`.

## Upstream Repository Evidence

Cloned and reviewed on 2026-06-24:

| Repository | Local path | Branch | Commit | Finding |
| --- | --- | --- | --- | --- |
| `agx_arm_ros` | `upstream/agx_arm_ros` | `ros2` | `c73d33f` | Current ROS control route is ROS2; README shows Humble/Jazzy and NERO support. |
| `pyAgxArm` | `upstream/pyAgxArm` | `master` | `a226840` | SDK supports Ubuntu 20.04 and Python 3.6+, usable standalone over SocketCAN. |
| `piper_ros` | `upstream/piper_ros` | `humble_beta1` | `2dc30fc` | Requested NERO path is a Humble/ament model description package. |
| `agx_arm_urdf` submodule | `upstream/agx_arm_ros/src/agx_arm_description/agx_arm_urdf` | submodule | `f6642ce` | Current NERO URDF/Xacro model set includes bare arm, gripper, and Revo2 variants. |

Detailed analysis: `docs/upstream/upstream_repo_analysis.md`.

S2 completion is now tracked at two levels:

- S2A host SDK/CAN-only is complete for offline preparation.
- S2B Docker ROS2 Humble is complete for offline preparation.
- CAN interface detection remains deferred to S6 because the real USB-CAN/robot
  is not connected in this session.

Hybrid plan details: `docs/phases/s2_hybrid_host_container_plan.md`.

## S3 Discovery Result

Observed on 2026-06-24:

- Runtime model package: `agx_arm_description`.
- Runtime URDF source: `agx_arm_urdf` submodule commit `f6642ce`.
- Current bare-arm model: `nero/urdf/nero_description.urdf`.
- S3 arm-only model setup remains `arm_type:=nero`, `effector_type:=none` for
  regression checks.
- Bare-arm model passes `xacro`, `check_urdf`, mesh existence checks, and
  `robot_state_publisher` loading.
- Bare-arm model structure: robot `nero`, 9 links, 8 joints, chain
  `world -> base_link -> link1 -> ... -> link7`.
- Gripper and Revo2/dexterous-hand model variants also pass `xacro` and
  `check_urdf`; Revo2 is now active only in S14-specific read-only checks.
- RViz GUI verification succeeded from the real desktop terminal:
  `rviz2` started, OpenGL `4.5` was reported, and the model segments
  `base_link`, `link1` through `link7`, and `world` were loaded.
- The launch was stopped with Ctrl-C, and `joint_state_publisher`,
  `robot_state_publisher`, and `rviz2` all exited cleanly.
- Temporary X11 permission was revoked with `xhost -local:root`; final `xhost`
  output allowed only `SI:localuser:lv-robotics`.
- URDF `joint2` limit is `-99.69..99.69 deg`, while the manual records J2 as
  `-15..190 deg`. Treat this as a zero/mapping discrepancy to verify with real
  Web/CAN/SDK/ROS feedback before relying on ROS limits for safety.

Detailed analysis: `docs/phases/s3_model_validation.md`.

## S4/S5 Initial Power-On And Web Evidence

Observed from `docs/evidence/pics/S4 上电与 S5 Web 只读验机.png` on 2026-06-24:

- Web page reachable at `http://192.168.31.1/#/welcome`.
- UI title: `松灵机器人`.
- Visible joint tabs: `关节1` through `关节7`.
- Footer shows version `v1.121` and model `7ax`.
- `关节1` page basic information:
  - bus voltage: `23.8 V`
  - bus current: `0.0 A`
  - driver temperature: `29.0 degC`
  - motor temperature: `22.0 degC`
- `关节1` status fields visible:
  - undervoltage: `否`
  - motor overtemperature: `否`
  - overcurrent: `否`
  - driver overtemperature: `否`
  - collision protection: `否`
  - driver error: `否`
  - driver disabled: `是`
  - stall protection: `否`

Interpretation:

- `7ax` and tabs `关节1` through `关节7` match one NERO 7-axis arm.
- `驱动失能: 是` is expected before deliberate enable; do not click `使能` yet.
- The site has a second physical arm, so it must be treated as a separate
  controller/IP/device.

## S5 Dual-Arm Network Evidence

Observed from `docs/evidence/pics/网络配置页面截图.png`, user report on 2026-06-24, and user
update on 2026-06-25:

- The site has two NERO arms with independent power.
- Arm A and Arm B both passed Web read-only checks.
- Arm A network configuration page is reachable at
  `http://192.168.31.1/#/settings/sys`.
- Earlier Arm A hotspot name visible in the screenshot: `agx-7ax-xin`.
- Arm A hotspot password was visible in the original screenshot; the value is
  intentionally omitted from tracked text and must be read from the lab credential store.
- Arm A hotspot channel visible in the screenshot: `9`.
- Current Arm A hotspot: `agx-7ax-armA`.
- Current Arm B hotspot: `agx-7ax-armB`.
- The host can connect to only one arm Wi-Fi hotspot at a time with its built-in
  Wi-Fi adapter. This does not block dual-arm CAN/ROS control because the
  planned control path is two independent USB-CAN interfaces, not Wi-Fi.
- The network-port configuration form is visible, but no committed wired IP
  value is proven by the screenshot.

Current dual-arm decision:

- S5 is complete for both arms.
- Continue to S6 dual-arm CAN read-only.
- Do not use simultaneous ROS control until both arms have independent CAN,
  SDK, and ROS feedback paths.
- Detailed plan: `docs/phases/s5_dual_arm_network_plan.md`.
  Next CAN/ROS plan: `docs/phases/s6_dual_arm_can_ros_plan.md`.
