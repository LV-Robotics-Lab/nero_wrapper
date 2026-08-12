# NERO Deployment Log

This file records actual deployment and debugging steps. It is the durable
history of what was done, what was observed, and what changed.

## 2026-06-24 - S0/S1 Baseline And Agent Rules

Phase: S0 资料基线 / S1 安全与场地

Goal:
Create a working rule set before entering S2 so future setup steps remain
faithful to local documents, verified facts, and observed results.

Action:
Added `agent.md` as the operating rule file for future deployment work.

Commands / evidence:
Local project already contains the user manual text, CAN protocol, CAD assets,
and key manual images under `docs/` and `docs/evidence/pics/`.

Result:
S0 is complete. S1 is complete for planning, with final physical checks required
before any power-on or robot motion.

Deployment choices:
Current bring-up remains bare-arm first. Dexterous hand installation is deferred
to S11. Initial ROS `effector_type` remains `none`.

Files changed:
`agent.md`, `docs/status/deployment_log.md`, `README.md`,
`docs/phases/机器人部署与调试行动路线.md`.

Verification:
Passed lightweight checks:

- `bash -n scripts/check_environment.sh`
- `bash -n scripts/activate_can.sh`
- Python AST parse for `examples/nero_read_state.py`
- `rg` check confirmed `agent.md`, `deployment_log.md`, and route links are present.

Route updates:
The action route now includes the agent operating requirement: after every
deployment step, record evidence and correct the route.

Open risks:
S2 host dependencies are not installed yet: ROS2, colcon, ethtool, python-can,
pyAgxArm, and agx_arm_ros workspace remain pending.

Next:
Enter S2 主机环境 after reviewing this agent rule file.

## 2026-06-24 - S2.1 Host Environment Discovery

Phase: S2 主机环境

Goal:
Check whether the current machine can be used as the ROS2/SDK deployment host
for NERO.

Action:
Ran the local environment check and additional read-only host diagnostics.

Commands / evidence:

- `bash scripts/check_environment.sh`
- `lsb_release -a`
- `python3 --version`
- `pip3 --version`
- `ls /opt/ros`
- `apt-cache policy ros-humble-ros-base ros-jazzy-ros-base ros-foxy-ros-base python3-colcon-common-extensions ethtool python3-can`
- `/usr/bin/python3 --version`
- `which python3`
- `which pip3`
- `printenv PATH`
- ROS REP 2000 was checked as upstream evidence for ROS distribution target
  platforms.

Result:

- OS is Ubuntu 20.04.6 LTS (`focal`).
- No ROS installation exists under `/opt/ros`.
- `ros2` is missing.
- `colcon` is missing.
- `ethtool` is missing.
- `python-can` is not importable.
- `pyAgxArm` is not importable.
- `agx_arm_ros` and `pyAgxArm` are not cloned under `~/agx_arm_ws/src`.
- Current shell `python3` and `pip3` resolve to Miniconda Python 3.13.
- System Python is `/usr/bin/python3`, version 3.8.10.
- Ubuntu apt currently shows packages for `ethtool` and `python3-can`, but no
  visible package candidate for `ros-humble-ros-base`, `ros-jazzy-ros-base`, or
  `python3-colcon-common-extensions`.
- ROS REP 2000 lists Humble as Tier 1 on Ubuntu Jammy 22.04, with Ubuntu Focal
  20.04 only Tier 3/source support.
- ROS REP 2000 lists Jazzy as Tier 1 on Ubuntu Noble 24.04.

Deployment choices:
No install was performed. S2 now needs an explicit ROS host strategy before
installing dependencies or cloning/building the ROS workspace.

Files changed:
`docs/status/deployment_log.md`, `docs/status/current_bringup_status.md`,
`docs/phases/机器人部署与调试行动路线.md`.

Verification:
Read-only diagnostics completed successfully. Environment check correctly
reports S2 blockers.

Route updates:
The route is corrected to mark Ubuntu 20.04 + Conda Python 3.13 as a blocker for
the default Humble/Jazzy path. S2 now requires choosing a supported ROS host
strategy.

Open risks:

- Upstream `agx_arm_ros` route targets Humble/Jazzy, while the current OS is
  Ubuntu 20.04.
- Conda Python 3.13 is first in `PATH`; ROS apt work should use system Python in
  a clean shell.
- Installing packages on this machine may create a partially supported ROS setup
  if the OS strategy is not decided first.

Next:
Choose the S2 host strategy: recommended Ubuntu 22.04 + ROS2 Humble, alternative
Ubuntu 24.04 + ROS2 Jazzy, or an isolated container/VM strategy if the host must
remain Ubuntu 20.04.

## 2026-06-24 - S2.2 Environment Check Script Correction

Phase: S2 主机环境

Goal:
Make the environment checker expose the Python environment risk discovered
during S2.1.

Action:
Updated `scripts/check_environment.sh` to print the active `python3` path, active
`pip3` path, and `/usr/bin/python3` version. It now warns if `python3` resolves
to Conda/Miniconda/Anaconda.

Commands / evidence:

- `bash -n scripts/check_environment.sh`
- `bash scripts/check_environment.sh`

Result:
The script reports:

- active `python3`: `/home/lv-robotics/miniconda3/bin/python3`
- active `pip3`: `/home/lv-robotics/miniconda3/bin/pip3`
- system Python: `Python 3.8.10`
- warning: ROS apt work should use a clean system Python shell

Deployment choices:
No ROS install was performed. The S2 host strategy remains undecided.

Files changed:
`scripts/check_environment.sh`, `docs/status/deployment_log.md`.

Verification:
`bash -n scripts/check_environment.sh` passed. Running the check reports the
expected S2 blockers and the new Conda Python warning.

Route updates:
No additional route structure change was needed beyond the existing S2 host
strategy blocker. The script now enforces that blocker more visibly.

Open risks:
Same as S2.1.

Next:
Choose the S2 host strategy before installing ROS or cloning/building the ROS
workspace.

## 2026-06-24 - S2.3 Noetic Strategy Evaluation

Phase: S2 主机环境

Goal:
Evaluate whether ROS Noetic can be selected for the NERO bring-up because the
current host is Ubuntu 20.04.

Action:
Checked official ROS distribution metadata and the upstream AgileX ROS package
direction.

Commands / evidence:

- ROS rosdistro index reports `noetic` as `distribution_type: ros1` and
  `distribution_status: end-of-life`.
- ROS REP 3 lists Noetic as May 2020 - May 2025, with required support for
  Ubuntu Focal 20.04 and Python 3.8.
- Upstream `agx_arm_ros` README identifies the current package as an AgileX ROS2
  driver, shows Humble/Jazzy passing, and describes support for Piper/Nero.

Result:
Noetic is technically compatible with the current Ubuntu 20.04 host, but it is
ROS1 and already end-of-life. It is not the recommended NERO bring-up path unless
there is a hard legacy ROS1 integration requirement.

Deployment choices:
No install was performed. Recommended S2 strategy remains Ubuntu 22.04 + ROS2
Humble, unless the project explicitly chooses a legacy ROS1 route.

Files changed:
`docs/status/deployment_log.md`, `docs/phases/机器人部署与调试行动路线.md`,
`docs/status/current_bringup_status.md`.

Verification:
Evaluation is documented. No system state was changed.

Route updates:
The S2 route now includes a Noetic decision note: possible for legacy ROS1 only,
not recommended for the default NERO setup.

Open risks:
Choosing Noetic would require finding or maintaining a ROS1-compatible NERO
driver path, remapping expected topics/interfaces, and accepting EOL ROS
infrastructure risk.

Next:
User decision: keep recommended Humble route or intentionally switch to a legacy
Noetic route with a separate validation plan.

## 2026-06-24 - S2.4 Upstream Repository Clone And ROS Strategy Correction

Phase: S2 主机环境

Goal:
Clone the user-specified upstream repositories into the project workspace, read
their current contents, and decide the most reasonable ROS strategy from
repository evidence rather than assumption.

Action:
Created local upstream evidence clones under `upstream/`:

- `agx_arm_ros`
- `pyAgxArm`
- `piper_ros`
- `agx_arm_ros/src/agx_arm_description/agx_arm_urdf` submodule

Commands / evidence:

- `git clone -b humble_beta1 https://github.com/agilexrobotics/piper_ros.git upstream/piper_ros`
- `git clone https://github.com/agilexrobotics/pyAgxArm.git upstream/pyAgxArm`
- `git clone -b ros2 https://github.com/agilexrobotics/agx_arm_ros.git upstream/agx_arm_ros`
- `git -C upstream/agx_arm_ros submodule update --init --recursive`
- `sed` review of upstream README, `package.xml`, `CMakeLists.txt`, launch files,
  install script, SDK setup file, and URDF README.

Observed repository states:

| Repository | Branch | Commit | Key observation |
| --- | --- | --- | --- |
| `agx_arm_ros` | `ros2` | `c73d33f` | README identifies it as the AgileX ROS2 driver, with Humble/Jazzy pass status and NERO support. |
| `pyAgxArm` | `master` | `a226840` | SDK supports Ubuntu 18.04/20.04/22.04/24.04 and Python 3.6+, requires `python-can>=3.3.4`. |
| `piper_ros` | `humble_beta1` | `2dc30fc` | Requested `nero_description` package is `ament_cmake`/`rviz2` model description, not a NERO control driver. |
| `agx_arm_urdf` submodule | submodule | `f6642ce` | Contains current NERO URDF/Xacro assets for bare arm, gripper, and Revo2 variants. |

Result:
The default NERO ROS deployment route should remain ROS2, not Noetic. The most
reasonable ROS host remains Ubuntu 22.04 + ROS2 Humble, with Ubuntu 24.04 +
ROS2 Jazzy as an alternative. The current Ubuntu 20.04 host can still be used
for SDK/CAN-only readout preparation because `pyAgxArm` supports Ubuntu 20.04,
but it should not be treated as a completed ROS environment.

Deployment choices:

- Split S2 into S2A SDK/CAN-only and S2B ROS host preparation.
- Keep initial ROS parameters as `arm_type:=nero`, `effector_type:=none` for
  the bare-arm phase.
- Defer dexterous hand configuration to S11.
- Do not choose Noetic unless there is a hard legacy ROS1 requirement and a
  separate validation plan is created.

Files changed:
`docs/upstream/upstream_repo_analysis.md`, `docs/status/deployment_log.md`,
`docs/status/current_bringup_status.md`, `docs/phases/机器人部署与调试行动路线.md`,
`README.md`, `docs/status/setup_framework.md`, `docs/status/bringup_checklist.md`,
`config/nero.env`.

Verification:
Repository clones and submodule are present locally. Read-only checks confirmed:

- `agx_arm_ros` is a ROS2/ament/rclpy workspace.
- `piper_ros` NERO path is an ament model package.
- `pyAgxArm` can support SDK-only work on Ubuntu 20.04 if Python dependencies
  meet version requirements.

Route updates:
The action route now records the upstream clone evidence, the ROS2 strategy, the
Noetic correction, and the S2A/S2B split. The checklist S2/S3/S4 numbering was
also corrected to match the main route.

Open risks:

- Current host still lacks `ros2`, `colcon`, `ethtool`, `python-can`, and
  `pyAgxArm` import.
- Current shell still resolves `python3`/`pip3` to Miniconda Python 3.13.
- Ubuntu Focal apt candidate for `python3-can` is `3.3.2`, below the SDK
  requirement, so SDK-only setup needs pip or another isolated dependency path.
- ROS2 workspace build has not been attempted because a supported ROS2 host has
  not yet been selected.

Next:
Choose whether to proceed with S2A on this Ubuntu 20.04 host first, or prepare a
Ubuntu 22.04 + ROS2 Humble host for S2B.

## 2026-06-24 - S2.5 Upstream Repository Role Clarification

Phase: S2 主机环境

Goal:
Before choosing the next S2 track, clarify what the three user-provided GitHub
repositories are, what role each one plays, and how each should be used later.

Action:
Updated `agent.md` and the main action route with explicit repository role
boundaries.

Commands / evidence:

- Re-read `agent.md`.
- Re-read `docs/phases/机器人部署与调试行动路线.md`.
- Re-read `docs/upstream/upstream_repo_analysis.md`.
- Used the local upstream clone evidence recorded in S2.4.

Result:
The project now treats the three repositories as distinct layers:

| Repository | Role | Later use |
| --- | --- | --- |
| `agx_arm_ros` | Main ROS2 integration/control workspace for NERO. | Use for S2B ROS host setup, S3 model display, S8 ROS read-only feedback, and later MoveIt/application work. |
| `pyAgxArm` | Python SDK and CAN hardware access layer. | Use for S2A SDK/CAN-only preparation and S7 read-only state checks; no motion before motion gates. |
| `piper_ros` | Reference source for the user-provided NERO URDF path on branch `humble_beta1`. | Use only for model cross-checking and historical comparison, not as the default NERO control workspace. |

Deployment choices:

- `agx_arm_ros` remains the default ROS route.
- `pyAgxArm` remains the SDK-only route for current Ubuntu 20.04 preparation.
- `piper_ros` is demoted from possible runtime route to reference/model evidence
  unless a separate validation plan is written.
- `agx_arm_ros` submodule `agx_arm_urdf` is the preferred runtime model source
  for the ROS2 route.

Files changed:
`agent.md`, `docs/phases/机器人部署与调试行动路线.md`, `docs/status/deployment_log.md`.

Verification:
Role boundaries are present in both `agent.md` and the main route. No install,
build, hardware connection, or robot command was executed.

Route updates:
The main route now has an "上游仓库职责边界" section and S2 now points back to
that boundary while preserving commit-level evidence.

Open risks:
No new technical risk. S2 environment blockers remain unchanged:
`ros2`, `colcon`, `ethtool`, `python-can`, and `pyAgxArm` import are still not
ready on the current host.

Next:
Choose whether to proceed with S2A SDK/CAN-only preparation on this host, or
prepare the S2B ROS2 Humble/Jazzy host.

## 2026-06-24 - S2.6 Shared Host Hybrid Deployment Plan

Phase: S2 主机环境

Goal:
Adopt a practical deployment plan because this Ubuntu 20.04 computer is the
only NERO deployment machine and cannot be reinstalled or upgraded due to other
users.

Action:
Selected and documented the hybrid host/container plan:

- Host Ubuntu 20.04 remains in place for SDK/CAN-only work.
- Docker runs Ubuntu 22.04 + ROS2 Humble for the official `agx_arm_ros` route.
- The project will use `sudo docker` initially instead of adding the operator to
  the `docker` group.

Commands / evidence:

- `command -v docker` returned missing.
- `command -v podman` returned missing.
- `command -v candump` returned `/usr/bin/candump`.
- `command -v cansend` returned `/usr/bin/cansend`.
- `command -v ethtool` returned missing.
- `/usr/bin/python3 -m venv --help` works.
- `apt-cache policy docker.io ethtool python3-venv python3-pip` showed
  available `docker.io` and `ethtool` packages on Ubuntu Focal.

Result:
The selected S2 strategy is now:

- S2A: host SDK/CAN-only with a project-local venv using `/usr/bin/python3`.
- S2B: Docker image `nero-humble:local` based on ROS2 Humble desktop, used for
  `agx_arm_ros`, RViz, ROS topics, and later MoveIt.

Deployment choices:

- No OS reinstall or in-place upgrade.
- No native ROS2 Humble/Jazzy installation on Ubuntu 20.04.
- No Noetic default route.
- System-level changes are limited to `docker.io` and `ethtool`, with risk and
  necessity to be stated before installation.
- Docker group membership is not changed by default.

Files changed:
`config/nero.env`, `docker/humble/Dockerfile`, `docker/humble/entrypoint.sh`,
`scripts/build_humble_container.sh`, `scripts/run_humble_container.sh`,
`scripts/setup_host_sdk_venv.sh`, `docs/phases/s2_hybrid_host_container_plan.md`,
`docs/phases/机器人部署与调试行动路线.md`, `docs/status/current_bringup_status.md`,
`docs/status/bringup_checklist.md`, `docs/status/setup_framework.md`, `README.md`,
`agent.md`, `docs/status/deployment_log.md`.

Verification:
Pending after script syntax checks and environment check. No install, Docker
build, ROS build, hardware connection, or robot command has been executed yet.

Route updates:
The main route now treats the hybrid host/container path as the selected S2
strategy. S2 acceptance criteria now separate host SDK/CAN-only readiness from
Docker ROS2 Humble readiness.

Open risks:

- Docker is not installed yet.
- `ethtool` is not installed yet.
- Docker image build requires network and package downloads.
- RViz GUI access through X11 may need separate display permission handling.
- Current shell still resolves `python3` to Conda, so host SDK setup must use
  `/usr/bin/python3`.

Next:
Run syntax checks. Then request approval for the system-level installation of
`docker.io` and `ethtool`, explicitly stating risk and necessity.

## 2026-06-24 - S2.7 System Install Approval Blocked

Phase: S2 主机环境

Goal:
Install the two required system packages for the selected hybrid plan:
`docker.io` and `ethtool`.

Action:
Requested escalated execution of:

```bash
sudo apt-get install -y docker.io ethtool
```

Commands / evidence:

- The request stated the necessity of Docker for Ubuntu 22.04/ROS2 Humble
  container deployment without reinstalling the shared Ubuntu 20.04 host.
- The request stated the risk that Docker installs a persistent high-privilege
  daemon/service and that Docker control is effectively high privilege.
- The request stated the lower risk of `ethtool` as a diagnostic utility.

Result:
The escalation was rejected by safety policy because explicit user approval is
required after stating the concrete risks of installing Docker on a shared
machine. No package was installed.

Deployment choices:
No change. Continue to use the selected hybrid plan, but block system package
installation until the user explicitly approves this exact system-level change.

Files changed:
`docs/status/deployment_log.md`.

Verification:
No installation occurred. Current S2 failures remain `docker` and `ethtool`
missing.

Route updates:
No route change. The route already records the risk and necessity of Docker and
`ethtool`.

Open risks:
Docker installation remains a shared-host security decision.

Next:
Ask the user for explicit approval to install `docker.io` and `ethtool`.

## 2026-06-24 - S2.8 Hybrid Environment Installation And Build

Phase: S2 主机环境

Goal:
Complete the selected hybrid host/container S2 environment on the shared Ubuntu
20.04 machine.

Action:
After explicit user approval, installed required host packages, prepared the
host SDK venv, built the ROS2 Humble Docker image, cloned the official ROS
workspace, and built `agx_arm_ros` in the container.

Commands / evidence:

- `sudo apt-get update`
- `sudo apt-get install -y docker.io ethtool`
- `sudo docker info`
- `bash scripts/check_environment.sh`
- `sudo apt-get install -y python3.8-venv`
- `bash scripts/setup_host_sdk_venv.sh`
- `bash scripts/build_humble_container.sh`
- `bash scripts/run_humble_container.sh ...`
- `git clone -b ros2 --recurse-submodules https://github.com/agilexrobotics/agx_arm_ros.git /home/lv-robotics/agx_arm_ws/src/agx_arm_ros`
- `git clone https://github.com/agilexrobotics/pyAgxArm.git /home/lv-robotics/agx_arm_ws/src/pyAgxArm`
- Container: `cd /root/agx_arm_ws/src/pyAgxArm && pip3 install .`
- Container: `cd /root/agx_arm_ws && colcon build`
- `sudo chown -R lv-robotics:lv-robotics /home/lv-robotics/agx_arm_ws/build /home/lv-robotics/agx_arm_ws/install /home/lv-robotics/agx_arm_ws/log`

Result:

- Host package install succeeded.
- Docker version: `26.1.3`.
- Docker daemon check passed via `sudo docker info`.
- `ethtool` version: `5.4`.
- Current user groups remain `lv-robotics nogroup`; the user was not added to
  the `docker` group.
- Host SDK venv `.venv/nero-sdk` is ready.
- Host SDK venv imports `python-can=4.5.0` and `pyAgxArm`.
- Docker image `nero-humble:local` exists, image ID `cd76a30091d2`, size about
  `3.65GB`.
- Container reports Ubuntu `22.04.5 LTS`, `ROS_DISTRO=humble`, `ros2`,
  `colcon`, and `python-can=4.6.1`.
- ROS workspace build completed: 5 packages finished.
- Built packages include `agx_arm_msgs`, `agx_arm_description`, `pyAgxArm`,
  `agx_arm_ctrl`, and `agx_arm_moveit`.
- `pyAgxArm` emitted packaging warnings about excluded directories/cache files;
  this did not fail the build.
- Container install-space verification passed:
  `agx_arm_ctrl`, `agx_arm_description`, `agx_arm_moveit`, and `pyAgxArm`
  import are available.

Deployment choices:

- Keep `sudo docker` strategy; do not add `lv-robotics` to the `docker` group.
- Keep host-native ROS2 absent; ROS2/colcon are expected only inside the Humble
  container.
- Use `.venv/nero-sdk` for host SDK/CAN-only checks.
- Use `~/agx_arm_ws` as the mounted ROS workspace for container builds.

Files changed:
`.dockerignore`, `scripts/setup_host_sdk_venv.sh`,
`scripts/fix_ros_ws_permissions.sh`, `docs/status/deployment_log.md`,
`docs/status/current_bringup_status.md`, `docs/phases/机器人部署与调试行动路线.md`,
`docs/phases/s2_hybrid_host_container_plan.md`, `README.md`.

Verification:

- `bash scripts/check_environment.sh` exits with 0 failures.
- Container verification reports:
  - `ROS_DISTRO=humble`
  - `/opt/ros/humble/bin/ros2`
  - `/usr/bin/colcon`
  - `python-can 4.6.1`
  - `Ubuntu 22.04.5 LTS`
- ROS package prefix checks passed for `agx_arm_ctrl`, `agx_arm_description`,
  and `agx_arm_moveit`.

Route updates:
S2 is now marked complete for offline preparation. The next route phase is S3
离线模型. CAN interface detection is deferred to S6 because real hardware was
not connected.

Open risks:

- Docker image is large, about `3.65GB`.
- RViz/X11 GUI has not been tested yet.
- CAN interface is not present because the USB-CAN/robot is not connected.
- Container builds may leave host workspace artifacts with mapped ownership;
  use `bash scripts/fix_ros_ws_permissions.sh` if needed.

Next:
Proceed to S3 离线模型 in the ROS2 Humble container. Do not connect or move real
hardware yet.

## 2026-06-24 - S3.1 Offline NERO Model Validation

Phase: S3 离线模型

Goal:
Validate the NERO runtime model in the Docker ROS2 Humble environment before any
real hardware connection or motion.

Action:
Inspected `agx_arm_description` launch/model files, expanded NERO URDF/Xacro
models, ran `check_urdf`, verified mesh references, and tested
`robot_state_publisher` loading.

Commands / evidence:

- Read `agx_arm_description/launch/display.launch.py`.
- Listed NERO model files under
  `agx_arm_urdf/nero/urdf` and `agx_arm_urdf/nero/meshes`.
- Container: `xacro` expansion for:
  - `nero_description.urdf`
  - `nero_with_gripper_description.xacro`
  - `nero_with_left_revo2_description.xacro`
  - `nero_with_right_revo2_description.xacro`
  - `nero_with_revo2_flange_description.xacro`
- Container: `check_urdf` for the same models.
- Container: XML parse for links, joints, joint origins, axes, limits, and mesh
  references.
- Container: `robot_state_publisher` load test using a temporary parameter file.
- Container: `display.launch.py arm_type:=nero effector_type:=none gui:=false
  control:=true` with `QT_QPA_PLATFORM=offscreen`.

Result:

- Runtime model source is `agx_arm_description` using `agx_arm_urdf` submodule
  commit `f6642ce`.
- Current bare-arm model is `nero/urdf/nero_description.urdf`.
- All checked NERO models expand with `xacro` and pass `check_urdf`.
- Bare-arm model has robot name `nero`, 9 links, 8 joints, and chain:
  `world -> base_link -> link1 -> link2 -> link3 -> link4 -> link5 -> link6 -> link7`.
- Bare-arm model has 16 mesh references and 0 missing mesh files.
- `robot_state_publisher` successfully loaded segments `world`, `base_link`,
  and `link1` through `link7`.
- `display.launch.py` supports `arm_type:=nero`, `effector_type:=none`,
  `gui`, `control`, `follow`, `tcp_offset`, and related topic arguments.
- `display.launch.py` always starts RViz; `gui:=false` disables
  `joint_state_publisher_gui`, not RViz.
- RViz failed in the current shell because X11 display `:1` is not accessible:
  `No protocol specified`, `Unable to open display`, and OGRE
  `RenderingAPIException`.

Deployment choices:

- Keep the active model as bare arm: `arm_type:=nero`, `effector_type:=none`.
- Do not enable gripper/Revo2/dexterous-hand models until S11.
- Treat S3 as non-GUI complete, with RViz GUI verification pending in a real
  desktop session.
- Keep manual joint limits as the safety source until live feedback confirms
  the URDF/mechanical angle mapping.

Files changed:
`docs/phases/s3_model_validation.md`, `docs/status/deployment_log.md`,
`docs/status/current_bringup_status.md`, `docs/phases/机器人部署与调试行动路线.md`,
`docs/status/bringup_checklist.md`.

Verification:

- `xacro` succeeded for 5 NERO models.
- `check_urdf` succeeded for 5 NERO models.
- Mesh reference check passed: `16` references, `0` missing.
- `robot_state_publisher` loaded the bare-arm model.
- Launch test confirmed model load but RViz failed only at X11 display access.

Route updates:
S3 now records non-GUI model validation, the RViz/X11 blocker, and a joint-limit
mapping finding for J2.

Open risks:

- RViz visual inspection is not complete because the current shell cannot access
  the desktop X11 display.
- URDF `joint2` limit is approximately `-99.69..99.69 deg`, while the local
  manual records J2 as `-15..190 deg`. This likely reflects a zero/mapping
  convention difference, but it must be confirmed later with Web/CAN/SDK/ROS
  feedback on the real arm.

Next:
Retry RViz from a real desktop session, or explicitly accept non-GUI S3
validation as sufficient to prepare S4. Do not connect or move real hardware
until the next phase gate is clear.

## 2026-06-24 - S3.2 Desktop RViz GUI Validation

Phase: S3 离线模型

Goal:
Complete the RViz GUI portion of S3 from a real desktop terminal.

Action:
The operator ran the Docker Humble RViz launch from the desktop session:

```bash
bash scripts/run_humble_container.sh --allow-xhost \
  ros2 launch agx_arm_description display.launch.py \
  arm_type:=nero \
  effector_type:=none \
  gui:=false \
  control:=true
```

Commands / evidence:

- `--allow-xhost` added local root access:
  `non-network local connections being added to access control list`.
- `joint_state_publisher`, `robot_state_publisher`, and `rviz2` started.
- `robot_state_publisher` reported segments:
  `base_link`, `link1`, `link2`, `link3`, `link4`, `link5`, `link6`, `link7`,
  and `world`.
- `rviz2` reported:
  - `Stereo is NOT SUPPORTED`
  - `OpenGl version: 4.5 (GLSL 4.5)`
- The launch was stopped with Ctrl-C.
- `joint_state_publisher`, `robot_state_publisher`, and `rviz2` finished
  cleanly.
- The operator revoked X11 permission:

```bash
xhost -local:root
xhost
```

- Final `xhost` output:
  `access control enabled, only authorized clients can connect` and
  `SI:localuser:lv-robotics`.

Result:
S3 RViz GUI validation is complete. The earlier RViz failure was confirmed to be
a non-desktop X11 authorization issue, not a model/URDF issue.

Deployment choices:

- Keep current active offline model as bare arm:
  `arm_type:=nero`, `effector_type:=none`.
- Proceed to S4 机械与电气连接.
- No real robot was connected and no motion command was issued during S3.

Files changed:
`docs/status/deployment_log.md`, `docs/status/current_bringup_status.md`,
`docs/phases/s3_model_validation.md`, `docs/phases/机器人部署与调试行动路线.md`,
`docs/status/bringup_checklist.md`.

Verification:
The operator-provided terminal log satisfies the S3 RViz GUI acceptance
criteria: RViz started, OpenGL initialized, robot segments loaded, processes
exited cleanly, and temporary X11 permission was revoked.

Route updates:
S3 is now marked complete. The current route advances to S4 mechanical and
electrical connection.

Open risks:

- J2 URDF/manual angle mapping discrepancy remains open until live feedback
  comparison in S6-S8.
- No hardware connection has been verified yet.

Next:
Begin S4 with physical fixation, cable identification, CAN wiring, power
inspection, and final pre-power safety checks. Do not issue motion commands.

## 2026-06-24 - S4/S5.1 Power-On And Web Read-Only Observation

Phase: S4 机械与电气连接 / S5 Web 验机

Goal:
Record the first successful power-on and determine what the Web page currently
proves before moving to CAN/SDK/ROS hardware checks.

Action:
Reviewed the user-provided Web screenshot saved at
`docs/evidence/pics/S4 上电与 S5 Web 只读验机.png`.

Commands / evidence:

- Web URL visible: `http://192.168.31.1/#/welcome`.
- UI title: `松灵机器人`.
- Current account: `admin`.
- Visible joint tabs: `关节1` through `关节7`.
- Footer: version `v1.121`, model `7ax`.
- `关节1` visible values:
  - bus voltage `23.8 V`
  - bus current `0.0 A`
  - driver temperature `29.0 degC`
  - motor temperature `22.0 degC`
  - undervoltage `否`
  - motor overtemperature `否`
  - overcurrent `否`
  - driver overtemperature `否`
  - collision protection `否`
  - driver error `否`
  - driver disabled `是`
  - stall protection `否`

Result:

- Power-on succeeded and the Web UI is reachable.
- The visible UI represents one NERO `7ax` controller/arm with seven joint tabs.
- `驱动失能: 是` is expected before deliberate enable; this is not a fault by
  itself.

Deployment choices:

- Continue S5 as read-only Web validation.
- Do not click `使能`, `清除错误`, motion, zeroing, firmware upgrade, master/slave,
  or dexterous-hand controls yet.
- If a second physical arm is expected, treat it as a separate controller/IP or
  device until documentation or live evidence proves otherwise.

Files changed:
`agent.md`, `docs/status/deployment_log.md`, `docs/status/current_bringup_status.md`,
`docs/phases/机器人部署与调试行动路线.md`, `docs/status/bringup_checklist.md`.

Verification:
The screenshot contains a live Web session, model `7ax`, and readable joint
status fields for `关节1`.

Route updates:
The route no longer says the robot is unconnected. It now records that power-on
and Web access succeeded, and that S5 requires read-only checks for all seven
joint tabs before S6 CAN read-only capture.

Open risks:

- Final S4 wiring/fixation photo evidence is not fully archived yet.
- Only `关节1` status is visible in the screenshot; `关节2` through `关节7` still
  need read-only Web verification.
- Footer version `v1.121` must be clarified as software, firmware, or both
  before choosing the SDK firmware selector.

Next:
Complete S5 Web read-only validation by checking `关节1` through `关节7`, recording
version/status information, and confirming whether the physical setup is a single
arm or includes another independent controller.

## 2026-06-24 - S5.2 Dual-Arm Network Identity Correction

Phase: S5 Web 验机

Goal:
Correct the bring-up route after confirming that the site has two physical NERO
arms, not one.

Action:
Reviewed the new network configuration screenshot
`docs/evidence/pics/网络配置页面截图.png`, checked the local user manual network sections,
and updated the route to treat the system as a two-arm deployment with per-arm
identity checks.

Commands / evidence:

- User report: the site has a second physical arm with independent power.
- User report: the currently connected arm's other seven joint tabs are normal.
- Screenshot: Arm A Web network page at
  `http://192.168.31.1/#/settings/sys`.
- Screenshot: Arm A hotspot name `agx-7ax-xin`.
- Screenshot: Arm A hotspot password was visible; the value is intentionally
  omitted from tracked text.
- Screenshot: Arm A hotspot channel `9`.
- Manual section 4.1: default Wi-Fi SSID pattern `agx-7ax-xx`, Web address
  `192.168.31.1`, and a Web login. Credential values are intentionally omitted.
- Manual section 4.2: default wired controller IP `10.90.0.150`; host must use
  the same subnet, example `10.90.0.153/255.255.255.0`.
- Manual section 7.1/7.2: Web supports network-port configuration and hotspot
  configuration.
- Manual warning: do not set two arms as slave simultaneously, and do not enable
  CAN push on two connected arms simultaneously.

Result:

- The project state is now corrected to a two-arm physical setup.
- Arm A is the currently verified Web arm.
- Arm B requires independent S5 Web read-only verification before any S6 CAN
  work.

Deployment choices:

- Continue one-arm-at-a-time bring-up.
- Do not use simultaneous CAN/ROS until both arms have unique network identities
  and independent CAN paths.
- Use labels Arm A and Arm B until physical left/right installation is confirmed.
- Recommended future wired IP plan, if simultaneous wired Web access is needed:
  Arm A `10.90.0.151`, Arm B `10.90.0.152`, host `10.90.0.153`.

Files changed:
`agent.md`, `config/nero.env`, `docs/phases/s5_dual_arm_network_plan.md`,
`docs/status/deployment_log.md`, `docs/status/current_bringup_status.md`,
`docs/phases/机器人部署与调试行动路线.md`, `docs/status/bringup_checklist.md`.

Verification:
The new screenshot proves the Arm A hotspot configuration page is accessible and
that Arm A has a unique hotspot name `agx-7ax-xin`. The user report confirms all
Arm A joint tabs are normal.

Route updates:
S5 now includes dual-arm identity management. S6 now requires per-arm Web
verification and unique identity before CAN capture. Dual-arm simultaneous CAN
is deferred until independent CAN interfaces are mapped.

Open risks:

- Arm B has not yet been verified through Web.
- Arm B may still share default Wi-Fi/IP identity with Arm A.
- Arm A wired IP is not proven by the screenshot.
- SDK firmware selector is still not final because footer `v1.121` has not been
  tied to the exact SDK firmware selector.

Next:
Physically label Arm A and Arm B. Then power/connect Arm B by itself, complete
the same S5 Web read-only joint/status checks, and set/record a unique hotspot
name before both arms are used in the same environment.

## 2026-06-25 - S5.3 Dual-Arm Web Complete And S6 Plan

Phase: S5 Web 验机 / S6 CAN 只读

Goal:
Record completion of dual-arm Web identity checks and define the next read-only
CAN/ROS direction for future simultaneous dual-arm control.

Action:
Recorded the operator's confirmation that both arms passed Web checks and that
the Wi-Fi hotspots were changed to unique names. Reviewed the ROS2 launch files
for dual-instance support and safety defaults.

Commands / evidence:

- User report: both NERO arms have no observed Web problems.
- User report: Arm A Wi-Fi hotspot is now `agx-7ax-armA`.
- User report: Arm B Wi-Fi hotspot is now `agx-7ax-armB`.
- Source review:
  `start_single_agx_arm.launch.py` has `namespace` and `can_port` arguments.
- Source review:
  `start_single_agx_arm.launch.py` defaults `auto_enable:=true` and
  `control_enabled:=true`.
- Source review:
  `display.launch.py` applies a namespace frame prefix for RViz/model display.
- Source review:
  upstream CAN documentation supports finding USB bus-info and assigning
  deterministic names to multiple CAN modules.

Result:

- S5 is complete for both arms.
- The next phase is S6 dual-arm CAN read-only.
- The selected dual-arm naming plan is:
  - Arm A: Wi-Fi `agx-7ax-armA`, CAN `can_arm_a`, ROS namespace `arm_a`.
  - Arm B: Wi-Fi `agx-7ax-armB`, CAN `can_arm_b`, ROS namespace `arm_b`.

Deployment choices:

- Use two independent official USB-CAN modules or two independent CAN channels.
- Do not put both arms on one CAN bus.
- Do not enable CAN push on two connected arms simultaneously.
- For S8 ROS read-only, explicitly launch with
  `auto_enable:=false control_enabled:=false`.

Files changed:
`agent.md`, `config/nero.env`, `scripts/find_can_ports.sh`,
`scripts/activate_can.sh`, `docs/phases/s6_dual_arm_can_ros_plan.md`,
`docs/status/deployment_log.md`, `docs/status/current_bringup_status.md`,
`docs/phases/s5_dual_arm_network_plan.md`, `docs/phases/机器人部署与调试行动路线.md`,
`docs/status/bringup_checklist.md`.

Verification:
Documentation now records unique Wi-Fi identities for both arms and a read-only
dual-CAN plan. The new `scripts/find_can_ports.sh` wrapper is read-only and
delegates to the upstream CAN discovery script when available.

Route updates:
The route advances from S5 to S6 and replaces single-arm `can0` examples with
`can_arm_a` and `can_arm_b`. S8 examples now use namespaces and disable
auto-enable/control gate for read-only bring-up.

Open risks:

- USB-CAN bus-info for Arm A and Arm B has not been recorded yet.
- CAN feedback has not yet been captured from either arm.
- Footer version `v1.121` still needs to be tied to the SDK firmware selector
  before SDK/ROS conclusions are finalized.

Next:
Connect the two official USB-CAN modules, identify their USB bus-info one at a
time, map them to Arm A/Arm B, activate `can_arm_a` and `can_arm_b`, then run
read-only `candump` on each interface.

## 2026-06-25 - S6.0 Two Official USB-CAN Modules Confirmed

Phase: S6 CAN 只读

Goal:
Record the hardware prerequisite for dual-arm CAN read-only validation.

Action:
Recorded the operator's confirmation that the dual-arm setup uses two official
USB-CAN modules, one module per arm.

Commands / evidence:

- User report: there are two official USB-CAN modules.
- User report: the modules were already used separately while testing each
  arm's Wi-Fi/Web setup.

Result:

- S6 can proceed with the planned dual-interface mapping:
  `can_arm_a` for Arm A and `can_arm_b` for Arm B.

Deployment choices:

- Continue with one CAN bus per physical arm.
- Do not combine both arms on one CAN bus.
- Keep S6 read-only: `find_can_ports`, `activate_can`, `ip link`, and `candump`;
  no `cansend`.

Files changed:
`docs/status/deployment_log.md`, `docs/status/current_bringup_status.md`,
`docs/phases/s6_dual_arm_can_ros_plan.md`.

Verification:
Hardware availability is confirmed by operator report; actual USB bus-info and
feedback frames are still pending.

Route updates:
No phase jump. S6 remains the active phase; the next concrete step is bus-info
mapping and read-only feedback capture.

Open risks:

- USB bus-info for each module has not been recorded yet.
- It is not yet proven that `can_arm_a` feedback stops only when Arm A CAN is
  disconnected and `can_arm_b` feedback stops only when Arm B CAN is disconnected.

Next:
Run read-only CAN discovery, map each USB-CAN module to Arm A/Arm B, activate
the deterministic interface names, then capture `candump` output from each
interface.

## 2026-06-25 - S6.1 USB-CAN Bus-Info Mapping

Phase: S6 CAN 只读

Goal:
Map each official USB-CAN module to the correct physical arm before activating
deterministic CAN interface names.

Action:
Recorded operator-provided output from `bash scripts/find_can_ports.sh` with one
module connected at a time.

Commands / evidence:

Arm B:

```text
Both ethtool and can-utils are installed.
Interface can0 is connected to USB port 1-11:1.0
```

Arm A:

```text
Both ethtool and can-utils are installed.
Interface can0 is connected to USB port 1-5:1.0
```

Result:

- Arm A USB-CAN bus-info: `1-5:1.0`.
- Arm B USB-CAN bus-info: `1-11:1.0`.

Deployment choices:

- Activate Arm A as `can_arm_a` from bus-info `1-5:1.0`.
- Activate Arm B as `can_arm_b` from bus-info `1-11:1.0`.
- Keep the modules in the same physical USB ports unless the mapping is
  rediscovered and updated.

Files changed:
`config/nero.env`, `docs/status/deployment_log.md`,
`docs/status/current_bringup_status.md`, `docs/phases/s6_dual_arm_can_ros_plan.md`.

Verification:
The mapping is verified by read-only `find_can_ports.sh` output. Interface
activation and CAN feedback capture are still pending.

Route updates:
S6 now has concrete USB bus-info values for Arm A and Arm B.

Open risks:

- If a USB-CAN module is moved to a different host USB port, the bus-info mapping
  can change.
- Both modules have not yet been activated simultaneously.
- No `candump` feedback has been captured yet.

Next:
Plug both modules into the mapped USB ports, verify both bus-info values are
visible at the same time, activate `can_arm_a` and `can_arm_b`, and run read-only
`candump`.

## 2026-06-25 - S6.2 CAN Interfaces Up And Frames Reported

Phase: S6 CAN 只读

Goal:
Record the first successful dual USB-CAN interface activation and clarify the
role of Wi-Fi in future dual-arm control.

Action:
Recorded operator-provided `ip -details link show` and
`find_can_ports.sh` output, plus the operator report that CAN capture produced
normal frames.

Commands / evidence:

Arm B:

```text
21: can_arm_b: <NOARP,UP,LOWER_UP,ECHO> mtu 16 qdisc pfifo_fast state UP mode DEFAULT group default qlen 10
    link/can
    can state ERROR-ACTIVE restart-ms 0
      bitrate 1000000 sample-point 0.750
```

Arm A:

```text
20: can_arm_a: <NOARP,UP,LOWER_UP,ECHO> mtu 16 qdisc pfifo_fast state UP mode DEFAULT group default qlen 10
    link/can
    can state ERROR-ACTIVE restart-ms 0
      bitrate 1000000 sample-point 0.750
```

CAN discovery:

```text
Both ethtool and can-utils are installed.
Interface can_arm_a is connected to USB port 1-5:1.0
Interface can_arm_b is connected to USB port 1-11:1.0
```

Operator report:

- CAN capture produced normal frames.
- Arm A uses the vertical USB port.
- Arm B uses the horizontal USB port.

Result:

- `can_arm_a` is UP, ERROR-ACTIVE, bitrate `1000000`.
- `can_arm_b` is UP, ERROR-ACTIVE, bitrate `1000000`.
- USB mapping is stable with both modules visible at the same time.
- Normal CAN frames were observed by the operator.

Deployment choices:

- Continue using USB-CAN as the dual-arm real-time control path.
- Treat Wi-Fi as a Web configuration/status path only.
- The host's single Wi-Fi connection does not block future dual-arm CAN/ROS
  coordination.

Files changed:
`config/nero.env`, `docs/status/deployment_log.md`,
`docs/status/current_bringup_status.md`, `docs/phases/s6_dual_arm_can_ros_plan.md`,
`docs/phases/机器人部署与调试行动路线.md`, `docs/status/bringup_checklist.md`.

Verification:
Interface-level S6 checks passed. Detailed frame ID evidence should still be
archived before closing S6 completely if not already saved.

Route updates:
The route now records the USB physical orientation, confirms both CAN interfaces
are UP at 1 Mbps, and clarifies that Wi-Fi is not the dual-arm control path.

Open risks:

- The actual `candump` frame lines were not pasted into the log; exact frame IDs
  are based on operator report so far.
- SDK firmware selector is still pending.

Next:
Archive a short `candump` sample from each interface if possible, then proceed
to S7 SDK read-only on `can_arm_a` and `can_arm_b`.

## 2026-06-25 - S7.1 SDK Read-Only Passed And S8 Prepared

Phase: S7 SDK 只读 / S8 ROS 只读

Goal:
Record S7 completion and prepare a safe dual-arm ROS read-only launch path.

Action:
Recorded the operator's confirmation that S7 passed, reviewed the ROS container
entrypoint and launch requirements, and added a project wrapper for dual-arm ROS
read-only startup.

Commands / evidence:

- User report: S7 passed.
- Existing Docker entrypoint sources ROS Humble and
  `/root/agx_arm_ws/install/setup.bash`.
- The new wrapper `scripts/launch_dual_ros_readonly.sh` starts two
  `start_single_agx_arm.launch.py` instances:
  - Arm A: `namespace:=arm_a`, `can_port:=can_arm_a`
  - Arm B: `namespace:=arm_b`, `can_port:=can_arm_b`
  - both: `arm_type:=nero`, `effector_type:=none`,
    `auto_enable:=false`, `control_enabled:=false`

Result:

- S7 is complete by operator report.
- S8 is now the active next phase.
- A safer project command exists for ROS read-only startup.

Deployment choices:

- Continue with bare-arm `effector_type:=none`.
- Do not use MoveIt execute, `/control/*`, `enable_agx_arm`, or `move_home`
  during S8.
- Use Docker Humble for ROS2; host remains SDK/CAN-only.

Files changed:
`scripts/launch_dual_ros_readonly.sh`, `docs/status/deployment_log.md`,
`docs/status/current_bringup_status.md`, `docs/phases/s6_dual_arm_can_ros_plan.md`,
`docs/phases/机器人部署与调试行动路线.md`.

Verification:
The wrapper checks that `ros2`, `can_arm_a`, and `can_arm_b` are visible before
starting the two ROS drivers.

Route updates:
S8 now documents the preferred host command:
`bash scripts/run_humble_container.sh bash /workspace/nero/scripts/launch_dual_ros_readonly.sh`.

Open risks:

- S8 has not yet been run.
- ROS topic frequency and namespace isolation still need verification.

Next:
Run the dual ROS read-only wrapper, then inspect `/arm_a/feedback/*` and
`/arm_b/feedback/*` topics from inside the running container.

## 2026-06-25 - S8.1 Dual ROS Feedback Passed

Phase: S8 ROS 只读

Goal:
Verify that both NERO arms publish isolated ROS feedback topics through the
Humble container with distinct namespaces.

Action:
Recorded operator-provided `ros2 topic list`, `ros2 topic hz`, and
`ros2 topic echo --once` output.

Commands / evidence:

- Topic list contains namespaced feedback topics:
  - `/arm_a/feedback/joint_states`
  - `/arm_a/feedback/tcp_pose`
  - `/arm_a/feedback/arm_status`
  - `/arm_b/feedback/joint_states`
  - `/arm_b/feedback/tcp_pose`
  - `/arm_b/feedback/arm_status`
- Topic list also contains namespaced control subscribers under
  `/arm_a/control/*` and `/arm_b/control/*`; these are expected node interfaces,
  but S8 does not publish to them.
- Arm A `/arm_a/feedback/joint_states` frequency: about `199.8-200.0 Hz` over a
  10 second sample.
- Arm B `/arm_b/feedback/joint_states` frequency: about `199.8-200.0 Hz` over a
  10 second sample.
- Arm A `arm_status`:
  - `ctrl_mode: 1`
  - `arm_status: 6`
  - `mode_feedback: 1`
  - `teach_status: 0`
  - `motion_status: 1`
  - `trajectory_num: 0`
  - `err_status: 0`
  - all `joint_angle_limit` values `false`
  - all `communication_status_joint` values `false`
- Arm B `arm_status` shows the same status pattern, including `err_status: 0`,
  all joint angle limits `false`, and all joint communication statuses `false`.

Result:

- Dual-arm ROS feedback is working.
- ROS namespace isolation is working: Arm A topics are under `/arm_a`, and Arm B
  topics are under `/arm_b`.
- Both arms publish joint feedback at the configured `200 Hz` rate.
- No ROS-level error, joint limit flag, or joint communication error is visible
  in the provided status output.

Deployment choices:

- Keep S8 read-only.
- Do not publish to `/arm_a/control/*` or `/arm_b/control/*`.
- Do not call `enable_agx_arm`, `move_home`, MoveIt execute, or any motion
  command yet.

Files changed:
`docs/status/deployment_log.md`, `docs/status/current_bringup_status.md`,
`docs/phases/机器人部署与调试行动路线.md`.

Verification:
S8 ROS feedback/topic portion passes. RViz follow visual validation remains as
the only S8 item not yet evidenced in this log.

Route updates:
The action route now records the observed 200 Hz dual-arm ROS feedback and clean
arm status.

Open risks:

- RViz has not yet been confirmed to follow the real dual-arm feedback.
- `arm_status` numeric meanings should still be interpreted through vendor docs
  before using them for application logic; the immediately relevant safety
  fields here are `err_status: 0`, no joint limits, and no joint communication
  errors.

Next:
Run RViz follow validation without publishing control topics. If the displayed
pose matches the real arms, close S8 and move to S9 configuration review.

## 2026-06-25 - S8.2 RViz RobotModel TF Issue

Phase: S8 ROS 只读

Goal:
Evaluate the operator-provided RViz screenshot after visual pose confirmation.

Action:
Reviewed `docs/evidence/pics/Riz 姿态确认关节未识别.png` and compared it with the
`display.launch.py` namespace/frame-prefix behavior.

Commands / evidence:

- User report: RViz pose matches the real arm.
- Screenshot: RViz Fixed Frame is `arm_a/base_link`.
- Screenshot: RobotModel has Description Source `Topic`, Description Topic
  `robot_description`, and TF Prefix `arm_a`.
- Screenshot: RobotModel status is `Error`.
- Screenshot: `arm_a/base_link` and `arm_a/world` are `Transform OK`.
- Screenshot: `arm_a/link1` through `arm_a/link7` report:
  `No transform from [arm_a/linkN] to [arm_a/base_link]`.
- Source review: `display.launch.py` sets `frame_prefix` from namespace and
  remaps `joint_states` to the selected `feedback_topic` when `follow:=true`.

Result:

- S8 ROS feedback remains passed from prior topic evidence.
- RViz visual follow is not fully accepted yet because the RobotModel plugin
  reports missing dynamic link transforms.
- The failure surface is likely between `/arm_a/feedback/joint_states` and
  `/arm_a/robot_state_publisher` dynamic TF output, or a joint-name mismatch
  between feedback and URDF.

Deployment choices:

- Keep S8 open until RViz RobotModel reports transforms for `link1` through
  `link7`.
- Continue read-only. Do not publish to `/control/*`.

Files changed:
`docs/status/deployment_log.md`, `docs/status/current_bringup_status.md`,
`docs/phases/机器人部署与调试行动路线.md`.

Verification:
Screenshot evidence confirms the RViz issue is not mesh loading or base frame
selection; it is missing dynamic TF for joint links.

Route updates:
S8 now requires both subjective visual pose match and RobotModel transform OK
for `link1` through `link7`.

Open risks:

- The exact cause is not yet proven. Need to inspect joint state names and
  robot_state_publisher subscription/TF output while RViz/RSP is running.

Next:
Re-run RViz with explicit absolute `feedback_topic:=/arm_a/feedback/joint_states`.
If RobotModel still reports missing link transforms, run ROS diagnostics for
joint state names, robot_state_publisher subscriptions, and TF echo.

## 2026-06-25 - S8.3 RViz Diagnosis Corrected And S8 Accepted

Phase: S8 ROS 只读

Goal:
Correct the previous RViz TF diagnosis using operator follow-up evidence.

Action:
The operator restarted the RViz validation with the first terminal running the
dual ROS read-only driver. RViz then recognized the joints and displayed the arm
pose correctly.

Commands / evidence:

- Prior screenshot showed `link1` through `link7` missing transforms while RViz
  was open.
- Operator confirmed the first terminal, which should run the ROS read-only
  driver and publish `/arm_a/feedback/joint_states` and
  `/arm_b/feedback/joint_states`, had not been started at that time.
- After starting that terminal, RViz behaved normally.
- Operator confirmed the RViz arm posture matches the real robot feedback.
- Remaining visual difference: the RViz model appears horizontal while the real
  table-upright arm hangs vertically. This is treated as coordinate frame /
  installation-pose alignment for S9, not as an S8 driver or URDF failure.

Result:

- Corrected diagnosis: the previous RobotModel TF error was caused by missing
  runtime feedback source due to launch order / prerequisite terminal omission.
- There is no current evidence of a joint-name mismatch or URDF joint-loading
  failure.
- S8 read-only ROS feedback and RViz follow are accepted.

Deployment choices:

- RViz follow validation requires the dual ROS read-only driver terminal to be
  running first.
- Keep `auto_enable:=false control_enabled:=false` for all read-only launches.
- Defer world/base frame alignment, Web installation-pose review, and external
  frame documentation to S9.

Files changed:
`docs/status/deployment_log.md`, `docs/status/current_bringup_status.md`,
`docs/phases/机器人部署与调试行动路线.md`, `docs/status/bringup_checklist.md`.

Verification:
Operator field report confirms RViz joint recognition and pose following work
after the driver terminal is active.

Route updates:
S8 is marked complete. The action route now says that missing `link1-link7` TF
in RViz should first trigger a check that the ROS feedback driver is running.

Next:
Proceed to S9 configuration review: installation posture, coordinate frames,
zero/TCP/tool settings, conservative limits, and documentation of the dual-arm
base frames.

## 2026-06-25 - S9.1 Read-Only Configuration Inventory Prepared

Phase: S9 标定与参数配置

Goal:
Start S9 without changing robot settings or sending motion commands.

Action:
Created a S9 worksheet and a read-only ROS snapshot helper. Updated the current
phase state and action route so S9 begins with Web/ROS evidence capture before
any configuration write.

Commands / evidence:

- Read `agent.md`, `docs/phases/机器人部署与调试行动路线.md`, and the user manual sections
  for zero setting and system settings.
- User manual section `6.7 设置零点` states zero setting should be done at the
  default upright position and that automatic zero setting moves the motor to
  the mechanical limit before returning.
- User manual section `6.8.4 安装位置设置` states installation posture affects
  robot coordinate calibration and spatial calculation.
- Added `docs/phases/s9_configuration_review.md`.
- Added executable script `scripts/snapshot_ros_readonly_state.sh`.

Result:

- S9 is active as `S9.1 read-only inventory`.
- The first S9 task is to capture Arm A and Arm B Web screenshots and one ROS
  read-only snapshot.
- Zero calibration, joint-limit changes, collision-level changes, and speed
  changes remain blocked until reviewed separately.

Deployment choices:

- S9.1 is read-only.
- Use current bare-arm configuration: `effector_type:=none`,
  `tcp_offset:=[0.0, 0.0, 0.0, 0.0, 0.0, 0.0]`.
- Treat the RViz horizontal-versus-real vertical visual difference as an S9
  coordinate/installation-pose alignment item.

Files changed:
`agent.md`, `docs/status/deployment_log.md`, `docs/status/current_bringup_status.md`,
`docs/phases/机器人部署与调试行动路线.md`, `docs/phases/s9_configuration_review.md`,
`scripts/snapshot_ros_readonly_state.sh`.

Verification:
`scripts/snapshot_ros_readonly_state.sh` was created and marked executable.
Route/status files now identify S9.1 as the active next step.

Route updates:
The S9 section now explicitly starts with a read-only inventory and requires a
ROS snapshot under `docs/evidence/ros_snapshots/`.

Open risks:

- Arm A and Arm B Web configuration screenshots have not yet been captured.
- The exact Web installation-position option corresponding to the physical
  table-upright installation still needs operator confirmation.
- No zero calibration decision has been made.

Next:
Operator captures S9 Web screenshots for both arms and runs the ROS read-only
snapshot command while the dual ROS read-only driver is running.

## 2026-06-25 - S9.2 Web Screenshots Read And Snapshot Script Corrected

Phase: S9 标定与参数配置

Goal:
Read the operator-provided S9 Web screenshots and identify whether S9.1 can be
accepted.

Action:
Inspected `docs/evidence/pics/S9.1/A01.png` through `A04.png` and
`docs/evidence/pics/S9.1/B01.png` through `B03.png`. Inspected the ROS snapshot directory
`docs/evidence/ros_snapshots/20260625_035128/`. Corrected the snapshot helper so a
timed `ros2 topic hz` sample does not abort the remaining captures.

Commands / evidence:

- Screenshot files:
  - Arm A: `A01.png`, `A02.png`, `A03.png`, `A04.png`.
  - Arm B: `B01.png`, `B02.png`, `B03.png`.
- Arm A and Arm B Web installation position: `1-水平正装`.
- Arm A and Arm B end effector: `默认（无加载）`.
- Arm A and Arm B load mode: `满载`.
- Arm A and Arm B visible tool mass: `0.00000 kg`.
- Arm A and Arm B visible collision protection evidence: J1 level `1`.
- Arm A zero-setting dialog was captured; Arm B zero-setting dialog was not
  captured.
- Arm A and Arm B joint limits/speeds shown by Web:
  - J1 `-155..155 deg`, max speed `179.9 deg/s`.
  - J2 `-100..100 deg`, max speed `179.9 deg/s`.
  - J3 `-158..158 deg`, max speed `179.9 deg/s`.
  - J4 `-58..123 deg`, max speed `179.9 deg/s`.
  - J5 `-158..158 deg`, max speed `224.6 deg/s`.
  - J6 `-42..55 deg`, max speed `224.6 deg/s`.
  - J7 `-90..90 deg`, max speed `224.6 deg/s`.
- End-speed settings shown by Web:
  - Linear velocity `1000.0 mm/s`.
  - Angular velocity `34.4 deg/s`.
  - Linear acceleration `1500.0 mm/s^2`.
  - Angular acceleration `286.5 deg/s^2`.
- Existing ROS snapshot only contains Arm A files because `timeout 5s ros2
  topic hz` returned a timeout code and the script stopped before Arm B capture.

Result:

- S9.1 is partially complete, but not accepted yet.
- A/B installation, default end-effector, load mode, joint limits, and end-speed
  values are recorded.
- J2 Web limit `-100..100 deg` conflicts with the manual route value
  `-15..190 deg`. This is consistent with the earlier URDF/Web/manual angle
  convention concern and must be resolved before any limit expansion or larger
  motion.
- Collision protection is not fully recorded because only J1 level is visible.
- Arm B zero-setting page is missing.
- Full A/B ROS snapshot is missing.

Deployment choices:

- Do not change Web settings yet.
- Do not perform zero calibration.
- Treat Web option `1-水平正装` as the currently observed installation setting
  for both arms.
- Treat `满载` as observed, not yet approved as the final operating load mode.

Files changed:
`docs/status/deployment_log.md`, `docs/status/current_bringup_status.md`,
`docs/phases/机器人部署与调试行动路线.md`, `docs/status/bringup_checklist.md`,
`docs/phases/s9_configuration_review.md`, `scripts/snapshot_ros_readonly_state.sh`.

Verification:
The snapshot helper now allows timeout exit code `124` for the intended short
frequency sample. Screenshot-derived values are recorded in the S9 worksheet.

Route updates:
S9 now records the observed Web configuration and explicitly calls out the
remaining S9.1 evidence gaps.

Open risks:

- Need Arm B zero-setting page screenshot.
- Need collision protection levels for J2-J7 on both arms.
- Need a corrected full A/B ROS snapshot.
- Need a decision on whether `满载` is an appropriate conservative load mode for
  the current bare-arm state.
- Need to reconcile Web J2 `-100..100 deg` with the manual `-15..190 deg`
  representation before S10.

Next:
Capture the missing Web evidence and rerun the S9 ROS read-only snapshot with
the corrected script.

## 2026-06-25 - S9.3 Read-Only Inventory Accepted

Phase: S9 标定与参数配置

Goal:
Close S9.1 inventory after the remaining operator confirmations and corrected
ROS snapshot.

Action:
Read the new ROS snapshot and recorded operator field confirmations for Arm B
zero page and collision protection levels.

Commands / evidence:

- Operator ran:
  `NERO_CONTAINER_NAME=nero-humble-s9-snapshot2 bash scripts/run_humble_container.sh bash /workspace/nero/scripts/snapshot_ros_readonly_state.sh`
- Snapshot path:
  `docs/evidence/ros_snapshots/20260625_044256/`.
- Snapshot contains Arm A and Arm B files for:
  - topic list
  - `joint_states`
  - `tcp_pose`
  - `arm_status`
  - short `joint_states` frequency samples
- Arm A `joint_states` names: `joint1` through `joint7`.
- Arm B `joint_states` names: `joint1` through `joint7`.
- Arm A frequency sample: about `199.98-200.00 Hz`.
- Arm B frequency sample: about `200.00-200.02 Hz`.
- Arm A and Arm B `arm_status`: `err_status: 0`, all joint angle limits
  `false`, all joint communication statuses `false`.
- Operator confirmed Arm B zero-setting page joint sequence is also `1`.
- Operator confirmed both arms have collision protection level `1` for all
  joints J1-J7.

Result:

- S9.1 read-only inventory is accepted.
- S9 remains active because configuration decisions are still pending before
  S10.
- The `ros2 topic hz` timeout files include a shutdown message after the sample
  window, but the frequency samples are valid. The helper script was updated to
  use SIGINT for cleaner future timeout shutdown.

Deployment choices:

- Current Web installation position for both arms: `1-水平正装`.
- Current Web end effector for both arms: `默认（无加载）`.
- Current Web load mode for both arms: `满载`.
- Current Web collision levels for both arms: J1-J7 all `1`.
- Current ROS runtime remains bare arm:
  `effector_type:=none`, `tcp_offset:=[0.0, 0.0, 0.0, 0.0, 0.0, 0.0]`.

Files changed:
`agent.md`, `config/nero.env`, `docs/status/deployment_log.md`,
`docs/status/current_bringup_status.md`, `docs/phases/机器人部署与调试行动路线.md`,
`docs/status/bringup_checklist.md`, `docs/phases/s9_configuration_review.md`,
`scripts/snapshot_ros_readonly_state.sh`.

Verification:
The corrected snapshot directory contains both Arm A and Arm B data and both
arms report clean read-only ROS status.

Route updates:
S9.1 is now accepted. S9.2 is the active next step.

Open risks:

- Decide whether `满载` should be kept or changed before first motion.
- Reconcile Web/URDF/manual J2 angle conventions before any limit expansion or
  larger motion.
- Decide how to document/transform the horizontal RViz/world representation
  relative to the real table-upright hanging posture.
- Decide whether zero calibration is needed; if yes, write a dedicated procedure
  before doing it.

Next:
Proceed to S9.2 configuration decisions. Do not enter S10 motion until S9.2
decisions are documented.

## 2026-06-25 - S9.4 Configuration Decisions Made

Phase: S9 标定与参数配置

Goal:
Resolve the remaining S9.2 decisions using current evidence and define the next
safe action before S10.

Action:
Reviewed the S9.1 Web/ROS evidence, user note that Web joint limits are
editable, local manual sections, and upstream ROS/SDK source behavior.

Commands / evidence:

- Manual section `6.8.5` says end-effector physical properties are used for
  motion control and torque compensation.
- Manual-derived S9 route says load mode must match the actual end effector.
- Current physical end effector is bare arm.
- Current Web end effector is `默认（无加载）`; visible tool mass is `0.00000 kg`.
- Current Web load mode is `满载`.
- Web J2 limit is `-100..100 deg`.
- URDF J2 limit found in S3 is about `-99.69..99.69 deg`.
- Manual J2 mechanical range is `-15..190 deg`.
- User confirmed Web joint limits are adjustable.
- Upstream `pyAgxArm` NERO `arm_mode_ctrl.py` defines installation position
  `0x01` as `Horizontal upright`.
- Upstream ROS launch/config review did not identify a ROS launch argument for
  Web installation pose; ROS exposes namespace, end-effector type, and TCP
  offset.

Result:

1. Load-mode decision:
   Change both arms from observed `满载` to the Web empty/no-load option before
   S10. Keep end effector `默认（无加载）`, tool mass `0.00000 kg`, ROS
   `effector_type:=none`, and TCP offset zero.

2. J2 limit decision:
   Do not edit or expand J2 Web limits before S10. Keep Web `-100..100 deg`.
   Treat manual `-15..190 deg` as a different angle convention, with current
   working inference `manual_J2_angle ≈ web_or_urdf_J2_angle + 90 deg`. This
   inference is only for avoiding unsafe edits, not for extending the allowed
   range.

3. Coordinate-frame decision:
   Keep Web installation position `1-水平正装`. Do not rotate URDF or change Web
   installation position to make RViz visually match the real hanging posture.
   Treat `arm_a/base_link` and `arm_b/base_link` as robot-local frames; future
   dual-arm coordination must add measured static transforms:
   `lab_world -> arm_a/base_link` and `lab_world -> arm_b/base_link`.

Deployment choices:

- S9.3 must perform only the load-mode correction and read-only revalidation.
- No joint limit edits before first motion.
- No Web installation-position change.
- No zero calibration.
- No Cartesian, MoveIt execute, or dual-arm coordinated motion before external
  base-frame calibration.

Files changed:
`agent.md`, `config/nero.env`, `docs/status/deployment_log.md`,
`docs/status/current_bringup_status.md`, `docs/phases/机器人部署与调试行动路线.md`,
`docs/status/bringup_checklist.md`, `docs/phases/s9_configuration_review.md`.

Verification:
Documents and config now distinguish observed current load mode `满载` from the
target before S10: empty/no-load.

Route updates:
S9.2 decisions are recorded. The active next step is S9.3 load-mode correction
and ROS read-only revalidation.

Open risks:

- Need to identify the exact Web label for empty/no-load on the live UI before
  applying it.
- Changing load mode is a controller configuration write and must be done while
  disabled and without motion.
- J2 angle convention remains an inference until validated through controlled
  first-motion observations.
- Lab/world base-frame calibration is still missing for dual-arm coordination.

Next:
Perform S9.3: change both arms' load mode to the Web empty/no-load option,
record screenshots, and rerun the ROS read-only snapshot.

## 2026-06-25 - S9.5 Load-Mode Change Procedure Prepared

Phase: S9 标定与参数配置

Goal:
Prepare the controlled S9.3 load-mode correction before the operator changes Web
settings.

Action:
Expanded `docs/phases/s9_configuration_review.md` with a load-mode-only execution
procedure, acceptance criteria, and stop conditions.

Commands / evidence:

- Current observed load mode remains `满载`.
- Current target before S10 is empty/no-load, expected Web label `空载`.
- Current Web end effector remains `默认（无加载）` and tool mass is
  `0.00000 kg`.

Result:

- S9.3 can proceed as a single controlled Web configuration write on each arm.
- The action is limited to load mode only.

Deployment choices:

- Change Arm A and Arm B consistently.
- Capture after-change screenshots under `docs/evidence/pics/S9.3/`.
- Re-run ROS read-only snapshot after the Web write.

Files changed:
`docs/status/deployment_log.md`, `docs/phases/s9_configuration_review.md`.

Verification:
Procedure now specifies acceptance criteria and stop/rollback conditions.

Route updates:
No phase gate changed. S9.3 remains the active next step.

Open risks:

- The exact Web label for empty/no-load must be verified on the live UI.
- Any Web submit is a controller configuration write, so the operator must avoid
  changing adjacent settings.

Next:
Operator performs S9.3 in Web UI, then provides screenshots and ROS snapshot
path/output.

## 2026-06-25 - S9.6 Web Mode And CAN Revalidation Issue

Phase: S9 标定与参数配置

Goal:
Record the S9.3 recovery state after Web load-mode change and failed ROS
revalidation.

Action:
The operator reported that the load setting was successfully changed, but Web
could not switch back through the top CAN button. The CAN button tooltip says
`关闭外网CAN推送`. The operator also reported ROS launch failure:
`CAN interface can_arm_a is not visible`.

Commands / evidence:

- User report: load setting changed successfully.
- User report: top CAN button tooltip is `关闭外网CAN推送`.
- User report: clicking it fails.
- User command/output:
  `bash scripts/run_humble_container.sh >     bash /workspace/nero/scripts/launch_dual_ros_readonly.sh`
  then `CAN interface can_arm_a is not visible.`
- Local repository root contains a new zero-byte file named `bash`, consistent
  with a literal shell redirection character `>` being used accidentally.
- Attempting to inspect netlink interfaces from the assistant sandbox failed
  with `Operation not permitted`, so host CAN state must be checked in the real
  desktop terminal.

Result:

- S9.3 is not accepted yet.
- The Web CAN button may be CAN push rather than the SocketCAN host interface.
  Tooltip `关闭外网CAN推送` means CAN push appears already enabled.
- ROS failure now needs host SocketCAN interface recovery or command syntax
  correction.

Deployment choices:

- Do not repeatedly click the Web CAN push button during recovery.
- Verify host `can_arm_a` and `can_arm_b` visibility first.
- If deterministic names are missing, reactivate with the recorded USB bus-info:
  Arm A `1-5:1.0`, Arm B `1-11:1.0`.
- Use the correct read-only launch command without a literal `>`.

Files changed:
`docs/status/deployment_log.md`, `docs/status/current_bringup_status.md`,
`docs/phases/s9_configuration_review.md`.

Verification:
No ROS revalidation accepted yet.

Route updates:
S9.3 troubleshooting now documents Web mode, CAN push, SocketCAN checks, and the
correct launch command.

Open risks:

- Unknown whether both host CAN interfaces are currently up and named.
- Unknown whether both arms' load mode was changed and screenshotted.

Next:
Operator checks host CAN interfaces, reactivates names if needed, then reruns
read-only ROS and S9 snapshot.

## 2026-06-25 - S9.7 Load-Mode Snapshot Attempt Missing ROS Topics

Phase: S9 标定与参数配置

Goal:
Evaluate the operator's S9.3 snapshot attempt.

Action:
Inspected the latest snapshot directories:
`docs/evidence/ros_snapshots/20260625_051838/` and
`docs/evidence/ros_snapshots/20260625_051844/`.

Commands / evidence:

- Both latest `topic_list.txt` files contain only:
  - `/parameter_events`
  - `/rosout`
- Both attempts fail at `/arm_a/feedback/joint_states`:
  `topic [/arm_a/feedback/joint_states] does not appear to be published yet`.
- No Arm B files were created by the old script because it stopped on the first
  failed Arm A capture.

Result:

- These S9.3 snapshots do not validate the load-mode change.
- The likely cause is that the dual ROS read-only driver was not running, or had
  already exited, when the snapshot was taken.

Deployment choices:

- S9.3 remains open.
- Snapshot helper was made more diagnostic: it now continues through both arms
  and reports failed capture commands instead of leaving a partial directory.

Files changed:
`docs/status/deployment_log.md`, `scripts/snapshot_ros_readonly_state.sh`.

Verification:
Latest snapshot topic lists prove the expected `/arm_a/...` and `/arm_b/...`
feedback topics were absent during the attempt.

Route updates:
No phase gate changed.

Open risks:

- Need to confirm the dual ROS read-only driver can stay running after the Web
  load-mode change.
- Need after-change Web screenshots if not already saved.

Next:
Start the dual ROS read-only driver in one terminal, confirm feedback topics in
a second terminal, then rerun the S9 snapshot.

## 2026-06-25 - S9.8 Arm A Firmware Read Failure

Phase: S9 标定与参数配置

Goal:
Diagnose why S9.3 ROS revalidation topics were absent.

Action:
Reviewed the operator-provided dual ROS read-only launch log and upstream driver
code around firmware detection.

Commands / evidence:

- Launch command:
  `bash scripts/run_humble_container.sh bash /workspace/nero/scripts/launch_dual_ros_readonly.sh`
- Both arm nodes started with:
  `auto_enable: False`, `control_enabled: False`, `pub_rate: 200`,
  `effector_type: none`.
- Arm B:
  - `firmware version: 1.121`
  - `Agx_arm feedback is ready`
- Arm A:
  - `Failed to get firmware version`
  - process exited with code `1`
- `launch_dual_ros_readonly.sh` exits when one child exits, so Arm B is also
  stopped after Arm A fails.
- Upstream `agx_arm_ctrl_single_node.py` calls `get_firmware()` during node
  initialization and exits if firmware is not returned within
  `enable_timeout`.
- Upstream NERO driver `get_firmware()` sends a firmware request and waits for
  an 8-byte firmware feedback message.

Result:

- The failure is isolated to Arm A / `can_arm_a` CAN request-response path.
- Arm B / `can_arm_b` is proven healthy in the same launch attempt.
- S9.3 remains open.

Deployment choices:

- Do not proceed to S10.
- Do not keep repeatedly clicking the Web CAN push button.
- First verify host `can_arm_a` visibility and passive CAN frames, then test
  Arm A SDK read-only.

Files changed:
`docs/status/deployment_log.md`.

Verification:
Driver source confirms the ROS failure happens before any control topic
operation; it is a firmware query failure.

Route updates:
No phase gate changed.

Open risks:

- Arm A may still be in a Web/control state that blocks external CAN
  request-response.
- Arm A external CAN push may be off despite Web tooltip ambiguity.
- Arm A USB-CAN mapping or physical CAN connection may have changed.

Next:
Run host CAN visibility checks, passive `candump`, and Arm A SDK read-only
firmware/state checks before retrying dual ROS.

## 2026-06-25 - S9.9 Arm A Passive CAN Frames Missing

Phase: S9 标定与参数配置

Goal:
Record the result of host-side CAN isolation after Arm A firmware read failure.

Action:
The operator ran the second diagnostic step and compared passive CAN capture on
Arm A and Arm B.

Commands / evidence:

- Operator report: Arm A has no passive CAN frames.
- Operator report: Arm B has passive CAN frames and is normal.
- Operator attempted SDK read-only commands from the Conda/base environment:
  `python examples/nero_read_state.py --connect --channel can_arm_a --firmware v112 --duration 3`
  and the same command for `can_arm_b`.
- Both SDK attempts failed before connecting:
  `No module named 'pyAgxArm'`.
- This SDK result is an environment activation issue, not a robot communication
  result.
- Manual section `5.1.3` identifies the top `can通讯` button as toggling CAN
  communication on/off.
- Manual notes the controller uses independent state-machine modes and Web mode
  is required for Web operations.

Result:

- Current fault is isolated to Arm A CAN publishing/communication availability.
- Arm B remains healthy.
- The most likely explanation is that Arm A's CAN communication / external CAN
  push was disabled or not restored during the Web mode/configuration sequence.

Deployment choices:

- Do not proceed to S10.
- Recover Arm A CAN communication through the Web CAN communication toggle or a
  controlled reboot if Web recovery fails.
- SDK tests must be run from `.venv/nero-sdk`, not the Conda/base environment.

Files changed:
`docs/status/deployment_log.md`.

Verification:
Passive `candump` comparison distinguishes Arm A from Arm B and points below ROS
to the arm/controller CAN communication state.

Route updates:
No phase gate changed.

Open risks:

- It is not yet verified whether Arm A Web CAN button state says enable or
  disable after refreshing/relogging.
- It is not yet verified whether Arm A reboot restores CAN push.

Next:
Refresh/relogin Arm A Web, ensure CAN communication is enabled, verify passive
`candump -tz can_arm_a`, then rerun dual ROS read-only.

## 2026-06-25 - S9.10 Arm A Still Has No Passive CAN Frames After Reboot

Phase: S9 标定与参数配置

Goal:
Record Arm A recovery attempt after Web load-mode change and CAN frame loss.

Action:
The operator rebooted Arm A and reran passive CAN capture on `can_arm_a`.

Commands / evidence:

- Operator report: after reboot, `timeout 5s candump -tz can_arm_a` still shows
  no frames.
- Prior comparison remains: Arm B has frames and is normal.

Result:

- S9.3 remains blocked.
- The problem is below ROS topics and below the previous SDK import issue.
- Candidate causes are now:
  - Arm A Web CAN communication / external CAN push is still off or stuck.
  - `can_arm_a` is not actually mapped to the Arm A USB-CAN path after recovery.
  - Arm A CAN interface is not UP / not ERROR-ACTIVE / bus-off.
  - Arm A physical CAN wiring or USB-CAN module path has a fault.

Deployment choices:

- Do not proceed to S10.
- First collect host CAN interface state and mapping before changing more Web
  settings.
- If host interface/mapping is healthy, isolate by known-good module/cable or
  Arm A Web CAN state.

Files changed:
`docs/status/deployment_log.md`, `docs/status/current_bringup_status.md`.

Verification:
No passive Arm A CAN frames are present after reboot.

Route updates:
No phase gate changed.

Open risks:

- Unknown exact Arm A Web CAN button state after reboot.
- Unknown current `ip -details` state for `can_arm_a`.
- Unknown whether Arm A physical CAN path is healthy.

Next:
Run host CAN interface/mapping checks, then run SDK read-only from the correct
venv if any Arm A frames or request-response path is restored.

## 2026-06-25 - S9.11 Arm A CAN Recovered By USB Replug

Phase: S9 标定与配置

Goal:
Record the recovery that restored Arm A CAN communication after the S9.3 Web
load-mode change.

Action:
The operator unplugged/replugged the Arm A USB-CAN path and reactivated the
interface.

Commands / evidence:

- Operator report: the issue was resolved by replugging the USB port and then
  setting/activating the interface again.
- Operator report: the dual ROS read-only launch now runs successfully:
  `bash scripts/run_humble_container.sh bash /workspace/nero/scripts/launch_dual_ros_readonly.sh`

Result:

- Arm A CAN request/response path is recovered by operator report.
- S9.3 still needs final ROS snapshot after the load-mode change.

Deployment choices:

- If a CAN interface is mapped but produces no passive frames after Web mode or
  configuration changes, use USB-CAN replug plus deterministic reactivation as a
  recovery step before deeper robot-side debugging.
- Preserve Arm A mapping as `1-5:1.0` and Arm B mapping as `1-11:1.0`.

Files changed:
`docs/status/deployment_log.md`, `docs/status/current_bringup_status.md`,
`docs/phases/s9_configuration_review.md`.

Verification:
No new S9.3 snapshot has been recorded yet in `docs/evidence/ros_snapshots/`.

Route updates:
S9.3 moves from CAN recovery to ROS read-only revalidation pending.

Open risks:

- Need to confirm the post-load-mode ROS snapshot shows clean A/B status.
- Need screenshots or field confirmation that both arms show the new no-load
  mode.

Next:
Run S9.3 snapshot while the dual ROS read-only driver remains running.

## 2026-06-25 - S9.12 S9 Accepted After Load-Mode Revalidation

Phase: S9 标定与配置

Goal:
Evaluate the final S9.3 ROS snapshot after load-mode correction and Arm A CAN
recovery.

Action:
Read `docs/evidence/ros_snapshots/20260625_054435/`.

Commands / evidence:

- Operator confirmed topic list includes complete Arm A and Arm B feedback
  topics.
- Snapshot path: `docs/evidence/ros_snapshots/20260625_054435/`.
- Snapshot `README.md`: `Failed capture commands: 0`.
- Arm A `arm_status`:
  - `err_status: 0`
  - all joint angle limits `false`
  - all joint communication statuses `false`
- Arm B `arm_status`:
  - `err_status: 0`
  - all joint angle limits `false`
  - all joint communication statuses `false`
- Arm A joint-state frequency: about `199.9 Hz`.
- Arm B joint-state frequency: about `199.7-199.9 Hz`.
- Arm A and Arm B joint-state names are `joint1` through `joint7`.
- Operator previously reported both arms' load settings were changed
  successfully to the bare-arm empty/no-load option.
- No after-change Web screenshots were found under `docs/evidence/pics/`; acceptance uses
  operator field confirmation plus clean ROS revalidation.

Result:

- S9 is accepted.
- S10 can be prepared, but no motion is approved until the S10 first-motion
  checklist is explicitly followed.

Deployment choices:

- Current Web load mode is treated as empty/no-load by operator confirmation.
- Keep Web installation position `1-水平正装`.
- Keep J2 Web limits `-100..100 deg`; do not expand before first motion.
- Keep ROS runtime as bare arm:
  `effector_type:=none`, `tcp_offset:=[0.0, 0.0, 0.0, 0.0, 0.0, 0.0]`.
- Record Arm A USB-CAN replug plus deterministic activation as a valid recovery
  path for a mapped interface with no passive frames.

Files changed:
`agent.md`, `config/nero.env`, `docs/status/deployment_log.md`,
`docs/status/current_bringup_status.md`, `docs/phases/机器人部署与调试行动路线.md`,
`docs/status/bringup_checklist.md`, `docs/phases/s9_configuration_review.md`.

Verification:
Final S9.3 ROS snapshot is complete and clean for both arms.

Route updates:
S9 is complete. The active next phase is S10 first low-speed motion planning.

Open risks:

- No measured `lab_world -> arm_a/base_link` or `lab_world -> arm_b/base_link`
  transforms yet; do not do dual-arm coordinated or Cartesian motion.
- First motion still requires human safety checks and one active control source.
- J2 angle convention remains inferred and must be watched during small
  joint-space tests.

Next:
Prepare S10 first low-speed single-arm joint-space motion checklist and command
selection.

## 2026-06-25 - S10.0 First-Motion Plan Prepared

Phase: S10 首次低速运动

Goal:
Prepare the first real NERO motion as a bounded, documented, operator-confirmed
procedure.

Action:
Created a dedicated first-motion plan and updated the route, status page,
checklist, agent rules, and environment defaults.

Commands / evidence:

- Manual section `6.1 运动控制`: Web operation requires switching to `WEB`
  mode and enabling before joint motion; joint motion applies after clicking
  apply.
- Manual section `6.5 速度调节`: Web has an overall speed percentage slider.
- S9 accepted snapshot: `docs/evidence/ros_snapshots/20260625_054435/`.
- S9 accepted configuration: bare arm, no-load, Web `1-水平正装`, collision
  levels J1-J7 all `1`, no ROS status errors.

Result:

- S10 is active but no motion has been executed.
- First motion is constrained to one arm, Web control only, low speed, single
  joint J7, `+2 deg` then return to the original angle.

Deployment choices:

- Prefer Arm B only if physical clearance is no worse than Arm A, because Arm B
  had the more stable CAN path during S9 recovery.
- Use J7 first because the bare-arm swept volume is expected to be smallest and
  it avoids J2/J4 and J1 for the initial motion.
- Stop ROS before Web motion so there is only one active control source.
- Use the Web speed percentage slider at the lowest available value, preferably
  `5%` or lower.
- After Web motion, return to dual-arm ROS read-only validation and save a
  snapshot before any SDK or ROS motion.

Files changed:
`agent.md`, `config/nero.env`, `docs/status/deployment_log.md`,
`docs/status/current_bringup_status.md`, `docs/status/bringup_checklist.md`,
`docs/phases/机器人部署与调试行动路线.md`, `docs/phases/s10_first_motion_plan.md`.

Follow-up correction:
Updated the current SDK selector note to `v112`, fixed the `agent.md`
read-only launch sentence, and changed `NERO_DUAL_ARM_INITIAL_MODE` from the
stale S6 value to `s10_web_first_motion_next`.

Verification:
Documentation update only. No robot motion or control command was sent.

Route updates:
S10.0 is prepared. S10.1 Web first motion is pending operator safety
confirmation.

Open risks:

- The Web speed UI must be physically confirmed before clicking apply.
- J7 can twist a cable if the cable path is poor; confirm J6/J7 clearance before
  using the default J7 motion.
- Web mode may again disturb passive CAN frames; use the S9 USB-CAN replug and
  deterministic activation recovery if needed.

Next:
Operator confirms the S10 Pre-Motion Gate, then executes the Web J7 `+2 deg`
and return test on the selected single arm.

## 2026-06-25 - S10.1 Arm A Selected For First Motion

Phase: S10 首次低速运动

Goal:
Record operator selection and safety confirmation before the first real motion.

Action:
The operator selected Arm A for S10.1 and confirmed the remaining pre-motion
requirements.

Commands / evidence:

- Operator statement: "就用 arm A 吧，其余内容已确认。"
- Planned action remains Web-only, low-speed, single-joint J7, `+2 deg` then
  return to the original J7 angle.

Result:

- Arm A is the selected S10.1 execution arm.
- First motion has not yet been reported executed.

Deployment choices:

- Use Arm A despite the default Arm B recommendation because the operator chose
  Arm A after confirming the safety conditions.
- Keep the Web first-motion procedure unchanged: stop ROS first, Web is the
  only control source, use lowest speed percentage, command only J7.

Files changed:
`config/nero.env`, `docs/status/current_bringup_status.md`,
`docs/status/deployment_log.md`, `docs/phases/s10_first_motion_plan.md`.

Verification:
Documentation update only. No robot motion or control command was sent by this
agent.

Route updates:
S10.1 may now proceed on Arm A under the documented Web first-motion procedure.

Open risks:

- Motion result and post-motion ROS snapshot are still pending.
- If Arm A CAN feedback disappears after Web mode, use the documented USB-CAN
  replug and deterministic reactivation recovery path.

Next:
Execute Arm A Web J7 `+2 deg`, return to original angle, then run post-motion
ROS read-only validation.

## 2026-06-25 - S10.1 Web First Motion Passed On Arm A

Phase: S10 首次低速运动

Goal:
Record and evaluate the first real NERO motion result.

Action:
The operator executed Web control on Arm A.

Commands / evidence:

- Operator report: Web enable succeeded.
- Operator report: Web joint control succeeded.
- Operator report: all 7 Arm A degrees of freedom moved successfully.
- Post-motion ROS read-only snapshot:
  `docs/evidence/ros_snapshots/20260625_060810/`.
- Snapshot `README.md`: `Failed capture commands: 0`.
- Arm A joint-state frequency: about `200.0 Hz`.
- Arm B joint-state frequency: about `200.0 Hz`.
- Arm A `arm_status`:
  - `arm_status: 0`
  - `err_status: 0`
  - all joint angle limits `false`
  - all joint communication statuses `false`
- Arm B `arm_status`:
  - `arm_status: 6`
  - `err_status: 0`
  - all joint angle limits `false`
  - all joint communication statuses `false`
- Arm A after-motion joint positions in radians:
  `J1=0.9686577348568529`,
  `J2=1.2356931104119853`,
  `J3=-0.5166174585903216`,
  `J4=0.7260569688296411`,
  `J5=0.3769911184307752`,
  `J6=-0.6981317007977318`,
  `J7=-0.6195220712879073`.

Result:

- S10.1 Web first motion is accepted for Arm A.
- Actual field motion exceeded the original J7-only recommendation because all
  7 degrees of freedom were moved. It succeeded and post-motion ROS feedback is
  healthy, but it does not remove the need for separate SDK/ROS motion gates.

Deployment choices:

- Hold further motion after the successful Web test.
- Treat the current Arm A pose as the latest observed post-motion pose; do not
  command return/home/park unless a separate procedure is written.
- Keep SDK motion, ROS `/control/*`, raw CAN motion, Cartesian motion, MoveIt
  execute, MIT mode, master-slave mode, dexterous-hand actuation, and dual-arm
  motion disabled until separately planned.

Files changed:
`agent.md`, `config/nero.env`, `docs/status/deployment_log.md`,
`docs/status/current_bringup_status.md`, `docs/status/bringup_checklist.md`,
`docs/phases/机器人部署与调试行动路线.md`, `docs/phases/s10_first_motion_plan.md`.

Verification:
Post-motion ROS read-only snapshot is complete and clean for both arms.

Route updates:
S10.1 Web first motion has passed. S10 remains active for SDK/ROS low-speed
motion planning.

Open risks:

- Arm A `arm_status` changed from previous snapshot value `6` to `0`; no error
  flags are set, but monitor this state-machine difference in the next step.
- Intentional emergency-stop recovery has not been triggered and verified.
- The final Arm A pose may need a future controlled park/home decision.

Next:
Prepare S10.2: a single-arm, single-joint, low-speed SDK or ROS motion test
with explicit command limits and post-motion read-only validation.

## 2026-06-25 - S10.2 SDK Single-Joint Test Prepared

Phase: S10 首次低速运动

Goal:
Prepare the next control path after Web: direct `pyAgxArm` SDK joint-space
control over SocketCAN.

Action:
Read the local SDK and ROS driver sources, then created a bounded SDK motion
script and S10.2 procedure.

Commands / evidence:

- Local SDK documentation `pyAgxArm/docs/nero/nero_api.md`:
  NERO joint angles are 7-element lists in radians; `move_j()` commands
  joint-space targets; `set_speed_percent()` sets relative speed.
- Local SDK v112 driver:
  `enable(joint_index=255, timeout=...)` is supported for all-joint enable.
- Local ROS driver:
  `/control/move_j` ultimately calls SDK `move_j()` and is additionally gated
  by ROS `auto_enable`, `control_enabled`, and feedback readiness.
- New script:
  `examples/nero_sdk_single_joint_step.py`.
- New procedure:
  `docs/phases/s10_2_sdk_motion_plan.md`.
- Verification commands:
  `python3 -m py_compile examples/nero_sdk_single_joint_step.py`
  and
  `.venv/nero-sdk/bin/python examples/nero_sdk_single_joint_step.py --help`
  both passed.

Result:

- S10.2 is prepared but not executed.
- The script defaults to dry-run and requires `--execute` to send any motion.

Deployment choices:

- Test SDK before ROS because SDK is the direct control layer underneath the ROS
  driver and avoids ROS launch/topic gate variables for this step.
- Scope is Arm A, `can_arm_a`, J7, `+1 deg`, speed `5%`, then return to the
  original angle.
- The script reads current 7-joint feedback, modifies only J7, verifies SDK
  joint limits, refuses speed above `10%`, and refuses delta above `2 deg` by
  default.
- Do not disable the arm at script end because disabling can allow gravity
  motion depending on posture and brake state.

Files changed:
`agent.md`, `config/nero.env`, `docs/status/deployment_log.md`,
`docs/status/current_bringup_status.md`, `docs/status/bringup_checklist.md`,
`docs/phases/机器人部署与调试行动路线.md`, `docs/phases/s10_2_sdk_motion_plan.md`,
`examples/nero_sdk_single_joint_step.py`.

Verification:
Static Python compilation and `--help` passed. No robot motion command was sent
by this agent.

Route updates:
S10.2 SDK dry-run is next. SDK execution requires operator safety confirmation
after dry-run output is checked.

Open risks:

- SDK execution still enables all joints and sends real CAN motion; keep one
  active control source and a human emergency-stop/power-cutoff assignment.
- Arm A `arm_status` state-machine value should continue to be monitored.
- ROS motion remains pending until S10.2 SDK motion is accepted.

Next:
Run the SDK dry-run command from `docs/phases/s10_2_sdk_motion_plan.md`. If the target
is correct and safety gate remains true, run the `--execute` command and then
capture a ROS read-only snapshot.

## 2026-06-25 - S10.2 SDK J7 Dry-Run Passed, Execution Candidate Revised To J1

Phase: S10 首次低速运动

Goal:
Evaluate SDK dry-run output and decide the execution joint for observability.

Action:
Operator ran the SDK dry-run for Arm A J7 without `--execute`.

Commands / evidence:

- Command:
  `.venv/nero-sdk/bin/python examples/nero_sdk_single_joint_step.py --channel can_arm_a --firmware v112 --joint 7 --delta-deg 1 --speed-percent 5`
- Output reported firmware: `{'software_version': '1.121'}`.
- Current Arm A joint angles in degrees:
  `[55.5, 70.798, -29.599, 41.602000000000004, 21.6, -39.999, -35.5]`.
- Target Arm A joint angles in degrees:
  `[55.5, 70.798, -29.599, 41.602000000000004, 21.6, -39.999, -34.5]`.
- Pre-status:
  `ctrl_mode=CAN_CTRL(0x1)`,
  `arm_status=NORMAL(0x0)`,
  `mode_feedback=MOVE_J(0x1)`,
  `motion_status=REACH_TARGET_POS_SUCCESSFULLY(0x0)`.
- Script ended in dry-run mode; no motion was sent.
- Operator proposed using J1 instead of J7 because J7 rotation is hard to
  observe visually.

Result:

- SDK dry-run path is healthy.
- J7 dry-run target was correct and changed only J7 by `+1 deg`.
- No SDK motion has been executed.
- Execution candidate is revised from J7 to J1, pending a new J1 dry-run.

Deployment choices:

- Accept J1 as the next dry-run/execution candidate because `1 deg` J1 motion
  is more observable than J7 wrist rotation.
- Recognize the added risk: J1 moves the whole arm around the base. Before
  execution, the entire small J1 swept area must be clear.
- Keep all other constraints unchanged: Arm A only, `can_arm_a`, `+1 deg`,
  speed `5%`, SDK only, then return to the original angle.

Files changed:
`agent.md`, `config/nero.env`, `docs/status/deployment_log.md`,
`docs/status/current_bringup_status.md`, `docs/status/bringup_checklist.md`,
`docs/phases/机器人部署与调试行动路线.md`, `docs/phases/s10_2_sdk_motion_plan.md`.

Verification:
Dry-run output is consistent with a J7-only target change and healthy status.

Route updates:
S10.2 remains active. Run a new J1 dry-run before considering SDK execution.

Open risks:

- J1 has larger workspace sweep than J7 even at `1 deg`.
- No SDK motion has been accepted yet.

Next:
Run the SDK J1 dry-run command. If it changes only J1 by `+1 deg`, and the J1
swept area is confirmed clear, proceed to the SDK `--execute` command.

## 2026-06-25 - S10.2 SDK J1 Dry-Run Passed, Delta Revised To 2 Degrees

Phase: S10 首次低速运动

Goal:
Evaluate the revised J1 dry-run and decide whether the execution delta should
remain `1 deg` or increase slightly for observability.

Action:
Operator ran the SDK dry-run for Arm A J1 without `--execute`.

Commands / evidence:

- Command:
  `.venv/nero-sdk/bin/python examples/nero_sdk_single_joint_step.py --channel can_arm_a --firmware v112 --joint 1 --delta-deg 1 --speed-percent 5`
- Output reported firmware: `{'software_version': '1.121'}`.
- Current Arm A joint angles in degrees:
  `[55.498000000000005, 70.796, -29.599, 41.599000000000004, 21.599, -40.0, -35.499]`.
- Target Arm A joint angles in degrees:
  `[56.49800000000001, 70.796, -29.599, 41.599000000000004, 21.599, -40.0, -35.499]`.
- Pre-status:
  `ctrl_mode=CAN_CTRL(0x1)`,
  `arm_status=NORMAL(0x0)`,
  `mode_feedback=MOVE_J(0x1)`,
  `motion_status=REACH_TARGET_POS_SUCCESSFULLY(0x0)`.
- Script ended in dry-run mode; no motion was sent.
- Operator confirmed the J1 swept area is clear and requested a slightly larger
  J1 angle for easier observation.

Result:

- J1 `+1 deg` dry-run is accepted.
- No SDK motion has been executed.
- Execution delta is revised to J1 `+2 deg`, pending a new `+2 deg` dry-run.

Deployment choices:

- Keep the delta at the script's default safety ceiling of `2 deg`; do not
  increase above this for first SDK motion.
- At the manual working radius of about `580 mm`, `2 deg` corresponds to about
  `20 mm` arc displacement at the outer radius, which should be observable
  while still being a small joint-space command.
- Preserve all other constraints: Arm A only, `can_arm_a`, speed `5%`, SDK only,
  then return to the original angle.

Files changed:
`agent.md`, `config/nero.env`, `docs/status/deployment_log.md`,
`docs/status/current_bringup_status.md`, `docs/status/bringup_checklist.md`,
`docs/phases/机器人部署与调试行动路线.md`, `docs/phases/s10_2_sdk_motion_plan.md`.

Verification:
Dry-run output is consistent with a J1-only `+1 deg` target change and healthy
status.

Route updates:
S10.2 remains active. Run a new J1 `+2 deg` dry-run before SDK execution.

Open risks:

- J1 moves the full arm around the base; swept area must remain clear during
  execution.
- No SDK motion has been accepted yet.

Next:
Run the SDK J1 `+2 deg` dry-run command. If it changes only J1 by `+2 deg`, and
the safety gate remains true, proceed to the SDK `--execute` command.

## 2026-06-25 - S10.2 SDK J1 Motion Passed

Phase: S10 首次低速运动

Goal:
Record and evaluate the first SDK-controlled real motion.

Action:
Operator executed the SDK single-joint step on Arm A J1.

Commands / evidence:

- Command:
  `.venv/nero-sdk/bin/python examples/nero_sdk_single_joint_step.py --execute --channel can_arm_a --firmware v112 --joint 1 --delta-deg 2 --speed-percent 10`
- Operator report: J1 visibly moved upward a small amount and then returned to
  the original position.
- Firmware: `{'software_version': '1.121'}`.
- Current Arm A joint angles in degrees:
  `[55.499, 70.799, -29.62, 41.599000000000004, 21.6, -39.999, -35.502]`.
- Target Arm A joint angles in degrees:
  `[57.499, 70.799, -29.62, 41.599000000000004, 21.6, -39.999, -35.502]`.
- After-step angles:
  `[57.503, 70.8, -29.625000000000004, 41.598, 21.6, -39.999, -35.502]`.
- After-return angles:
  `[55.49500000000001, 70.8, -29.619, 41.597, 21.6, -40.005, -35.502]`.
- Pre, enabled, and final statuses were all:
  `ctrl_mode=CAN_CTRL(0x1)`,
  `arm_status=NORMAL(0x0)`,
  `mode_feedback=MOVE_J(0x1)`,
  `motion_status=REACH_TARGET_POS_SUCCESSFULLY(0x0)`.
- Script printed:
  `S10.2 SDK single-joint step completed.`

Result:

- S10.2 SDK single-joint motion is accepted for Arm A.
- J1 moved by about `+2 deg` and returned to the original angle within normal
  feedback tolerance.
- Actual speed percent was `10`, not the planned `5`; this is accepted because
  it stayed within the script's S10.2 hard limit of `0..10`.

Deployment choices:

- Keep future first-time control-path motions at or below `10%`; prefer `5%`
  unless observability requires otherwise.
- Do not proceed to ROS motion until the post-SDK ROS read-only snapshot is
  captured and accepted.

Files changed:
`agent.md`, `config/nero.env`, `docs/status/deployment_log.md`,
`docs/status/current_bringup_status.md`, `docs/status/bringup_checklist.md`,
`docs/phases/机器人部署与调试行动路线.md`, `docs/phases/s10_2_sdk_motion_plan.md`.

Verification:
SDK script output and operator visual observation indicate successful motion and
return. ROS post-motion validation is still pending.

Route updates:
S10.2 SDK motion has passed. S10.2 post-SDK ROS read-only validation is next.

Open risks:

- Need post-SDK ROS snapshot to confirm both arms still have clean feedback.
- Intentional emergency-stop recovery remains untested.

Next:
Start dual-arm ROS read-only validation and capture a post-SDK snapshot.

## 2026-06-25 - S10.2 Post-SDK ROS Snapshot Accepted And S10.3 Prepared

Phase: S10 首次低速运动

Goal:
Accept the post-SDK read-only validation and prepare the ROS control-layer test.

Action:
Read `docs/evidence/ros_snapshots/20260625_062910/`, then created the S10.3 ROS
single-joint procedure and helper script.

Commands / evidence:

- Snapshot: `docs/evidence/ros_snapshots/20260625_062910/`.
- Snapshot `README.md`: `Failed capture commands: 0`.
- Topic list includes complete `/arm_a/...` and `/arm_b/...` feedback and
  control topics.
- Arm A joint-state frequency: about `200.0 Hz`.
- Arm B joint-state frequency: about `200.0 Hz`.
- Arm A `arm_status`:
  - `ctrl_mode: 1`
  - `arm_status: 0`
  - `mode_feedback: 1`
  - `motion_status: 0`
  - `err_status: 0`
  - all joint angle limits `false`
  - all joint communication statuses `false`
- Arm B `arm_status`:
  - `ctrl_mode: 1`
  - `arm_status: 6`
  - `mode_feedback: 1`
  - `motion_status: 1`
  - `err_status: 0`
  - all joint angle limits `false`
  - all joint communication statuses `false`
- New script:
  `scripts/ros_single_joint_step.py`.
- New procedure:
  `docs/phases/s10_3_ros_motion_plan.md`.
- Verification:
  `python3 -m py_compile scripts/ros_single_joint_step.py` passed.

Result:

- S10.2 SDK motion is fully accepted, including post-SDK ROS read-only
  validation.
- S10.3 ROS single-joint test is prepared but not executed.

Deployment choices:

- S10.3 will test ROS after SDK because ROS wraps the SDK and adds launch
  parameters, enable behavior, control gate, and topic delivery.
- Scope remains Arm A only: ROS namespace `/arm_a`, `can_arm_a`, `joint1 +2 deg`,
  then return to original angle.
- ROS driver speed is planned at `5%`; `10%` remains the maximum for first
  control-path tests.

Files changed:
`agent.md`, `config/nero.env`, `docs/status/deployment_log.md`,
`docs/status/current_bringup_status.md`, `docs/status/bringup_checklist.md`,
`docs/phases/机器人部署与调试行动路线.md`, `docs/phases/s10_2_sdk_motion_plan.md`,
`docs/phases/s10_3_ros_motion_plan.md`, `scripts/ros_single_joint_step.py`.

Verification:
Post-SDK ROS snapshot is clean. S10.3 script static compilation passed. No ROS
motion was sent by this agent.

Route updates:
S10.3 ROS dry-run is next.

Open risks:

- S10.3 requires an Arm A ROS control driver with `auto_enable:=true` and
  `control_enabled:=true`; do not leave the dual read-only driver running.
- Intentional emergency-stop recovery remains untested.
- No Cartesian, MoveIt, MIT/JS, raw CAN, dual-arm, or dexterous-hand motion is
  allowed in S10.3.

Next:
Start the Arm A ROS control driver, run the S10.3 dry-run, verify only
`joint1 +2 deg`, then decide whether to execute.

## 2026-06-25 - S10.3 ROS Dry-Run Passed

Phase: S10 首次低速运动

Goal:
Verify the ROS command target before sending a real ROS motion command.

Action:
Operator ran `scripts/ros_single_joint_step.py` in dry-run mode inside the
Humble container.

Commands / evidence:

- Command:
  `NERO_CONTAINER_NAME=nero-humble-s10-ros-tool bash scripts/run_humble_container.sh python3 /workspace/nero/scripts/ros_single_joint_step.py --namespace arm_a --joint joint1 --delta-deg 2`
- Feedback topic: `/arm_a/feedback/joint_states`.
- Command topic: `/arm_a/control/move_j`.
- Current degrees:
  `[55.498000000000005, 70.797, -29.62, 41.599000000000004, 21.6, -39.998, -35.505]`.
- Target degrees:
  `[57.498000000000005, 70.797, -29.62, 41.599000000000004, 21.6, -39.998, -35.505]`.
- Pre-status:
  `ctrl_mode=1`, `arm_status=0`, `mode_feedback=1`, `motion_status=0`.
- Script ended with:
  `Dry run only. Add --execute after the S10.3 safety gate is confirmed.`

Result:

- S10.3 ROS dry-run is accepted.
- No ROS motion has been executed yet.

Deployment choices:

- Proceed to S10.3 ROS execution only if the Arm A ROS control driver remains
  running, the J1 swept area remains clear, and no Web/SDK command is active.
- Keep the command as Arm A only, `joint1 +2 deg`, then return to original
  angle.

Files changed:
`agent.md`, `config/nero.env`, `docs/status/deployment_log.md`,
`docs/status/current_bringup_status.md`, `docs/status/bringup_checklist.md`,
`docs/phases/机器人部署与调试行动路线.md`, `docs/phases/s10_3_ros_motion_plan.md`.

Verification:
Dry-run target changes only `joint1` by `+2 deg`; pre-status is healthy.

Route updates:
S10.3 ROS execution is pending.

Open risks:

- ROS control driver uses `auto_enable:=true control_enabled:=true`; keep only
  the Arm A control driver active.
- Intentional emergency-stop recovery remains untested.

Next:
Run the S10.3 `--execute` command if the safety gate remains true.

## 2026-06-25 - S10.3 ROS J1 Motion Passed, Post-Snapshot Pending

Phase: S10 首次低速运动

Goal:
Record the first ROS-controlled real motion result.

Action:
Operator executed the S10.3 ROS single-joint step on Arm A.

Commands / evidence:

- Command:
  `NERO_CONTAINER_NAME=nero-humble-s10-ros-tool bash scripts/run_humble_container.sh python3 /workspace/nero/scripts/ros_single_joint_step.py --execute --namespace arm_a --joint joint1 --delta-deg 2`
- Operator report: J1 angle change was visually observable and returned to the
  original position.
- Feedback topic: `/arm_a/feedback/joint_states`.
- Command topic: `/arm_a/control/move_j`.
- Current degrees:
  `[55.498000000000005, 70.799, -29.62, 41.599000000000004, 21.6, -39.999, -35.505]`.
- Target degrees:
  `[57.498000000000005, 70.799, -29.62, 41.599000000000004, 21.6, -39.999, -35.505]`.
- After-step degrees:
  `[57.294000000000004, 70.801, -29.615000000000002, 41.595, 21.6, -39.999, -35.505]`.
- After-return degrees:
  `[55.743, 70.798, -29.613999999999997, 41.598, 21.6, -39.999, -35.505]`.
- Final status:
  `ctrl_mode=1`, `arm_status=0`, `mode_feedback=1`, `motion_status=1`.
- Script completed with:
  `S10.3 ROS single-joint step completed.`

Result:

- S10.3 ROS motion is accepted by operator observation and script target
  tolerance.
- J1 return error was about `0.245 deg`, within script tolerance `0.3 deg`.
- Final printed `motion_status=1` is an observation item, so S10.3 still needs
  a post-motion dual-arm ROS read-only snapshot before full acceptance.

Deployment choices:

- Stop the Arm A ROS control driver before starting the dual-arm read-only
  validation driver.
- Do not proceed to Cartesian, MoveIt, MIT/JS, dual-arm, raw CAN, or dexterous
  hand motion until S10.3 post-motion validation is accepted.

Files changed:
`agent.md`, `config/nero.env`, `docs/status/deployment_log.md`,
`docs/status/current_bringup_status.md`, `docs/status/bringup_checklist.md`,
`docs/phases/机器人部署与调试行动路线.md`, `docs/phases/s10_3_ros_motion_plan.md`.

Verification:
Script output and operator observation indicate successful ROS motion and
return. Post-motion ROS read-only snapshot is still pending.

Route updates:
S10.3 post-motion ROS read-only validation is next.

Open risks:

- Final printed `motion_status=1` needs interpretation through the next
  read-only snapshot.
- Intentional emergency-stop recovery remains untested.

Next:
Stop the Arm A ROS control driver, start dual-arm read-only validation, and
capture a post-ROS snapshot.

## 2026-06-25 - S10.3 Post-ROS Snapshot Accepted

Phase: S10 首次低速运动

Goal:
Accept the post-ROS read-only validation and close the Arm A Web/SDK/ROS
single-joint motion ladder.

Action:
Read `docs/evidence/ros_snapshots/20260625_064243/`.

Commands / evidence:

- Snapshot: `docs/evidence/ros_snapshots/20260625_064243/`.
- Snapshot `README.md`: `Failed capture commands: 0`.
- Topic list includes complete `/arm_a/...` and `/arm_b/...` feedback and
  control topics.
- Arm A joint-state frequency: about `200.0 Hz`.
- Arm B joint-state frequency: about `200.0 Hz`.
- Arm A `arm_status`:
  - `ctrl_mode: 1`
  - `arm_status: 0`
  - `mode_feedback: 1`
  - `motion_status: 0`
  - `err_status: 0`
  - all joint angle limits `false`
  - all joint communication statuses `false`
- Arm B `arm_status`:
  - `ctrl_mode: 1`
  - `arm_status: 6`
  - `mode_feedback: 1`
  - `motion_status: 1`
  - `err_status: 0`
  - all joint angle limits `false`
  - all joint communication statuses `false`
- Arm A post-ROS joint positions in radians:
  `[0.9686228282718131, 1.2356756571194656, -0.5170188843182802,
  0.7260569688296411, 0.3769911184307752, -0.6981142475052119,
  -0.6197140575056266]`.

Result:

- S10.3 ROS single-joint motion is fully accepted.
- The final printed `motion_status=1` from the execution script is resolved by
  the post-motion snapshot showing Arm A `motion_status=0`.
- Arm A has now passed Web, SDK, and ROS single-joint low-speed motion with
  post-motion ROS read-only validation.

Deployment choices:

- Do not broaden immediately to Cartesian, MoveIt, MIT/JS, raw CAN, dual-arm,
  or dexterous-hand motion.
- Next preferred step is S10.4 stop/recovery and control-source closure.
- If Arm B motion parity is required before S11/S12, repeat the same minimal
  Web/SDK/ROS ladder on Arm B with separate post-motion snapshots.

Files changed:
`agent.md`, `config/nero.env`, `docs/status/deployment_log.md`,
`docs/status/current_bringup_status.md`, `docs/status/bringup_checklist.md`,
`docs/phases/机器人部署与调试行动路线.md`, `docs/phases/s10_3_ros_motion_plan.md`.

Verification:
Post-ROS snapshot is complete and clean for both arms.

Route updates:
S10.3 accepted. S10.4 stop/recovery and safe control-source closure is next.

Open risks:

- Intentional emergency-stop recovery remains untested.
- Arm B has not yet gone through the same motion ladder.
- External lab-frame transforms for dual-arm coordination remain unmeasured.

Next:
Prepare S10.4 stop/recovery and control-source closure, then decide whether to
repeat minimal motion on Arm B or defer to later dual-arm planning.

## 2026-06-25 - S10.4 Closure Plan Prepared

Phase: S10 首次低速运动

Goal:
Prepare a no-motion stop/recovery and control-source closure step before
replicating the first-motion ladder on Arm B.

Action:
Created the S10.4 closure document and a read-only control-source audit script.
No emergency stop, power cut, Web motion, SDK motion, ROS motion, raw CAN
command, Cartesian command, or dual-arm command was sent by the agent.

Commands / evidence:

- New procedure: `docs/results/s10_4_stop_recovery_closure.md`.
- New audit helper: `scripts/s10_control_source_audit.sh`.
- Codex-session audit output:
  `docs/results/s10_4_control_source_audit_codex_20260625_150052.txt`.
- Last accepted motion evidence remains
  `docs/evidence/ros_snapshots/20260625_064243/`.

Result:

- S10.4 is prepared. A Codex-session audit was saved, but live
  desktop-terminal audit is still pending because the Codex session could not
  see the CAN interfaces.
- Recommended handoff state before Arm B motion is `handoff_to_arm_b`.
- Intentional emergency-stop recovery and power-cut recovery remain deferred.

Deployment choices:

- Stop or account for any Arm A ROS control driver before Arm B motion.
- Dual-arm read-only monitoring may be used for observation, but should be
  stopped before Arm B Web/SDK/ROS motion so only one deliberate control source
  remains.
- Arm B should repeat the same minimal ladder as Arm A: Web single-joint,
  SDK single-joint, ROS single-joint, each followed by read-only validation.

Files changed:
`agent.md`, `config/nero.env`, `docs/status/deployment_log.md`,
`docs/status/current_bringup_status.md`, `docs/status/bringup_checklist.md`,
`docs/phases/机器人部署与调试行动路线.md`,
`docs/results/s10_4_stop_recovery_closure.md`,
`docs/results/s10_4_control_source_audit_codex_20260625_150052.txt`,
`scripts/s10_control_source_audit.sh`.

Verification:
`bash -n scripts/s10_control_source_audit.sh` passed. The script was also run
once from the Codex session and reported `can_arm_a` and `can_arm_b` as not
visible, Docker status unavailable without interactive sudo, and no
NERO-related host process. Because the CAN interfaces were not visible from
that session, this does not replace live desktop-terminal audit.

Route updates:
S10.4 is now the active immediate step. Arm B replication starts only after
S10.4 closure is accepted.

Open risks:

- Intentional emergency-stop recovery remains untested.
- Arm B has not yet gone through motion parity.
- Active control sources must be confirmed from the live machine before any
  further motion.

Next:
Run the S10.4 audit from the real desktop terminal, record the handoff state,
then start Arm B first-motion replication if the audit is clean.

## 2026-06-25 - S10.4 Live Audit Accepted And Git Boundary Defined

Phase: S10 首次低速运动 / repository baseline

Goal:
Accept the live S10.4 closure and prepare the project for the first git commit.

Action:
Recorded the operator's real desktop-terminal S10.4 audit and defined which
workspace contents belong in the baseline repository.

Commands / evidence:

- Live audit output saved to
  `docs/results/s10_4_control_source_audit_live_20260625_150438.txt`.
- `can_arm_a`: UP, LOWER_UP, ERROR-ACTIVE, bitrate `1000000`.
- `can_arm_b`: UP, LOWER_UP, ERROR-ACTIVE, bitrate `1000000`.
- NERO-related Docker containers: none.
- NERO-related host processes: none.
- Upstream repo status checks were clean:
  - `upstream/agx_arm_ros`
  - `upstream/pyAgxArm`
  - `upstream/piper_ros`
- Upstream commits recorded in `README.md`:
  - `agx_arm_ros`: `c73d33f2ab377447261423f1b881bd89c6663627`
  - `pyAgxArm`: `a226840db0c3d5c5dc7f3ec78d6cef1a6800f9e6`
  - `piper_ros`: `2dc30fca68cbf4e04d1d0bc15c123d026380ece7`

Result:

- S10.4 no-motion control-source closure is accepted.
- Handoff state is `handoff_to_arm_b`.
- The next operational step is Arm B Web/SDK/ROS first-motion replication.
- Before that, create the first repository baseline commit.

Deployment choices:

- Track `docs/`, `scripts/`, `examples/`, `config/`, `docker/`, `README.md`,
  and `agent.md`.
- Do not track `upstream/`, because the repos are clean and reproducible from
  URL plus commit.
- Do not track `.venv/`, local agent metadata, Python caches, or ROS build
  outputs.
- Keep `docs/` tracked even though it contains large CAD and evidence files;
  it is part of this deployment package.

Files changed:
`.gitignore`, `README.md`, `agent.md`, `config/nero.env`,
`docs/status/current_bringup_status.md`, `docs/status/bringup_checklist.md`,
`docs/status/deployment_log.md`, `docs/phases/机器人部署与调试行动路线.md`,
`docs/results/s10_4_stop_recovery_closure.md`,
`docs/results/s10_4_control_source_audit_live_20260625_150438.txt`.

Verification:
S10.4 live audit is clean. Upstream working trees are clean. Git is installed
but the root `.git/` directory is currently an empty invalid repository
directory and must be converted into a valid git repository before committing.

Route updates:
S10.4 accepted. First git baseline commit is next; Arm B replication follows.

Open risks:

- First commit will include large `docs/` assets, about `434 MB`.
- Remote hosting may later require Git LFS or a different artifact policy, but
  local baseline commit can proceed now.

Next:
Initialize git, stage the project package according to `.gitignore`, review the
staged set, and create the first commit.

## 2026-06-25 - Git Repository Initialized And Baseline Staged

Phase: repository baseline

Goal:
Create the first git baseline for the NERO deployment package before Arm B
motion replication.

Action:
Converted the project root into a valid git repository and staged the baseline
package according to `.gitignore`.

Commands / evidence:

- `git init` succeeded after removing the previous empty invalid `.git/`
  directory.
- Default branch HEAD was set to `main`.
- `git add .` staged the project package.
- `git diff --cached --name-only` showed no staged `upstream/`, `.venv/`,
  `.agents/`, `.codex/`, root `bash`, Python cache, `__MACOSX/`, or `._*`
  paths.
- Staged file count before commit: `126`.

Result:

- The repository baseline is ready for the first commit.
- `upstream/` remains present locally but ignored because the three upstream
  working trees are clean and reproducible from `README.md`.
- `docs/` remains tracked as part of the deployment evidence package.

Deployment choices:

- Commit on branch `main`.
- Commit message: `Initial NERO bring-up baseline`.

Verification:
Shell scripts passed `bash -n`. Python helper scripts passed `py_compile`.

Route updates:
After the baseline commit, proceed to Arm B Web/SDK/ROS first-motion
replication using the same staged procedure that passed on Arm A.

Open risks:

- The baseline contains large CAD/evidence assets in `docs/`; this is accepted
  for local traceability. Remote publishing may need a separate artifact or LFS
  policy.

Next:
Run the first commit.

## 2026-06-25 - Arm B First-Motion Replication Prepared

Phase: S10 首次低速运动

Goal:
Start Arm B motion validation after Arm A Web/SDK/ROS ladder, S10.4 closure,
and the first git baseline commit.

Action:
Created the Arm B first-motion replication plan and updated project status,
checklist, route, and environment defaults.

Commands / evidence:

- New procedure: `docs/phases/s10_5_arm_b_first_motion_plan.md`.
- Current accepted handoff state from S10.4: `handoff_to_arm_b`.
- Arm B identity:
  - Web SSID: `agx-7ax-armB`
  - CAN: `can_arm_b`
  - ROS namespace: `arm_b`
  - USB bus: `1-11:1.0`
- Baseline git commit exists:
  `fb8a262 Initial NERO bring-up baseline`.

Result:

- S10.5 is prepared but not executed.
- The next real motion is Arm B Web-only J1 `+2 deg`, then return to the
  original angle.
- SDK and ROS Arm B motion remain pending until S10.5 Web motion and post-Web
  read-only snapshot pass.

Deployment choices:

- Use J1 again because Arm A showed J7 is hard to observe visually and J1
  `+2 deg` is observable.
- Keep the Arm B Web first step narrower than Arm A's actual Web result: one
  joint only, not all 7 degrees of freedom.
- Require a fresh control-source audit before touching Arm B Web motion.
- Require a post-Web dual-arm ROS read-only snapshot before SDK or ROS motion
  on Arm B.

Files changed:
`agent.md`, `config/nero.env`, `docs/status/current_bringup_status.md`,
`docs/status/bringup_checklist.md`, `docs/status/deployment_log.md`,
`docs/phases/机器人部署与调试行动路线.md`,
`docs/phases/s10_5_arm_b_first_motion_plan.md`.

Verification:
`bash -n scripts/*.sh` passed. Python helper scripts passed `py_compile`.
S10.5 references were checked across status, checklist, route, agent rules, and
environment defaults. No Arm B motion has been sent.

Route updates:
Immediate next step is S10.5 Arm B Web first motion.

Open risks:

- Arm B J1 swept area must be checked independently; do not assume Arm A
  clearance applies to Arm B.
- Operator must verify Web is connected to Arm B, not Arm A.
- Intentional emergency-stop recovery remains deferred.

Next:
Run the S10.5 pre-motion gate and Web J1 `+2 deg` return test on Arm B.

## 2026-06-25 - S10.5 Arm B Audit And Snapshot Clean

Phase: S10 首次低速运动

Goal:
Record the Arm B S10.5 pre-motion audit and the following read-only validation
snapshot.

Action:
Read the operator-provided audit output and ROS read-only snapshot
`docs/evidence/ros_snapshots/20260625_072129/`.

Commands / evidence:

- Pre-motion audit saved to:
  `docs/results/s10_5_control_source_audit_live_20260625_152039.txt`.
- Audit result:
  - `can_arm_a`: UP, LOWER_UP, ERROR-ACTIVE, bitrate `1000000`.
  - `can_arm_b`: UP, LOWER_UP, ERROR-ACTIVE, bitrate `1000000`.
  - NERO-related Docker containers: none.
  - NERO-related host processes: none.
- Snapshot:
  `docs/evidence/ros_snapshots/20260625_072129/`.
- Snapshot `README.md`: `Failed capture commands: 0`.
- Topic list includes complete `/arm_a/...` and `/arm_b/...` feedback and
  control topics.
- Arm A joint-state frequency: about `200 Hz`.
- Arm B joint-state frequency: about `200 Hz`.
- Arm A `arm_status`: `err_status: 0`, all joint angle limits `false`, all
  joint communication statuses `false`.
- Arm B `arm_status`: `err_status: 0`, all joint angle limits `false`, all
  joint communication statuses `false`.
- Arm B sampled joint positions in radians:
  `[0.5724505413616201, 1.3979912775549381, -0.3002140846355446,
  0.3630110311223006, -1.2374035330789397, 0.37346555334174664,
  0.16057029118347835]`.

Result:

- S10.5 audit and read-only validation are clean.
- S10.5 is not fully accepted yet because the chat log has not explicitly
  recorded whether Arm B Web J1 `+2 deg` actually moved normally and returned
  to the original angle.

Deployment choices:

- Do not skip the SDK dry-run just because Arm A passed.
- It is acceptable to streamline S10.6 by running dry-run and, if the printed
  target/status are correct, immediately running the execute command manually.
- Keep post-motion ROS read-only snapshots after each control layer.

Files changed:
`agent.md`, `config/nero.env`, `docs/status/current_bringup_status.md`,
`docs/status/bringup_checklist.md`, `docs/status/deployment_log.md`,
`docs/phases/机器人部署与调试行动路线.md`,
`docs/phases/s10_5_arm_b_first_motion_plan.md`,
`docs/results/s10_5_control_source_audit_live_20260625_152039.txt`,
`docs/evidence/ros_snapshots/20260625_072129/`.

Verification:
Snapshot is complete and clean for both arms. Web motion outcome needs one
operator confirmation before S10.6.

Route updates:
S10.6 SDK can start after the operator confirms Arm B Web J1 motion and return.

Open risks:

- Moving faster is acceptable only by reducing waiting between gates, not by
  removing gates.
- Intentional emergency-stop recovery remains deferred.

Next:
Confirm Arm B Web J1 `+2 deg` motion and return, then run S10.6 SDK dry-run on
`can_arm_b`.

## 2026-06-25 - S10.5 Accepted And S10.6 SDK Dry-Run Accepted

Phase: S10 首次低速运动

Goal:
Close Arm B Web first motion and accept the Arm B SDK dry-run before SDK
execution.

Action:
Recorded operator confirmation that Arm B Web motion was normal, then recorded
the SDK dry-run output and read-only snapshot `20260625_072742`.

Commands / evidence:

- Operator statement: Arm B Web side was normal.
- SDK dry-run command:
  `.venv/nero-sdk/bin/python examples/nero_sdk_single_joint_step.py --channel can_arm_b --firmware v112 --joint 1 --delta-deg 2 --speed-percent 5`
- SDK dry-run output:
  - firmware: `{'software_version': '1.121'}`
  - current degrees:
    `[32.799, 80.10000000000001, -17.199, 20.799, -70.9, 21.398,
    9.200000000000001]`
  - target degrees:
    `[34.799, 80.10000000000001, -17.199, 20.799, -70.9, 21.398,
    9.200000000000001]`
  - `pre_status`: `CAN_CTRL`, `NORMAL`, `MOVE_J`,
    `REACH_TARGET_POS_SUCCESSFULLY`
  - dry run only; no SDK motion occurred
- Read-only snapshot:
  `docs/evidence/ros_snapshots/20260625_072742/`.
- Snapshot `README.md`: `Failed capture commands: 0`.
- Arm A joint-state frequency: about `200 Hz`.
- Arm B joint-state frequency: about `200 Hz`.
- Arm A and Arm B `err_status: 0`.
- Arm A and Arm B joint angle limits and joint communication statuses: all
  `false`.

Result:

- S10.5 Arm B Web first motion is accepted.
- S10.6 Arm B SDK dry-run is accepted.
- S10.6 SDK execution is pending.

Deployment choices:

- Proceed faster by chaining the next commands manually, but do not skip gates.
- Before SDK `--execute`, stop the dual-arm read-only driver that was launched
  for the snapshot.
- Keep SDK execution at J1 `+2 deg`, speed `5%`, then return to the original
  angle.

Files changed:
`agent.md`, `config/nero.env`, `docs/status/current_bringup_status.md`,
`docs/status/bringup_checklist.md`, `docs/status/deployment_log.md`,
`docs/phases/机器人部署与调试行动路线.md`,
`docs/phases/s10_5_arm_b_first_motion_plan.md`,
`docs/phases/s10_6_arm_b_sdk_motion_plan.md`,
`docs/evidence/ros_snapshots/20260625_072742/`.

Verification:
SDK dry-run target changes only Arm B J1 by `+2 deg`. Read-only snapshot is
complete and clean for both arms.

Route updates:
Immediate next step is S10.6 SDK execution on `can_arm_b`.

Open risks:

- Running SDK execute while the dual-arm read-only driver is still active would
  violate the one-motion-control-source rule. Stop the driver first.
- Intentional emergency-stop recovery remains deferred.

Next:
Stop dual-arm read-only, run the S10.6 SDK execute command, then capture a
post-execute read-only snapshot.

## 2026-06-25 - S10.6 Arm B SDK Motion Accepted And S10.7 Prepared

Phase: S10 首次低速运动

Goal:
Accept Arm B SDK execution and prepare the Arm B ROS single-joint replication
step.

Action:
Recorded the operator's SDK execution result, read post-SDK snapshot
`docs/evidence/ros_snapshots/20260625_074048/`, and created the S10.7 ROS plan.

Commands / evidence:

- Operator report: Arm B SDK real motion was observed successfully and execution
  was smooth.
- Full SDK execute terminal output was not pasted, so exact `after_step_deg`
  and `after_return_deg` values are not recorded.
- Post-SDK snapshot:
  `docs/evidence/ros_snapshots/20260625_074048/`.
- Snapshot `README.md`: `Failed capture commands: 0`.
- Topic list includes complete `/arm_a/...` and `/arm_b/...` feedback and
  control topics.
- Arm A joint-state frequency: about `200 Hz`.
- Arm B joint-state frequency: about `200 Hz`.
- Arm A `arm_status`: `err_status: 0`, all joint angle limits `false`, all
  joint communication statuses `false`.
- Arm B `arm_status`: `err_status: 0`, all joint angle limits `false`, all
  joint communication statuses `false`.
- Arm B sampled joint positions in radians:
  `[0.57246799465414, 1.3979563709698983, -0.30017917805050476,
  0.36302848441482055, -1.2374035330789397, 0.37355281980434635,
  0.16053538459843844]`.
- New ROS plan:
  `docs/phases/s10_7_arm_b_ros_motion_plan.md`.

Result:

- S10.6 Arm B SDK execution is accepted.
- S10.7 Arm B ROS motion is prepared but not executed.

Deployment choices:

- S10.7 must start with dry-run, not execute.
- Stop the dual-arm read-only driver before starting the Arm B ROS control
  driver.
- Start only the Arm B ROS control driver for S10.7:
  `namespace:=arm_b`, `can_port:=can_arm_b`, `auto_enable:=true`,
  `control_enabled:=true`, `speed_percent:=5`.
- Keep the motion target as `joint1 +2 deg`, then return to original angle.

Files changed:
`agent.md`, `config/nero.env`, `docs/status/current_bringup_status.md`,
`docs/status/bringup_checklist.md`, `docs/status/deployment_log.md`,
`docs/phases/机器人部署与调试行动路线.md`,
`docs/phases/s10_6_arm_b_sdk_motion_plan.md`,
`docs/phases/s10_7_arm_b_ros_motion_plan.md`,
`docs/evidence/ros_snapshots/20260625_074048/`.

Verification:
Post-SDK snapshot is complete and clean for both arms.

Route updates:
Immediate next step is S10.7 ROS dry-run on `/arm_b`.

Open risks:

- ROS control driver uses `auto_enable:=true` and `control_enabled:=true`; keep
  only Arm B control active.
- Intentional emergency-stop recovery remains deferred.

Next:
Stop dual-arm read-only, start the Arm B ROS control driver, and run S10.7
dry-run.

## 2026-06-25 - S10.7 Arm B ROS Dry-Run Accepted

Phase: S10 首次低速运动

Goal:
Accept the Arm B ROS `move_j` dry-run before real ROS execution.

Action:
Recorded the S10.7 dry-run output from `scripts/ros_single_joint_step.py`.

Commands / evidence:

- Dry-run command:
  `NERO_CONTAINER_NAME=nero-humble-s10-ros-tool bash scripts/run_humble_container.sh python3 /workspace/nero/scripts/ros_single_joint_step.py --namespace arm_b --joint joint1 --delta-deg 2`
- Namespace: `arm_b`.
- Feedback topic: `/arm_b/feedback/joint_states`.
- Command topic: `/arm_b/control/move_j`.
- Current degrees:
  `[32.798, 80.098, -17.204, 20.797, -70.9, 21.403, 9.198]`.
- Target degrees:
  `[34.798, 80.098, -17.204, 20.797, -70.9, 21.403, 9.198]`.
- `pre_status`: `ctrl_mode=1`, `arm_status=0`, `mode_feedback=1`,
  `motion_status=0`.
- Script ended with:
  `Dry run only. Add --execute after the S10.3 safety gate is confirmed.`

Result:

- S10.7 ROS dry-run is accepted.
- Target changes only Arm B `joint1` by `+2 deg`.
- No ROS motion has been executed yet.

Deployment choices:

- Proceed to S10.7 ROS execution only if the Arm B ROS control driver remains
  running and no other control source is active.
- Keep the command as Arm B only, `joint1 +2 deg`, then return to original
  angle.

Files changed:
`agent.md`, `config/nero.env`, `docs/status/current_bringup_status.md`,
`docs/status/bringup_checklist.md`, `docs/status/deployment_log.md`,
`docs/phases/机器人部署与调试行动路线.md`,
`docs/phases/s10_7_arm_b_ros_motion_plan.md`.

Verification:
Dry-run target changes only `joint1` by `+2 deg`; pre-status is healthy.

Route updates:
S10.7 ROS execution is pending.

Open risks:

- ROS control driver uses `auto_enable:=true control_enabled:=true`; keep only
  the Arm B control driver active.
- Intentional emergency-stop recovery remains deferred.

Next:
Run the S10.7 `--execute` command if the safety gate remains true.

## 2026-06-25 - S10.7 Arm B ROS Motion Accepted

Phase: S10 首次低速运动

Goal:
Accept the Arm B ROS single-joint motion and post-motion read-only validation.

Action:
Recorded the ROS execute output and read post-ROS snapshot
`docs/evidence/ros_snapshots/20260625_074953/`.

Commands / evidence:

- ROS execute command:
  `NERO_CONTAINER_NAME=nero-humble-s10-ros-tool bash scripts/run_humble_container.sh python3 /workspace/nero/scripts/ros_single_joint_step.py --execute --namespace arm_b --joint joint1 --delta-deg 2`
- Namespace: `arm_b`.
- Feedback topic: `/arm_b/feedback/joint_states`.
- Command topic: `/arm_b/control/move_j`.
- Current degrees:
  `[32.798, 80.098, -17.204, 20.798000000000002, -70.9, 21.402, 9.198]`.
- Target degrees:
  `[34.798, 80.098, -17.204, 20.798000000000002, -70.9, 21.402, 9.198]`.
- `pre_status`: `ctrl_mode=1`, `arm_status=0`, `mode_feedback=1`,
  `motion_status=0`.
- `after_step_deg`:
  `[34.553, 80.09700000000001, -17.209, 20.791, -70.9, 21.402, 9.198]`.
- `after_return_deg`:
  `[33.026, 80.096, -17.207, 20.797, -70.9, 21.402, 9.198]`.
- `final_status`: `ctrl_mode=1`, `arm_status=0`, `mode_feedback=1`,
  `motion_status=0`.
- Script completed with:
  `S10.3 ROS single-joint step completed.`
- Post-ROS snapshot:
  `docs/evidence/ros_snapshots/20260625_074953/`.
- Snapshot `README.md`: `Failed capture commands: 0`.
- Arm A joint-state frequency: about `200 Hz`.
- Arm B joint-state frequency: about `200 Hz`.
- Arm A and Arm B `err_status: 0`.
- Arm A and Arm B joint angle limits and joint communication statuses: all
  `false`.
- Snapshot sampled Arm B J1 is about `32.797 deg`, consistent with settled
  return to the original angle.

Result:

- S10.7 Arm B ROS single-joint motion is accepted.
- Arm B has now passed Web, SDK, and ROS low-speed single-joint motion with
  post-motion read-only validation.

Deployment choices:

- Do not proceed directly to dual-arm coordination, Cartesian, MoveIt, or
  dexterous-hand motion.
- Next step is S10.8 closure: stop/account for the Arm B ROS control driver and
  audit active control sources.

Files changed:
`agent.md`, `config/nero.env`, `docs/status/current_bringup_status.md`,
`docs/status/bringup_checklist.md`, `docs/status/deployment_log.md`,
`docs/phases/机器人部署与调试行动路线.md`,
`docs/phases/s10_7_arm_b_ros_motion_plan.md`,
`docs/evidence/ros_snapshots/20260625_074953/`.

Verification:
ROS execute completed successfully, and post-ROS snapshot is complete and clean
for both arms.

Route updates:
S10.7 accepted. S10.8 closure is next.

Open risks:

- Intentional emergency-stop recovery remains deferred.
- Dual-arm coordinated motion has not been tested.
- External lab-frame transforms remain unmeasured.

Next:
Stop/account for Arm B ROS control driver, run the control-source audit, and
record S10.8 closure before any broader motion phase.

## 2026-06-25 - S10.8 Dual-Arm First-Motion Closure Accepted

Phase: S10 首次低速运动

Goal:
Close S10 after both arms passed Web, SDK, and ROS first-motion ladders.

Action:
Recorded the final control-source audit and updated the project route to enter
S11 dual-arm experiment baseline.

Commands / evidence:

- Final audit saved to:
  `docs/results/s10_8_control_source_audit_live_20260625_155538.txt`.
- `can_arm_a`: UP, LOWER_UP, ERROR-ACTIVE, bitrate `1000000`.
- `can_arm_b`: UP, LOWER_UP, ERROR-ACTIVE, bitrate `1000000`.
- NERO-related Docker containers: none.
- NERO-related host processes: none.
- S10 closure document:
  `docs/results/s10_8_dual_arm_first_motion_closure.md`.

Result:

- S10 is complete.
- Arm A and Arm B both passed Web, SDK, and ROS low-speed single-joint motion.
- No Web, SDK, or ROS motion process remains active.
- CAN interfaces may remain UP for the next phase.

Deployment choices:

- Do not proceed directly to coordinated dual-arm motion.
- Next phase is S11 dual-arm experiment baseline and coordinate closure.
- Former S11/S12 route items are renumbered: end-effector work moves to S14,
  and manipulation application integration moves to S15.

Files changed:
`agent.md`, `config/nero.env`, `docs/status/current_bringup_status.md`,
`docs/status/bringup_checklist.md`, `docs/status/deployment_log.md`,
`docs/phases/机器人部署与调试行动路线.md`,
`docs/results/s10_8_control_source_audit_live_20260625_155538.txt`,
`docs/results/s10_8_dual_arm_first_motion_closure.md`.

Verification:
Final audit is clean and confirms no active NERO Docker or host control
process.

Route updates:
S10 accepted and closed. S11 dual-arm experiment baseline is next.

Open risks:

- Intentional emergency-stop recovery remains deferred.
- Dual-arm coordinated motion has not been tested.
- External lab-frame transforms remain unmeasured.

Next:
Create and execute the S11 baseline plan.

## 2026-06-25 - S11 Dual-Arm Experiment Baseline Plan Prepared

Phase: S11 双臂实验基线与坐标闭环

Goal:
Prepare the acceptance-first plan for turning the two individually validated
arms into a measurable dual-arm experiment platform.

Action:
Created the S11 plan and synchronized the route, current status, README, agent
rules, and environment variables with the new phase ordering.

Commands / evidence:

- S11 plan and templates:
  - `docs/phases/s11_dual_arm_experiment_baseline.md`
  - `docs/phases/s11_measurement_notes.md`
  - `docs/phases/s11_static_tf_plan.md`
  - `docs/phases/s11_rosbag_logging_plan.md`
- `bash -n scripts/*.sh`
- `python3 -m py_compile examples/nero_read_state.py examples/nero_sdk_single_joint_step.py scripts/ros_single_joint_step.py`
- S10 closure commit exists before this planning step:
  `3507a8a Close S10 dual-arm first motion`.

Result:

- S11 is prepared but not executed.
- `lab_world`, measured A/B base transforms, static TF, TCP baseline, rosbag
  topics, and experiment-run directory conventions are now explicit.
- Measurement, static TF, and rosbag/logging templates exist with `TBD` fields
  awaiting physical execution.
- End-effector installation is renumbered to S14, and application integration
  is renumbered to S15.

Deployment choices:

- Do not expand motion during S11.
- Keep current ROS `effector_type:=none` and TCP offset zero until a physical
  end effector is installed and measured.
- Require static TF and logging evidence before S12 control-isolation tests.

Files changed:
`agent.md`, `README.md`, `config/nero.env`, `docs/status/current_bringup_status.md`,
`docs/status/deployment_log.md`, `docs/phases/机器人部署与调试行动路线.md`,
`docs/phases/s11_dual_arm_experiment_baseline.md`, `docs/phases/s11_measurement_notes.md`,
`docs/phases/s11_static_tf_plan.md`, `docs/phases/s11_rosbag_logging_plan.md`.

Verification:
Local checks passed:

- `bash -n scripts/*.sh`
- `python3 -m py_compile examples/nero_read_state.py examples/nero_sdk_single_joint_step.py scripts/ros_single_joint_step.py`

Route updates:
S11, S12, and S13 are now explicit pre-manipulation phases. Former end-effector
and application phases are S14 and S15.

Open risks:

- `lab_world` has not yet been physically marked.
- A/B base transforms have not yet been measured.
- Static TF values are not yet available.

Next:
Run document and script checks, commit the S11 plan, then execute S11
measurement and TF validation.

## 2026-06-26 - S11 Operator Guidance Prepared

Phase: S11 双臂实验基线与坐标闭环

Goal:
Make the S11 coordinate-measurement task executable for an operator who is not
yet familiar with TF frames.

Action:
Added a Chinese-facing operator guide that explains `lab_world`, `base_link`,
translation, yaw, measurement tools, base-center marking, photo evidence, and
what values must be returned for TF review.

Commands / evidence:

- Local URDF evidence: `world_to_base_link` is fixed at zero in the current
  NERO URDF.
- Local mesh inspection: `base_link` mesh spans approximately `z=0..0.086 m`;
  `joint1` is at `z=0.138 m` relative to `base_link`.
- Operator guide: `docs/phases/s11_operator_guide.md`.

Result:
S11 can start with a pragmatic first baseline: use Arm A base center projection
as `lab_world` origin unless an external table/fixture coordinate frame is
required.

Deployment choices:

- Treat the base mounting-hole center / J1-axis projection as the practical
  x/y measurement proxy for `base_link` in the first S11 baseline.
- Record this as a measurement convention, not a new factory specification.
- Do not run motion during this measurement step.

Files changed:
`config/nero.env`, `docs/status/current_bringup_status.md`, `docs/status/deployment_log.md`,
`docs/phases/s11_dual_arm_experiment_baseline.md`, `docs/phases/s11_operator_guide.md`,
`docs/phases/机器人部署与调试行动路线.md`.

Verification:
Local checks passed:

- `bash -n scripts/*.sh`
- `python3 -m py_compile examples/nero_read_state.py examples/nero_sdk_single_joint_step.py scripts/ros_single_joint_step.py`
- `git diff --check`

Route updates:
S11 now has an operator-facing execution guide before physical measurement.

Open risks:

- Physical base centers and yaw have not yet been measured.
- RViz has not yet validated whether the chosen physical yaw reference matches
  the URDF base orientation.

Next:
Operator marks `lab_world`, measures A/B base transforms, saves photos, and
reports the values for static TF review.

## 2026-06-26 - S11 Initial Measurement Recorded

Phase: S11 双臂实验基线与坐标闭环

Goal:
Record the first physical dual-arm baseline and prepare a static-TF candidate
for RViz validation.

Action:
Recorded the operator-provided `lab_world` convention, Arm B translation, new
photo/evidence directory, and Web-frame observations. Converted the observed
A/B Web-frame relationship into a cautious Arm B yaw candidate for RViz testing.

Commands / evidence:

- Photo/evidence directory: `docs/evidence/pics/s11_measurement_20260626/`.
- Arm A natural posture screenshot: `arm A 姿态.png`.
- Arm B natural posture screenshot: `arm B 姿态.png`.
- Base drawing: `底座.png`.
- Arm size drawing: `机械臂尺寸.png`.
- Operator measurement: `x_b = 260 mm`, `y_b = 0`, `z_b = 0`.
- Operator Web-frame observation:
  - Arm A: `+x_web = +Z`, `+y_web = +Y`, `+z_web = -X`.
  - Arm B: `+x_web = +Z`, `+y_web = -Y`, `+z_web = +X`.

Result:

- `lab_world` is defined:
  - origin: Arm A base center projection.
  - `+X`: Arm A base center to Arm B base center.
  - `+Y`: left-hand direction when facing `+X`.
  - `+Z`: up.
- Arm A transform candidate is identity.
- Arm B translation candidate is `x=0.260 m, y=0, z=0`.
- Arm B yaw candidate is `3.1415926 rad`.

Deployment choices:

- Treat `x_b=0.260 m` as measured physical evidence.
- Treat Arm B yaw `pi` as a validation candidate, not final acceptance, because
  Web coordinates may not be identical to ROS `base_link`.
- Continue S11 as no-motion TF/RViz validation.

Files changed:
`agent.md`, `config/nero.env`, `docs/status/current_bringup_status.md`,
`docs/status/bringup_checklist.md`, `docs/status/deployment_log.md`,
`docs/phases/s11_measurement_notes.md`, `docs/phases/s11_static_tf_plan.md`,
`docs/phases/机器人部署与调试行动路线.md`, `docs/evidence/pics/s11_measurement_20260626/`.

Verification:
Local checks passed:

- `bash -n scripts/*.sh`
- `python3 -m py_compile examples/nero_read_state.py examples/nero_sdk_single_joint_step.py scripts/ros_single_joint_step.py`
- `git diff --check`

RViz/static-TF validation is still pending.

Route updates:
S11 is now partially measured; the next gate is static-TF publishing and RViz
confirmation.

Open risks:

- Measurement uncertainty and exact tool were not reported.
- Yaw candidate may need correction if RViz shows a 90 deg or 180 deg mismatch.
- Web-frame axes are recorded as observations, not as ROS `base_link` facts.

Next:
Run the candidate static TF commands, check `tf2_echo`, inspect RViz, and save a
post-TF read-only snapshot if the layout is correct.

## 2026-06-26 - S11 Read-Only Launch Blocked By Arm A CAN Response

Phase: S11 双臂实验基线与坐标闭环

Goal:
Start the dual-arm ROS read-only driver before static-TF validation.

Action:
Operator launched `scripts/launch_dual_ros_readonly.sh` inside the Humble
container. Arm B initialized successfully, but Arm A failed while reading the
firmware version.

Commands / evidence:

- Command:
  `bash scripts/run_humble_container.sh bash /workspace/nero/scripts/launch_dual_ros_readonly.sh`
- Launch safety settings:
  `auto_enable=false`, `control_enabled=false`.
- Arm B:
  firmware version `1.121`; feedback became ready.
- Arm A:
  `Failed to get firmware version`; node exited with code `1`.

Result:
S11 TF validation is blocked until Arm A CAN read-only communication is
restored.

Deployment choices:

- Do not enable either arm to fix this issue. Firmware read and feedback read
  do not require joint enable.
- Treat this as a CAN/USB-CAN/interface/robot-response issue, similar to the
  earlier Arm A condition that recovered after USB-CAN replug and CAN interface
  reactivation.

Files changed:
`docs/status/deployment_log.md`.

Verification:
Pending operator CAN checks.

Route updates:
No route phase change. S11 remains partially measured and pending read-only
ROS/TF validation.

Open risks:

- Arm A may not be producing CAN frames on `can_arm_a`.
- USB-CAN bus mapping may have changed after unplug/replug.
- A stale interface state may require reactivation.

Next:
Check `can_arm_a` interface state and raw frames, then replug/reactivate the Arm
A USB-CAN module if needed. Do not use Web/SDK/ROS motion during this recovery.

## 2026-06-26 - S11 Static TF Command Line Split Error

Phase: S11 双臂实验基线与坐标闭环

Goal:
Publish the S11 candidate static transforms after the dual read-only driver is
running.

Action:
Operator reported that terminal 1 is now running normally. Terminal 2 failed
while running the static TF command because the shell command was split across
newlines inside the quoted `bash -lc` string.

Commands / evidence:

- First static TF command failed with:
  `Child frame id must not be empty`.
- The next line then ran as a shell command:
  `--child-frame-id: command not found`.
- The Arm B command failed with:
  `Not enough arguments for --yaw`.
- The next line then ran as:
  `3.1415926: command not found`.

Result:

- This was a command-line quoting/newline issue, not a robot enable issue and
  not a TF-value issue.
- Added `scripts/publish_s11_static_tf_candidate.sh` so S11 static TF can be
  published without long inline shell quoting.

Deployment choices:

- Continue using the candidate values from `config/nero.env`.
- Use the wrapper script as the preferred static TF publisher.

Files changed:
`docs/status/deployment_log.md`, `docs/phases/s11_static_tf_plan.md`,
`scripts/publish_s11_static_tf_candidate.sh`.

Verification:
Local checks passed:

- `bash -n scripts/*.sh`
- `python3 -m py_compile examples/nero_read_state.py examples/nero_sdk_single_joint_step.py scripts/ros_single_joint_step.py`
- `git diff --check`

Route updates:
S11 remains in TF validation. The next action is to rerun terminal 2 with the
wrapper script.

Open risks:

- Candidate yaw still needs RViz validation after TF is successfully published.

Next:
Run:
`NERO_CONTAINER_NAME=nero-humble-s11-static-tf bash scripts/run_humble_container.sh bash /workspace/nero/scripts/publish_s11_static_tf_candidate.sh`

## 2026-06-26 - S11 Static TF Echo Passed And Runtime Target Corrected

Phase: S11 双臂实验基线与坐标闭环

Goal:
Validate that the S11 candidate static TF is publishable, then prepare for RViz
RobotModel validation.

Action:
Operator ran `tf2_echo` and confirmed the candidate transform was available:
translation `[0.260, 0.000, 0.000]` and yaw `180 deg`.

While preparing the RViz step, the local NERO URDF and `display.launch.py` were
reviewed. The URDF contains a fixed `world -> base_link` joint, and
`display.launch.py` prefixes frames as `arm_a/world`, `arm_a/base_link`, etc.
Therefore the runtime external static TF target was corrected from
`arm_*/base_link` to `arm_*/world` to avoid duplicate TF parents after
`robot_state_publisher` starts.

Commands / evidence:

- `tf2_echo lab_world arm_b/base_link` output:
  - translation `[0.260, 0.000, 0.000]`
  - RPY degree `[0.000, -0.000, 180.000]`
- URDF evidence:
  `upstream/agx_arm_ros/src/agx_arm_description/agx_arm_urdf/nero/urdf/nero_description.urdf`
  has fixed joint `world_to_base_link`.
- Launch evidence:
  `display.launch.py` applies `frame_prefix` for namespaced multi-arm TF.

Result:

- Static TF numeric candidate is confirmed publishable.
- Runtime TF target is corrected to:
  - `lab_world -> arm_a/world`
  - `lab_world -> arm_b/world`

Deployment choices:

- Keep the measured base values unchanged.
- Publish to namespaced URDF root frames for RViz/model validation.
- Continue treating Arm B yaw `pi` as a candidate until RViz confirms physical
  layout.

Files changed:
`config/nero.env`, `docs/status/deployment_log.md`, `docs/phases/s11_measurement_notes.md`,
`docs/phases/s11_static_tf_plan.md`, `scripts/publish_s11_static_tf_candidate.sh`.

Verification:
Local checks passed:

- `bash -n scripts/*.sh`
- `python3 -m py_compile examples/nero_read_state.py examples/nero_sdk_single_joint_step.py scripts/ros_single_joint_step.py`
- `git diff --check`

Route updates:
S11 static TF target is corrected for the actual URDF structure.

Open risks:

- Existing terminal 2 may still be publishing the old `base_link` target and
  should be stopped before restarting the wrapper.
- RViz visual validation remains pending.

Next:
Stop terminal 2 if it is still running, restart the static TF wrapper, verify
`tf2_echo lab_world arm_b/world`, then launch/display the two robot models.

## 2026-06-26 - S11 Dual RViz Model View Prepared

Phase: S11 双臂实验基线与坐标闭环

Goal:
Prepare a one-command RViz validation path that displays both NERO arms in the
shared `lab_world` frame.

Action:
Added an S11 RViz config with two RobotModel displays and a wrapper script that
starts two `robot_state_publisher` instances from the current NERO URDF.

Commands / evidence:

- RViz config: `rviz/s11_dual_arm.rviz`.
- Wrapper script: `scripts/launch_s11_dual_model_view.sh`.
- The script remaps:
  - Arm A `joint_states` to `/arm_a/feedback/joint_states`.
  - Arm B `joint_states` to `/arm_b/feedback/joint_states`.
- The script uses frame prefixes:
  - `arm_a/`
  - `arm_b/`

Result:
The operator can validate both arms in one RViz scene with fixed frame
`lab_world`, while keeping terminal 1 as the read-only driver and terminal 2 as
the static TF publisher.

Deployment choices:

- The wrapper does not publish control commands.
- RViz contains two RobotModel displays reading `/arm_a/robot_description` and
  `/arm_b/robot_description`.
- This avoids launching two separate RViz windows via the upstream single-arm
  `display.launch.py`.

Files changed:
`docs/status/deployment_log.md`, `docs/phases/s11_static_tf_plan.md`,
`rviz/s11_dual_arm.rviz`, `scripts/launch_s11_dual_model_view.sh`.

Verification:
Local checks passed:

- `bash -n scripts/*.sh`
- `python3 -m py_compile examples/nero_read_state.py examples/nero_sdk_single_joint_step.py scripts/ros_single_joint_step.py`
- `git diff --check`

Route updates:
S11 now has a dedicated dual-arm RViz validation tool.

Open risks:

- The candidate Arm B yaw still needs visual acceptance in RViz.
- X11 access must be explicitly allowed and revoked after RViz use.

Next:
Run terminal 4:
`NERO_CONTAINER_NAME=nero-humble-s11-rviz bash scripts/run_humble_container.sh --allow-xhost bash /workspace/nero/scripts/launch_s11_dual_model_view.sh`

## 2026-06-26 - S11 RViz Wrapper Parameter Match Fixed

Phase: S11 双臂实验基线与坐标闭环

Goal:
Fix the S11 RViz wrapper after `robot_state_publisher` failed to receive
`robot_description`.

Action:
Operator ran `scripts/launch_s11_dual_model_view.sh`. RViz started, but both
namespaced `robot_state_publisher` processes aborted because their
`robot_description` parameter was empty.

Commands / evidence:

- Command:
  `NERO_CONTAINER_NAME=nero-humble-s11-rviz bash scripts/run_humble_container.sh --allow-xhost bash /workspace/nero/scripts/launch_s11_dual_model_view.sh`
- Error:
  `robot_description parameter must not be empty`.

Result:
The wrapper's generated parameter files used the relative node key
`robot_state_publisher`, which did not reliably match namespaced nodes. The
script now writes fully qualified keys:

- `/arm_a/robot_state_publisher`
- `/arm_b/robot_state_publisher`

Deployment choices:

- Keep the wrapper approach.
- Print the temporary parameter file paths so future parameter-loading failures
  can be inspected directly.

Files changed:
`docs/status/deployment_log.md`, `scripts/launch_s11_dual_model_view.sh`.

Verification:
Local checks passed:

- `bash -n scripts/*.sh`
- `python3 -m py_compile examples/nero_read_state.py examples/nero_sdk_single_joint_step.py scripts/ros_single_joint_step.py`
- `git diff --check`

Route updates:
S11 remains in RViz visual validation.

Open risks:

- RViz visual acceptance has not yet been performed.

Next:
Rerun terminal 4 with the same wrapper command after local checks pass.

## 2026-06-26 - S11 First RViz Layout Rejected

Phase: S11 双臂实验基线与坐标闭环

Goal:
Evaluate the first RViz layout from the pure-yaw candidate transform.

Action:
Operator opened RViz successfully and saved the screenshot
`docs/evidence/pics/Rviz世界坐标系.png`. The two models appeared horizontally in the RViz
XY plane and did not match the real natural hanging posture.

Commands / evidence:

- Screenshot: `docs/evidence/pics/Rviz世界坐标系.png`.
- Previous candidate:
  - Arm A: `roll=0`, `pitch=0`, `yaw=0`.
  - Arm B: `roll=0`, `pitch=0`, `yaw=3.1415926`.
- Operator observation from Web axes:
  - Arm A: `+x_web = +Z`, `+y_web = +Y`, `+z_web = -X`.
  - Arm B: `+x_web = +Z`, `+y_web = -Y`, `+z_web = +X`.

Result:
The pure-yaw candidate is rejected for S11 RViz acceptance.

Deployment choices:

- Keep measured translation: Arm B `x=0.260 m`, `y=0`, `z=0`.
- Use the operator's Web-axis observation to derive revised 3D root rotations:
  - Arm A: `roll=0`, `pitch=-1.5707963`, `yaw=0`.
  - Arm B: `roll=3.1415926`, `pitch=-1.5707963`, `yaw=0`.
- Continue treating the revised rotations as candidates until RViz confirms the
  physical layout.

Files changed:
`config/nero.env`, `docs/status/current_bringup_status.md`,
`docs/status/deployment_log.md`, `docs/phases/s11_measurement_notes.md`,
`docs/phases/s11_static_tf_plan.md`, `docs/evidence/pics/Rviz世界坐标系.png`.

Verification:
Local checks passed:

- `bash -n scripts/*.sh`
- `python3 -m py_compile examples/nero_read_state.py examples/nero_sdk_single_joint_step.py scripts/ros_single_joint_step.py`
- `git diff --check`

Route updates:
S11 remains in RViz visual validation; static TF candidate changed from pure
yaw to full 3D root rotations.

Open risks:

- Web-frame axes may still differ from ROS root frame axes.
- Revised candidate must be validated visually in RViz.

Next:
Restart the static TF publisher with the revised candidate and rerun the S11
dual-arm RViz view.

## 2026-06-26 - S11 Revised RViz Layout Accepted

Phase: S11 双臂实验基线与坐标闭环

Goal:
Validate the revised 3D root-frame static TF candidate in RViz.

Action:
Operator restarted the static TF publisher with the revised candidate and
opened the S11 dual-arm RViz model view.

Commands / evidence:

- Revised accepted static TF values:
  - `lab_world -> arm_a/world`: `x=0`, `y=0`, `z=0`, `roll=0`,
    `pitch=-1.5707963`, `yaw=0`.
  - `lab_world -> arm_b/world`: `x=0.260`, `y=0`, `z=0`,
    `roll=3.1415926`, `pitch=-1.5707963`, `yaw=0`.
- Operator report:
  - RViz layout now matches the real dual-arm layout.
  - Moving each arm is followed by the RViz model.

Result:
S11 RViz visual validation is accepted. Final S11 closure still needs a
post-TF read-only snapshot and normal cleanup.

Deployment choices:

- Accept the revised 3D root rotations for the S11 baseline.
- Keep using `lab_world -> arm_*/world`, not `lab_world -> arm_*/base_link`,
  because the URDF already provides `world -> base_link`.

Files changed:
`config/nero.env`, `docs/status/bringup_checklist.md`,
`docs/status/current_bringup_status.md`, `docs/status/deployment_log.md`,
`docs/phases/s11_measurement_notes.md`, `docs/phases/s11_static_tf_plan.md`,
`docs/phases/机器人部署与调试行动路线.md`.

Verification:
Local checks passed:

- `bash -n scripts/*.sh`
- `python3 -m py_compile examples/nero_read_state.py examples/nero_sdk_single_joint_step.py scripts/ros_single_joint_step.py`
- `git diff --check`

Post-TF snapshot is still pending.

Route updates:
S11 visual TF validation is accepted. Next action is S11 closure evidence.

Open risks:

- Measurement tool and exact uncertainty remain unreported.
- Post-TF read-only snapshot is not yet captured.

Next:
Capture a post-TF read-only snapshot, save/confirm final RViz screenshot if
needed, stop temporary terminals, and revoke X11 root access.

## 2026-06-26 - S11 Dual-Arm Baseline Closed

Phase: S11 双臂实验基线与坐标闭环

Goal:
Close S11 after RViz visual acceptance by recording the post-TF ROS snapshot,
accepted screenshot, and X11 cleanup state.

Action:
Operator captured the post-TF read-only snapshot, saved the successful RViz
layout screenshot, and confirmed `xhost` cleanup after RViz.

Commands / evidence:

- Snapshot: `docs/evidence/ros_snapshots/20260626_055339/`.
- Snapshot README: `Failed capture commands: 0`.
- Arm A joint-state frequency: about `200 Hz`.
- Arm B joint-state frequency: about `200 Hz`.
- A/B arm status: `ctrl_mode: 1`, `arm_status: 6`, `mode_feedback: 1`,
  `motion_status: 1`, `err_status: 0`.
- A/B `joint_angle_limit`: all `false`.
- A/B `communication_status_joint`: all `false`.
- RViz accepted screenshot:
  `docs/evidence/pics/S11_RViz_accepted_dual_arm_layout.png`.
- X11 cleanup: `xhost` reported access control enabled and only
  `SI:localuser:lv-robotics`.

Result:
S11 is accepted and closed. The machine has a documented first engineering
dual-arm `lab_world` baseline, accepted static TF values, RViz feedback follow,
and a clean post-TF read-only snapshot.

Deployment choices:

- Keep the accepted runtime static TF targets as `lab_world -> arm_a/world` and
  `lab_world -> arm_b/world`, because the URDF already contains fixed
  `world -> base_link`.
- Accept the current coordinate baseline as an engineering baseline. The exact
  measurement tool and uncertainty were not quantified, so high-precision
  dual-arm manipulation must remeasure or refine the extrinsics later.
- Move the immediate next phase to S12 control isolation and logging closure.

Files changed:
`README.md`, `agent.md`, `config/nero.env`, `docs/status/bringup_checklist.md`,
`docs/status/current_bringup_status.md`, `docs/status/deployment_log.md`,
`docs/phases/s11_dual_arm_experiment_baseline.md`, `docs/phases/s11_measurement_notes.md`,
`docs/phases/s11_operator_guide.md`, `docs/phases/s11_rosbag_logging_plan.md`,
`docs/phases/s11_static_tf_plan.md`, `docs/status/setup_framework.md`,
`docs/phases/机器人部署与调试行动路线.md`,
`docs/evidence/pics/S11_RViz_accepted_dual_arm_layout.png`,
`docs/evidence/ros_snapshots/20260626_055339/`.

Verification:
Local checks passed:

- `bash -n scripts/*.sh`
- `python3 -m py_compile examples/nero_read_state.py examples/nero_sdk_single_joint_step.py scripts/ros_single_joint_step.py`
- `git diff --check`

Route updates:
S11 is no longer pending post-TF evidence. The route now enters S12 before any
dual-arm coordination, Cartesian motion, MoveIt execution, or dexterous-hand
actuation.

Open risks:

- Measurement tool and exact uncertainty remain unreported.
- Current TF baseline is accepted by RViz/operator validation, not by external
  metrology.

Next:
Run local checks, commit S11 closure, then prepare S12 tests for control
isolation and logging.

## 2026-06-26 - S12 Visible J1 Isolation Plan Prepared

Phase: S12 控制隔离与日志闭环

Goal:
Prepare a field-executable S12 test that uses a visible J1 motion while still
verifying one-arm-at-a-time control isolation.

Action:
Added an S12 plan and two helper scripts. The driver wrapper starts one arm as
the active control target and the other arm as read-only monitoring. The test
script publishes only the target arm `move_j` command and monitors both arms'
joint feedback so passive-arm movement is detected quantitatively.

Commands / evidence:

- URDF evidence: NERO `joint1` axis is local `Z`.
- S11 TF evidence:
  - Arm A local `Z` maps approximately to `lab_world -X`.
  - Arm B local `Z` maps approximately to `lab_world +X`.
- Inferred S12 signs for an intended `lab_world -Y` sweep:
  - Arm A: `joint1 +30 deg`.
  - Arm B: `joint1 -30 deg`.
- Operator reported the surrounding workspace is clear and requested a visible
  `30 deg` J1 motion for observation/reporting.

Result:
S12 is prepared but not executed.

Deployment choices:

- Keep `speed_percent=5` for the first S12 visible-motion tests.
- Use `30 deg` as the bounded visible J1 amplitude, with optional `5 deg` sign
  gate if the operator wants to confirm direction before the full motion.
- Keep S12 as one active arm at a time; this is not dual-arm coordination.
- Accept passive-arm movement tolerance of `1.0 deg` and target-arm tolerance
  of `0.7 deg` for this first S12 field test.

Files changed:
`README.md`, `config/nero.env`, `docs/status/bringup_checklist.md`,
`docs/status/current_bringup_status.md`, `docs/status/deployment_log.md`,
`docs/phases/s12_control_isolation_plan.md`,
`docs/phases/机器人部署与调试行动路线.md`,
`scripts/launch_s12_isolation_pair.sh`, `scripts/ros_s12_isolation_step.py`.

Verification:
Local checks passed:

- `bash -n scripts/*.sh`
- `python3 -m py_compile examples/nero_read_state.py examples/nero_sdk_single_joint_step.py scripts/ros_single_joint_step.py scripts/ros_s12_isolation_step.py`
- `git diff --check`

Route updates:
S12 now has explicit test commands, target signs, motion limits, and acceptance
thresholds.

Open risks:

- The `-Y` direction sign is inferred from URDF and S11 TF; if visual direction
  disagrees, stop and reverse the sign before the `30 deg` acceptance move.
- `30 deg` is larger than S10 first-motion steps, so cable slack and swept area
  must be checked again immediately before execution.

Next:
Run local checks, commit the S12 preparation, then execute S12.1 Arm A dry-run
and, after operator confirmation, execution.

## 2026-06-26 - S12.1 Dry-Run Script Attribute Fix

Phase: S12 控制隔离与日志闭环

Goal:
Diagnose and fix the S12.1 Arm A dry-run failure before any motion command.

Action:
Operator ran the S12 dry-run command for Arm A `joint1 +30 deg`. The script
failed during node initialization with:

```text
AttributeError: can't set attribute 'publishers'
```

No motion command was published because the failure occurred before the target
publisher was created and before dry-run output was printed.

Commands / evidence:

```bash
NERO_CONTAINER_NAME=nero-humble-s12-tool \
  bash scripts/run_humble_container.sh \
    python3 /workspace/nero/scripts/ros_s12_isolation_step.py \
      --target arm_a \
      --joint joint1 \
      --delta-deg 30
```

Result:
The root cause is a script naming conflict: `rclpy.node.Node` already exposes a
read-only `publishers` property, so assigning `self.publishers = {}` is invalid.

Deployment choices:

- Rename the script's target command publisher map to
  `self.command_publishers`.
- Keep the S12 procedure unchanged; rerun dry-run after local checks pass.

Files changed:
`docs/status/deployment_log.md`, `scripts/ros_s12_isolation_step.py`.

Verification:
Local checks passed before commit `a992d67`:

- `bash -n scripts/*.sh`
- `python3 -m py_compile scripts/ros_s12_isolation_step.py`
- `git diff --check`

Route updates:
No phase-status change. S12.1 remains at dry-run gate.

Open risks:

- Resolved by the follow-up dry-run on 2026-06-26.

Next:
Run local checks, commit the fix, then rerun the S12.1 Arm A dry-run command.

## 2026-06-26 - S12.1 Arm A Dry-Run Accepted

Phase: S12 控制隔离与日志闭环

Goal:
Validate the Arm A `joint1 +30 deg` S12 dry-run target before any real motion.

Action:
Operator reran the S12 dry-run after the publisher-map script fix.

Commands / evidence:

```bash
NERO_CONTAINER_NAME=nero-humble-s12-tool \
  bash scripts/run_humble_container.sh \
    python3 /workspace/nero/scripts/ros_s12_isolation_step.py \
      --target arm_a \
      --joint joint1 \
      --delta-deg 30
```

Key output:

- `target=arm_a passive=arm_b execute=False`
- `joint=joint1 delta_deg=30.0`
- `target_current_deg=[1.109, 90.348, 92.988, 11.602, 7.709, 43.151, 50.516]`
- `target_goal_deg=[31.109, 90.348, 92.988, 11.602, 7.709, 43.151, 50.516]`
- `passive_current_deg=[-1.989, 89.862, -39.0, 5.704, 26.172, -10.311, 25.698]`
- Target status: `ctrl_mode=1`, `arm_status=0`, `mode_feedback=1`,
  `motion_status=1`, `err_status=0`.
- Passive status: `ctrl_mode=1`, `arm_status=6`, `mode_feedback=1`,
  `motion_status=1`, `err_status=0`.

Result:
S12.1 Arm A dry-run is accepted. The target vector changes only Arm A
`joint1` by `+30 deg`; Arm B is read-only passive feedback. No motion command
was published because `execute=False`.

Deployment choices:

- Keep the planned Arm A execution target as `joint1 +30 deg`.
- Keep passive-arm tolerance at `1.0 deg`.
- Execute only after the operator reconfirms the full J1 swept area, cable
  slack, and emergency-stop/power-cutoff assignment.

Files changed:
`docs/status/bringup_checklist.md`, `docs/status/current_bringup_status.md`,
`docs/status/deployment_log.md`, `docs/phases/机器人部署与调试行动路线.md`.

Verification:
Local checks passed:

- `bash -n scripts/*.sh`
- `python3 -m py_compile scripts/ros_s12_isolation_step.py`
- `git diff --check`

Route updates:
S12.1 advances from dry-run gate to execution gate.

Open risks:

- The inferred `lab_world -Y` direction is still unverified by actual motion.
  If the first observed motion direction is wrong, stop and reverse the sign
  before continuing.

Next:
Run local checks, commit the dry-run record, then execute Arm A S12.1 only if
the operator confirms the safety gate.

## 2026-06-26 - S12.1 Arm A Execution Core Passed

Phase: S12 控制隔离与日志闭环

Goal:
Execute Arm A `joint1 +30 deg` while monitoring Arm B as the passive arm, then
verify that the target arm moves and returns while the passive arm remains
still.

Action:
Operator executed the S12.1 Arm A control-isolation command after dry-run
acceptance and safety-gate confirmation.

Commands / evidence:

```bash
NERO_CONTAINER_NAME=nero-humble-s12-tool \
  bash scripts/run_humble_container.sh \
    python3 /workspace/nero/scripts/ros_s12_isolation_step.py \
      --execute \
      --target arm_a \
      --joint joint1 \
      --delta-deg 30
```

Key output:

- `target=arm_a passive=arm_b execute=True`.
- `target_current_deg=[1.109, 90.348, 92.986, 11.602, 7.709, 43.151, 50.516]`.
- `target_goal_deg=[31.109, 90.348, 92.986, 11.602, 7.709, 43.151, 50.516]`.
- `passive_current_deg=[-1.989, 89.862, -39.0, 5.704, 26.172, -10.311, 25.698]`.
- `after_step_target_deg=[30.490, 90.348, 92.986, 11.599, 7.707, 43.148, 50.516]`.
- `after_step_passive_deg=[-1.988, 89.862, -39.0, 5.704, 26.172, -10.311, 25.698]`.
- `max_passive_dev_deg=0.004`.
- `after_return_target_deg=[1.704, 90.349, 92.986, 11.606, 7.710, 43.15, 50.515]`.
- `after_return_passive_deg=[-1.989, 89.862, -39.0, 5.704, 26.172, -10.311, 25.698]`.
- `max_passive_dev_total_deg=0.005`.
- Final target status: `ctrl_mode=1`, `arm_status=0`, `mode_feedback=1`,
  `motion_status=0`, `err_status=0`.
- Final passive status: `ctrl_mode=1`, `arm_status=6`, `mode_feedback=1`,
  `motion_status=1`, `err_status=0`.
- Operator observation: motion direction matched expectation, and Arm B did not
  visibly move.

Result:
S12.1 Arm A execution core passes. Arm A reached and returned within the
`0.7 deg` tolerance, and Arm B passive deviation stayed far below the `1.0 deg`
tolerance.

Deployment choices:

- Treat Arm A `joint1 +30 deg` as the correct sign for the intended visible
  `lab_world -Y` sweep.
- Do not close S12.1 until a post-motion dual-arm read-only snapshot is
  captured and checked.

Files changed:
`config/nero.env`, `docs/status/bringup_checklist.md`,
`docs/status/current_bringup_status.md`, `docs/status/deployment_log.md`,
`docs/phases/s12_control_isolation_plan.md`, `docs/phases/机器人部署与调试行动路线.md`.

Verification:
Local checks passed:

- `bash -n scripts/*.sh`
- `python3 -m py_compile scripts/ros_s12_isolation_step.py`
- `git diff --check`

Route updates:
S12.1 advances from execution gate to post-motion snapshot gate.

Open risks:

- Post-motion read-only snapshot is not yet captured.
- S12.2 Arm B isolation has not started.

Next:
Stop the S12 driver pair, start the dual-arm read-only driver, capture a
post-motion snapshot, and evaluate it before closing S12.1.

## 2026-06-26 - S12.1 Arm A Post-Snapshot Accepted

Phase: S12 控制隔离与日志闭环

Goal:
Close S12.1 by validating the post-motion dual-arm read-only snapshot after Arm
A `joint1 +30 deg` isolation execution.

Action:
Operator stopped the S12 control driver pair, returned to the dual-arm
read-only driver, and captured a read-only snapshot.

Commands / evidence:

- Snapshot: `docs/evidence/ros_snapshots/20260626_080809/`.
- Snapshot README: `Failed capture commands: 0`.
- Arm A joint-state frequency: about `200 Hz`
  (`200.039`, `200.006`, `200.009`, `200.006`).
- Arm B joint-state frequency: about `200 Hz`
  (`200.036`, `200.027`, `200.014`, `200.008`).
- Arm A status: `ctrl_mode=1`, `arm_status=0`, `mode_feedback=1`,
  `motion_status=0`, `err_status=0`.
- Arm B status: `ctrl_mode=1`, `arm_status=6`, `mode_feedback=1`,
  `motion_status=1`, `err_status=0`.
- A/B joint-limit flags: all `false`.
- A/B joint-communication flags: all `false`.

Result:
S12.1 Arm A control-isolation test is accepted and closed. It now has dry-run
evidence, execution evidence, operator observation, quantitative passive-arm
monitoring, and a clean post-motion dual-arm read-only snapshot.

Deployment choices:

- Keep Arm A `joint1 +30 deg` as the accepted sign and amplitude for this
  visible S12 isolation motion.
- Proceed next to S12.2 Arm B `joint1 -30 deg` dry-run after stopping any
  unnecessary read-only/control terminals and confirming the workspace again.

Files changed:
`config/nero.env`, `docs/status/bringup_checklist.md`,
`docs/status/current_bringup_status.md`, `docs/status/deployment_log.md`,
`docs/phases/s12_control_isolation_plan.md`,
`docs/phases/机器人部署与调试行动路线.md`,
`docs/evidence/ros_snapshots/20260626_080809/`.

Verification:
Local checks passed:

- `bash -n scripts/*.sh`
- `python3 -m py_compile scripts/ros_s12_isolation_step.py`
- `git diff --check`

Route updates:
S12.1 is closed. S12.2 Arm B isolation is the next S12 gate.

Open risks:

- S12.2 Arm B isolation has not started.
- S12 as a whole is not complete until Arm B isolation and final logging
  closure pass.

Next:
Run local checks, commit the S12.1 closure, then start S12.2 Arm B dry-run.

## 2026-06-26 - S12.2 Arm B Dry-Run Accepted

Phase: S12 控制隔离与日志闭环

Goal:
Validate the Arm B `joint1 -30 deg` S12 dry-run target before any real motion.

Action:
Operator ran the S12.2 Arm B dry-run with Arm B as target and Arm A as passive
monitoring.

Commands / evidence:

```bash
NERO_CONTAINER_NAME=nero-humble-s12-tool \
  bash scripts/run_humble_container.sh \
    python3 /workspace/nero/scripts/ros_s12_isolation_step.py \
      --target arm_b \
      --joint joint1 \
      --delta-deg -30
```

Key output:

- `target=arm_b passive=arm_a execute=False`
- `joint=joint1 delta_deg=-30.0`
- `target_current_deg=[-1.988, 89.862, -39.0, 5.704, 26.172, -10.311, 25.698]`
- `target_goal_deg=[-31.988, 89.862, -39.0, 5.704, 26.172, -10.311, 25.698]`
- `passive_current_deg=[1.109, 90.347, 92.985, 11.602, 7.712, 43.151, 50.515]`
- Target status: `ctrl_mode=1`, `arm_status=0`, `mode_feedback=1`,
  `motion_status=1`, `err_status=0`.
- Passive status: `ctrl_mode=1`, `arm_status=0`, `mode_feedback=1`,
  `motion_status=0`, `err_status=0`.

Result:
S12.2 Arm B dry-run is accepted. The target vector changes only Arm B `joint1`
by `-30 deg`; Arm A is read-only passive feedback. No motion command was
published because `execute=False`.

Deployment choices:

- Keep the planned Arm B execution target as `joint1 -30 deg`.
- Keep passive-arm tolerance at `1.0 deg`.
- Execute only after the operator reconfirms the full Arm B J1 swept area,
  cable slack, and emergency-stop/power-cutoff assignment.

Files changed:
`config/nero.env`, `docs/status/bringup_checklist.md`,
`docs/status/current_bringup_status.md`, `docs/status/deployment_log.md`,
`docs/phases/s12_control_isolation_plan.md`, `docs/phases/机器人部署与调试行动路线.md`.

Verification:
Local checks passed:

- `bash -n scripts/*.sh`
- `python3 -m py_compile scripts/ros_s12_isolation_step.py`
- `git diff --check`

Route updates:
S12.2 advances from dry-run gate to execution gate.

Open risks:

- The inferred `lab_world -Y` direction for Arm B is still unverified by actual
  motion. If the observed direction is wrong, stop and reverse the sign before
  continuing.

Next:
Run local checks, commit the dry-run record, then execute Arm B S12.2 only if
the operator confirms the safety gate.

## 2026-06-26 - S12.2 Arm B Execution Core Passed

Phase: S12 控制隔离与日志闭环

Goal:
Execute Arm B `joint1 -30 deg` while monitoring Arm A as the passive arm, then
verify that the target arm moves and returns while the passive arm remains
still.

Action:
Operator executed the S12.2 Arm B control-isolation command after dry-run
acceptance and safety-gate confirmation.

Commands / evidence:

```bash
NERO_CONTAINER_NAME=nero-humble-s12-tool \
  bash scripts/run_humble_container.sh \
    python3 /workspace/nero/scripts/ros_s12_isolation_step.py \
      --execute \
      --target arm_b \
      --joint joint1 \
      --delta-deg -30
```

Key output:

- `target=arm_b passive=arm_a execute=True`.
- `target_current_deg=[-1.988, 89.862, -39.0, 5.704, 26.172, -10.311, 25.698]`.
- `target_goal_deg=[-31.988, 89.862, -39.0, 5.704, 26.172, -10.311, 25.698]`.
- `passive_current_deg=[1.109, 90.348, 92.986, 11.602, 7.709, 43.152, 50.518]`.
- `after_step_target_deg=[-31.398, 89.861, -39.0, 5.698, 26.172, -10.311, 25.698]`.
- `after_step_passive_deg=[1.110, 90.349, 92.986, 11.602, 7.709, 43.151, 50.515]`.
- `max_passive_dev_deg=0.007`.
- `after_return_target_deg=[-2.583, 89.861, -39.0, 5.704, 26.170, -10.310, 25.697]`.
- `after_return_passive_deg=[1.109, 90.347, 92.986, 11.602, 7.710, 43.151, 50.515]`.
- `max_passive_dev_total_deg=0.008`.
- Final target status: `ctrl_mode=1`, `arm_status=0`, `mode_feedback=1`,
  `motion_status=0`, `err_status=0`.
- Final passive status: `ctrl_mode=1`, `arm_status=0`, `mode_feedback=1`,
  `motion_status=0`, `err_status=0`.
- Operator observation: motion matched expectation, and Arm A did not visibly
  move.

Result:
S12.2 Arm B execution core passes. Arm B reached and returned within the
`0.7 deg` tolerance, and Arm A passive deviation stayed far below the `1.0 deg`
tolerance.

Deployment choices:

- Treat Arm B `joint1 -30 deg` as the correct sign for the intended visible
  sweep.
- Do not close S12.2 until a post-motion dual-arm read-only snapshot is
  captured and checked.

Files changed:
`config/nero.env`, `docs/status/bringup_checklist.md`,
`docs/status/current_bringup_status.md`, `docs/status/deployment_log.md`,
`docs/phases/s12_control_isolation_plan.md`, `docs/phases/机器人部署与调试行动路线.md`.

Verification:
Local checks passed:

- `bash -n scripts/*.sh`
- `python3 -m py_compile scripts/ros_s12_isolation_step.py`
- `git diff --check`

Route updates:
S12.2 advances from execution gate to post-motion snapshot gate.

Open risks:

- Post-motion read-only snapshot is not yet captured.
- S12 final closure is still pending.

Next:
Stop the S12 driver pair, start the dual-arm read-only driver, capture a
post-motion snapshot, and evaluate it before closing S12.2/S12.

## 2026-06-26 - S12 Control Isolation Closed

Phase: S12 控制隔离与日志闭环

Goal:
Close S12 by validating the post-motion dual-arm read-only snapshot after Arm B
`joint1 -30 deg` isolation execution, then summarize the accepted S12 evidence.

Action:
Operator stopped the S12 control driver pair, returned to the dual-arm
read-only driver, and captured the Arm B post-motion snapshot.

Commands / evidence:

- Snapshot: `docs/evidence/ros_snapshots/20260626_083210/`.
- Snapshot README: `Failed capture commands: 0`.
- Arm A joint-state frequency: about `200 Hz`
  (`200.016`, `199.993`, `200.006`, `200.002`).
- Arm B joint-state frequency: about `200 Hz`
  (`200.006`, `200.013`, `200.010`, `200.007`).
- Arm A status: `ctrl_mode=1`, `arm_status=0`, `mode_feedback=1`,
  `motion_status=0`, `err_status=0`.
- Arm B status: `ctrl_mode=1`, `arm_status=0`, `mode_feedback=1`,
  `motion_status=0`, `err_status=0`.
- A/B joint-limit flags: all `false`.
- A/B joint-communication flags: all `false`.

Result:
S12 is accepted and closed. Arm A and Arm B each passed visible `30 deg` J1
control-isolation tests, returned to the original joint angle within tolerance,
and kept the passive arm within tolerance.

Deployment choices:

- Accept the S12 logging evidence set as script terminal output recorded in
  deployment logs, read-only snapshots, configuration records, and git commits.
  No rosbag was recorded in S12.
- Do not treat S12 as authorization for Cartesian motion, MoveIt execution,
  dexterous-hand actuation, contact, handoff, or close-proximity bimanual
  manipulation.
- Move next to S13 low-risk dual-arm primitives.

Files changed:
`README.md`, `agent.md`, `config/nero.env`, `docs/status/bringup_checklist.md`,
`docs/status/current_bringup_status.md`, `docs/status/deployment_log.md`,
`docs/phases/s12_control_isolation_plan.md`,
`docs/phases/机器人部署与调试行动路线.md`,
`docs/evidence/ros_snapshots/20260626_083210/`.

Verification:
Local checks passed:

- `bash -n scripts/*.sh`
- `python3 -m py_compile scripts/ros_s12_isolation_step.py`
- `git diff --check`

Route updates:
S12 is closed. S13 is now the active next phase.

Open risks:

- S13 has not been planned or executed yet.
- Intentional emergency-stop testing remains deferred.
- No rosbag was recorded during S12; future motion phases should decide whether
  rosbag is required or whether structured script output plus snapshots are
  sufficient.

Next:
Run local checks, commit the S12 closure, then prepare the S13 low-risk
dual-arm primitive plan.

## 2026-06-26 - S13 Low-Risk Dual-Arm Primitive Plan Prepared

Phase: S13 低风险双臂协同原语

Goal:
Prepare the first low-risk dual-active joint-space primitive using the same
visible `30 deg` J1 motion amplitude requested by the operator.

Action:
Added an S13 plan and two helper scripts. The driver wrapper starts both arms
with active control gates. The step script performs a dry-run, monitors a hold
period with both drivers active, and can then execute simultaneous J1 targets
and return both arms to the start angles.

Commands / evidence:

- New plan: `docs/phases/s13_low_risk_dual_arm_primitives_plan.md`.
- New driver wrapper: `scripts/launch_s13_dual_active_pair.sh`.
- New test script: `scripts/ros_s13_dual_joint_step.py`.
- Planned first primitive:
  - Arm A `joint1 +30 deg`.
  - Arm B `joint1 -30 deg`.
  - `speed_percent=5`.
  - `hold_seconds=3`.

Result:
S13 is prepared but not executed.

Deployment choices:

- Reuse the S12-validated J1 signs and `30 deg` magnitude.
- Treat S13's first primitive as simultaneous joint-space control only, not
  manipulation.
- Require dry-run and hold acceptance before any `--execute`.
- Keep target tolerance at `0.7 deg`, hold/non-target tolerance at `1.0 deg`.

Files changed:
`README.md`, `agent.md`, `config/nero.env`, `docs/status/bringup_checklist.md`,
`docs/status/current_bringup_status.md`, `docs/status/deployment_log.md`,
`docs/phases/s13_low_risk_dual_arm_primitives_plan.md`,
`docs/phases/机器人部署与调试行动路线.md`,
`scripts/launch_s13_dual_active_pair.sh`, `scripts/ros_s13_dual_joint_step.py`.

Verification:
Local checks passed:

- `bash -n scripts/*.sh`
- `python3 -m py_compile scripts/ros_s12_isolation_step.py scripts/ros_s13_dual_joint_step.py`
- `git diff --check`

Route updates:
S13 now has explicit startup commands, dry-run/hold gates, execution command,
and stop conditions.

Open risks:

- S13 has not been dry-run yet.
- Simultaneous `30 deg` motion has higher combined swept-area risk than S12,
  so both arm swept areas and cables must be checked together before execution.

Next:
Run local checks, commit the S13 preparation, then start S13 dual-active driver
and dry-run/hold validation.

## 2026-06-26 - S13 Dry-Run And Hold Accepted

Phase: S13 低风险双臂协同原语

Goal:
Validate the first S13 dual-active dry-run and hold check before any
simultaneous dual-arm motion command.

Action:
Operator ran the S13 dual-arm joint-space step script without `--execute` while
the dual-active driver pair was running.

Commands / evidence:

```bash
NERO_CONTAINER_NAME=nero-humble-s13-tool \
  bash scripts/run_humble_container.sh \
    python3 /workspace/nero/scripts/ros_s13_dual_joint_step.py \
      --joint joint1 \
      --arm-a-delta-deg 30 \
      --arm-b-delta-deg -30
```

Key output:

- `execute=False`.
- Arm A current:
  `[1.111, 90.348, 92.985, 11.602, 7.707, 43.151, 50.516]`.
- Arm A target:
  `[31.111, 90.348, 92.985, 11.602, 7.707, 43.151, 50.516]`.
- Arm A status: `ctrl_mode=1`, `arm_status=0`, `mode_feedback=1`,
  `motion_status=0`, `err_status=0`.
- Arm B current:
  `[-1.988, 89.864, -39.005, 5.703, 26.172, -10.311, 25.697]`.
- Arm B target:
  `[-31.988, 89.864, -39.005, 5.703, 26.172, -10.311, 25.697]`.
- Arm B status: `ctrl_mode=1`, `arm_status=0`, `mode_feedback=1`,
  `motion_status=0`, `err_status=0`.
- `hold_max_dev_deg={'arm_a': 0.0, 'arm_b': 0.0}`.

Result:
S13 dry-run and hold gate is accepted. The target vectors change only each
arm's `joint1`, both active drivers held position for the dry-run hold period,
and no motion command was published.

Deployment choices:

- Keep the planned S13 execution command as Arm A `joint1 +30 deg` and Arm B
  `joint1 -30 deg`.
- Keep `speed_percent=5`.
- Execute only after the operator reconfirms both arms' simultaneous swept
  areas, cable slack, and emergency-stop/power-cutoff assignment.

Files changed:
`agent.md`, `config/nero.env`, `docs/status/bringup_checklist.md`,
`docs/status/current_bringup_status.md`, `docs/status/deployment_log.md`,
`docs/phases/s13_low_risk_dual_arm_primitives_plan.md`,
`docs/phases/机器人部署与调试行动路线.md`.

Verification:
Local checks passed:

- `bash -n scripts/*.sh`
- `python3 -m py_compile scripts/ros_s13_dual_joint_step.py`
- `git diff --check`

Route updates:
S13 advances from preparation to execution gate.

Open risks:

- Simultaneous S13 execution has not yet been attempted.
- Post-motion snapshot will still be required after execution.

Next:
Run local checks, commit the dry-run record, then execute S13 only if the
operator confirms the safety gate.

## 2026-06-26 - S13 First Execution Direction Semantics Failed

Phase: S13 低风险双臂协同原语

Goal:
Execute the first simultaneous low-risk dual-arm J1 primitive after dry-run and
hold acceptance, and verify both numeric feedback and operator-visible motion
semantics.

Action:
Operator ran the S13 dual-arm joint-space step script with `--execute`.

Command:

```bash
NERO_CONTAINER_NAME=nero-humble-s13-tool \
  bash scripts/run_humble_container.sh \
    python3 /workspace/nero/scripts/ros_s13_dual_joint_step.py \
      --execute \
      --joint joint1 \
      --arm-a-delta-deg 30 \
      --arm-b-delta-deg -30
```

Key output:

- Arm A target: `joint1 1.111 deg -> 31.111 deg`.
- Arm B target: `joint1 -1.988 deg -> -31.988 deg`.
- Hold before motion remained stable:
  `hold_max_dev_deg={'arm_a': 0.0, 'arm_b': 0.006000000000000263}`.
- After step: Arm A `joint1=30.513 deg`, Arm B `joint1=-31.441 deg`.
- After return: Arm A `joint1=1.753 deg`, Arm B `joint1=-2.660 deg`.
- `max_non_target_dev_total_deg={'arm_a': 0.01299999999999951, 'arm_b': 0.00800000000000141}`.
- Final Arm A status: `ctrl_mode=1`, `arm_status=0`, `mode_feedback=1`,
  `motion_status=0`, `err_status=0`.
- Final Arm B status: `ctrl_mode=1`, `arm_status=0`, `mode_feedback=1`,
  `motion_status=0`, `err_status=0`.

Operator observation:
Arm B did not rotate in the expected opposite visible direction. Both arms
appeared to rotate in the same visible direction.

Result:
The ROS/CAN joint-space control chain passed numerically: both commands were
accepted, both arms moved and returned, final statuses were healthy, and
non-target joint deviations stayed well inside tolerance. The intended
world-direction semantics failed, so this run does not close S13 and must not be
accepted as the intended dual-arm primitive.

Deployment choices:

- Treat local joint sign as different from lab-world visible direction.
- Do not infer future dual-arm primitive direction from isolated S12 signs
  without simultaneous operator-visible validation.
- Do not repeat Arm A `+30 deg` / Arm B `-30 deg` as an "opposite direction"
  primitive.
- Before any further simultaneous motion, capture a post-motion read-only
  snapshot.
- After the snapshot, run a corrected direction-sign dry-run. The likely next
  hypothesis is to keep Arm A `joint1 +30 deg` and change Arm B to
  `joint1 +30 deg`, but execution requires a fresh dry-run and safety gate.

Files changed:
`agent.md`, `config/nero.env`, `docs/status/bringup_checklist.md`,
`docs/status/current_bringup_status.md`, `docs/status/deployment_log.md`,
`docs/phases/s13_low_risk_dual_arm_primitives_plan.md`,
`docs/phases/机器人部署与调试行动路线.md`.

Verification:
Local checks passed:

- `bash -n scripts/*.sh`
- `python3 -m py_compile scripts/ros_s13_dual_joint_step.py`
- `git diff --check`

Route updates:
S13 remains active. The first execution is classified as numeric pass /
world-direction semantic fail. Post-motion snapshot and corrected sign dry-run
are now the next gates.

Open risks:

- The current `joint1` sign convention is calibrated for isolated arm motion
  but not yet accepted for simultaneous world-frame direction semantics.
- No Cartesian, MoveIt, manipulation, contact, handoff, or dexterous-hand
  motion is authorized.

## 2026-06-26 - S13 Post-Motion Snapshot Accepted After Direction Mismatch

Phase: S13 低风险双臂协同原语

Goal:
Validate hardware and ROS feedback health after the first S13 execution, which
was numerically healthy but failed the intended world-direction semantics.

Action:
Operator stopped the S13 active control context, returned to the dual-arm
read-only snapshot flow, and captured a post-motion snapshot.

Evidence:

- Snapshot directory: `docs/evidence/ros_snapshots/20260626_090214/`.
- `Failed capture commands: 0`.
- Arm A joint-state frequency: about `200 Hz`.
- Arm B joint-state frequency: about `200 Hz`.
- Arm A status: `ctrl_mode=1`, `arm_status=0`, `mode_feedback=1`,
  `motion_status=0`, `err_status=0`.
- Arm B status: `ctrl_mode=1`, `arm_status=0`, `mode_feedback=1`,
  `motion_status=0`, `err_status=0`.
- Arm A joint-limit flags: all `false`.
- Arm B joint-limit flags: all `false`.
- Arm A joint-communication flags: all `false`.
- Arm B joint-communication flags: all `false`.

Result:
The snapshot is accepted as clean post-motion health evidence. It confirms that
the failed direction semantics did not leave the arms or ROS feedback chain in
an error state. It does not accept Arm A `+30 deg` / Arm B `-30 deg` as the
intended S13 world-direction primitive.

Deployment choices:

- Keep S13 active but do not close it.
- Move the next gate from post-motion snapshot to corrected J1 direction-sign
  dry-run.
- Current dry-run hypothesis: Arm A `joint1 +30 deg`, Arm B `joint1 +30 deg`.
- Do not execute the corrected sign hypothesis until its dry-run and safety gate
  are accepted.

Files changed:
`agent.md`, `config/nero.env`, `docs/status/bringup_checklist.md`,
`docs/status/current_bringup_status.md`, `docs/status/deployment_log.md`,
`docs/phases/s13_low_risk_dual_arm_primitives_plan.md`,
`docs/evidence/ros_snapshots/20260626_090214/`,
`docs/phases/机器人部署与调试行动路线.md`.

Verification:
Local checks passed:

- `bash -n scripts/*.sh`
- `python3 -m py_compile scripts/ros_s13_dual_joint_step.py`
- `git diff --check`

Route updates:
S13 first execution now has clean post-motion health evidence. Direction-sign
correction remains open.

Open risks:

- The corrected sign hypothesis has not been dry-run.
- No additional motion should be executed until the corrected dry-run and safety
  gate are accepted.

## 2026-06-26 - S13 Corrected Direction-Sign Dry-Run Accepted

Phase: S13 低风险双臂协同原语

Goal:
Validate the corrected J1 sign hypothesis after the first S13 execution proved
that Arm A `+30 deg` / Arm B `-30 deg` did not match the intended
operator-visible direction semantics.

Action:
Operator ran the S13 dual-arm joint-space step script without `--execute`,
using Arm A `joint1 +30 deg` and Arm B `joint1 +30 deg`.

Command:

```bash
NERO_CONTAINER_NAME=nero-humble-s13-tool \
  bash scripts/run_humble_container.sh \
    python3 /workspace/nero/scripts/ros_s13_dual_joint_step.py \
      --joint joint1 \
      --arm-a-delta-deg 30 \
      --arm-b-delta-deg 30
```

Key output:

- `execute=False`.
- Arm A current:
  `[1.11, 90.348, 92.984, 11.604, 7.706, 43.15, 50.514]`.
- Arm A target:
  `[31.11, 90.348, 92.984, 11.604, 7.706, 43.15, 50.514]`.
- Arm A status: `ctrl_mode=1`, `arm_status=0`, `mode_feedback=1`,
  `motion_status=0`, `err_status=0`.
- Arm B current:
  `[-1.988, 89.863, -39.008, 5.703, 26.171, -10.31, 25.696]`.
- Arm B target:
  `[28.012, 89.863, -39.008, 5.703, 26.171, -10.31, 25.696]`.
- Arm B status: `ctrl_mode=1`, `arm_status=0`, `mode_feedback=1`,
  `motion_status=0`, `err_status=0`.
- `hold_max_dev_deg={'arm_a': 0.00799999999999823, 'arm_b': 0.005999999999997082}`.

Result:
Corrected direction-sign dry-run is accepted. The target vectors change only
each arm's `joint1`, both statuses are healthy, and hold drift is well below
the `1.0 deg` threshold.

Deployment choices:

- Keep corrected execution signs as Arm A `joint1 +30 deg`, Arm B
  `joint1 +30 deg`.
- Keep speed at the existing S13 active-driver value of `5%`.
- Execute only after the operator reconfirms simultaneous swept areas, cable
  slack, and emergency stop/power cutoff.

Files changed:
`agent.md`, `config/nero.env`, `docs/status/bringup_checklist.md`,
`docs/status/current_bringup_status.md`, `docs/status/deployment_log.md`,
`docs/phases/s13_low_risk_dual_arm_primitives_plan.md`,
`docs/phases/机器人部署与调试行动路线.md`.

Verification:
Local checks passed:

- `bash -n scripts/*.sh`
- `python3 -m py_compile scripts/ros_s13_dual_joint_step.py`
- `git diff --check`

Route updates:
S13 moves from corrected direction-sign dry-run gate to corrected execution
gate.

Open risks:

- Corrected execution has not been attempted.
- Operator-visible direction still must be confirmed during real motion.

## 2026-06-26 - S13 Corrected Direction-Sign Execution Accepted

Phase: S13 低风险双臂协同原语

Goal:
Execute the corrected simultaneous J1 primitive and verify that both numeric
feedback and operator-visible direction semantics match the intended S13
low-risk dual-arm primitive.

Action:
Operator ran the S13 dual-arm joint-space step script with `--execute`, using
Arm A `joint1 +30 deg` and Arm B `joint1 +30 deg`.

Command:

```bash
NERO_CONTAINER_NAME=nero-humble-s13-tool \
  bash scripts/run_humble_container.sh \
    python3 /workspace/nero/scripts/ros_s13_dual_joint_step.py \
      --execute \
      --joint joint1 \
      --arm-a-delta-deg 30 \
      --arm-b-delta-deg 30
```

Key output:

- Arm A current:
  `[1.112, 90.344, 92.984, 11.602, 7.705, 43.153, 50.514]`.
- Arm A target:
  `[31.112, 90.344, 92.984, 11.602, 7.705, 43.153, 50.514]`.
- Arm B current:
  `[-1.988, 89.862, -39.006, 5.703, 26.175, -10.306, 25.694]`.
- Arm B target:
  `[28.012, 89.862, -39.006, 5.703, 26.175, -10.306, 25.694]`.
- `hold_max_dev_deg={'arm_a': 0.00500000000000605, 'arm_b': 0.0}`.
- After step: Arm A `joint1=30.459 deg`, Arm B `joint1=27.318 deg`.
- After return: Arm A `joint1=1.737 deg`, Arm B `joint1=-1.394 deg`.
- `max_non_target_dev_total_deg={'arm_a': 0.006000000000000263, 'arm_b': 0.007000000000000837}`.
- Final Arm A status: `ctrl_mode=1`, `arm_status=0`, `mode_feedback=1`,
  `motion_status=0`, `err_status=0`.
- Final Arm B status: `ctrl_mode=1`, `arm_status=0`, `mode_feedback=1`,
  `motion_status=0`, `err_status=0`.

Operator observation:
The corrected simultaneous movement matched the expected visible direction.

Result:
Corrected S13 execution core is accepted. The original local-sign assumption
was wrong, but the corrected sign pair now satisfies both numeric and
operator-visible criteria. S13 is not closed until a corrected-execution
post-motion read-only snapshot is captured and accepted.

Deployment choices:

- Keep the accepted S13 J1 primitive signs as Arm A `joint1 +30 deg`, Arm B
  `joint1 +30 deg`.
- Treat the original Arm A `+30 deg` / Arm B `-30 deg` sign pair as a rejected
  world-direction primitive, despite numeric control success.
- Require post-motion read-only snapshot before closing S13.

Files changed:
`agent.md`, `config/nero.env`, `docs/status/bringup_checklist.md`,
`docs/status/current_bringup_status.md`, `docs/status/deployment_log.md`,
`docs/phases/s13_low_risk_dual_arm_primitives_plan.md`,
`docs/phases/机器人部署与调试行动路线.md`.

Verification:
Local checks passed:

- `bash -n scripts/*.sh`
- `python3 -m py_compile scripts/ros_s13_dual_joint_step.py`
- `git diff --check`

Route updates:
S13 moves from corrected execution gate to corrected-execution post-motion
snapshot gate.

Open risks:

- Corrected-execution post-motion snapshot is still pending.
- Do not expand to Cartesian, MoveIt, manipulation, contact, handoff, or
  dexterous-hand actuation before S13 closure.

## 2026-06-26 - S13 Final Snapshot Attempt Not Accepted

Phase: S13 低风险双臂协同原语

Goal:
Validate final post-motion ROS read-only health after the corrected S13
execution.

Action:
Operator captured a dual-arm read-only snapshot after the corrected execution.

Evidence:

- Snapshot directory: `docs/evidence/ros_snapshots/20260626_093414/`.
- `Failed capture commands: 0`.
- Arm A status: `ctrl_mode=1`, `arm_status=0`, `mode_feedback=1`,
  `motion_status=0`, `err_status=0`.
- Arm B status: `ctrl_mode=1`, `arm_status=0`, `mode_feedback=1`,
  `motion_status=0`, `err_status=0`.
- Arm A joint-limit flags: all `false`.
- Arm B joint-limit flags: all `false`.
- Arm A joint-communication flags: all `false`.
- Arm B joint-communication flags: all `false`.
- Arm A joint-state frequency: about `400 Hz`.
- Arm B joint-state frequency: about `400 Hz`.

Result:
The snapshot is not accepted for S13 closure. The robot state is healthy, but
the observed feedback rate is about double the established read-only baseline
of about `200 Hz`. This most likely means duplicate publishers, such as the S13
active driver still running while the read-only driver was launched.

Deployment choices:

- Do not close S13 on this snapshot.
- Keep the corrected execution core accepted.
- Stop extra ROS driver containers/terminals and rerun a clean final read-only
  snapshot.
- Treat about `200 Hz` single-source feedback as the expected final evidence.

Files changed:
`agent.md`, `config/nero.env`, `docs/status/bringup_checklist.md`,
`docs/status/current_bringup_status.md`, `docs/status/deployment_log.md`,
`docs/phases/s13_low_risk_dual_arm_primitives_plan.md`,
`docs/evidence/ros_snapshots/20260626_093414/`,
`docs/phases/机器人部署与调试行动路线.md`.

Verification:
Local checks passed:

- `bash -n scripts/*.sh`
- `python3 -m py_compile scripts/ros_s13_dual_joint_step.py`
- `git diff --check`

Route updates:
S13 remains open at the final snapshot gate.

Open risks:

- Running duplicate feedback publishers can hide whether the snapshot reflects a
  clean deployment topology.
- No next-phase motion should start until S13 has a clean final snapshot.

## 2026-06-29 - S13 Final Snapshot Accepted And Phase Closed

Phase: S13 低风险双臂协同原语

Goal:
Close S13 with clean final read-only evidence after the corrected dual-arm
execution and the previous duplicate-publisher frequency anomaly.

Action:
Operator cleaned up the extra ROS driver terminal/container state, checked
publisher counts, and reran the final read-only snapshot.

Publisher-count evidence:

- `/arm_a/feedback/joint_states`: `Publisher count: 1`.
- `/arm_b/feedback/joint_states`: `Publisher count: 1`.
- The single publisher in each namespace is `agx_arm_ctrl_single_node`.

Intermediate evidence:

- Snapshot directory: `docs/evidence/ros_snapshots/20260629_043358/`.
- `Failed capture commands: 0`.
- A/B `err_status: 0`, no joint-limit flags, no joint-communication flags.
- A/B joint-state frequency was still about `400 Hz`.
- Result: not accepted for closure; duplicate publishers were still indicated.

Accepted final evidence:

- Snapshot directory: `docs/evidence/ros_snapshots/20260629_043441/`.
- `Failed capture commands: 0`.
- Arm A joint-state frequency: about `200 Hz`.
- Arm B joint-state frequency: about `200 Hz`.
- Arm A status: `ctrl_mode=1`, `arm_status=6`, `mode_feedback=1`,
  `motion_status=1`, `err_status=0`.
- Arm B status: `ctrl_mode=1`, `arm_status=6`, `mode_feedback=1`,
  `motion_status=1`, `err_status=0`.
- Arm A joint-limit flags: all `false`.
- Arm B joint-limit flags: all `false`.
- Arm A joint-communication flags: all `false`.
- Arm B joint-communication flags: all `false`.

Result:
S13 is accepted and closed. The final clean snapshot explains the prior
`400 Hz` anomaly as duplicate publishers from an extra terminal/driver. The
accepted low-risk dual-arm primitive is Arm A `joint1 +30 deg` and Arm B
`joint1 +30 deg`. The original Arm A `+30 deg` / Arm B `-30 deg` sign pair
remains recorded as a rejected world-direction primitive.

Deployment choices:

- Move next to S14 end-effector pre-installation review.
- Do not mount, power, configure, or actuate the dexterous hand before S14.0
  records mechanical, electrical, CAN/ID, load/TCP, URDF/ROS, and no-motion
  read-only decisions.
- Do not expand to Cartesian, MoveIt execute, contact, handoff, or close
  proximity manipulation until later gates are accepted.

Files changed:
`agent.md`, `config/nero.env`, `docs/status/bringup_checklist.md`,
`docs/status/current_bringup_status.md`, `docs/status/deployment_log.md`,
`docs/phases/s13_low_risk_dual_arm_primitives_plan.md`,
`docs/evidence/ros_snapshots/20260629_043358/`,
`docs/evidence/ros_snapshots/20260629_043441/`,
`docs/phases/机器人部署与调试行动路线.md`.

Verification:
Local checks passed:

- `bash -n scripts/*.sh`
- `python3 -m py_compile scripts/ros_s13_dual_joint_step.py`
- `git diff --check`

Route updates:
S13 is closed. S14 is the next phase.

Open risks:

- S14 changes mass, TCP, cable routing, URDF, and possibly CAN endpoints; it
  must not inherit S13's bare-arm assumptions without revalidation.

## 2026-06-29 - S14 Dexterous Hands Mechanically Installed

Phase: S14 末端执行器接入

Goal:
Record the first field state after installing both dexterous hands and define
the next no-motion verification boundary.

Action:
Operator reported both dexterous hands have been mechanically installed.

Field facts:

- Both dexterous hands are installed mechanically.
- Current mapping follows the prior decision:
  - Arm A: right dexterous hand.
  - Arm B: left dexterous hand.
- Cable routing constrains J6/J7 wrist motion.
- Operator reports the cable does not interfere when bends stay below about
  `70 deg`; larger bends may affect the cable.

Interpretation:

- The `70 deg` value is a field cable-bend observation, not a calibrated joint
  angle limit.
- S13 bare-arm assumptions no longer fully apply because mass, TCP, collision
  envelope, cable routing, and model/driver parameters changed.
- No hand power/configuration/actuation is accepted yet.

Deployment choices:

- Created `docs/phases/s14_end_effector_preinstall_plan.md`.
- Treat S14.0/S14.1 as no-motion mechanical/cable/read-only verification.
- Do not command large J6/J7 wrist motion until a cable-safe envelope is
  documented.
- Do not use Web dexterous-hand controls, ROS `/control/hand`, SDK Revo2 control,
  Cartesian motion, MoveIt execute, contact, or handoff before the relevant S14
  gates are accepted.

Files changed:
`agent.md`, `config/nero.env`, `docs/status/bringup_checklist.md`,
`docs/status/current_bringup_status.md`, `docs/status/deployment_log.md`,
`docs/phases/s14_end_effector_preinstall_plan.md`,
`docs/phases/机器人部署与调试行动路线.md`.

Verification:
Local checks passed:

- `bash -n scripts/*.sh`
- `python3 -m py_compile scripts/ros_s13_dual_joint_step.py`
- `git diff --check`

Route updates:
S14 is active. The next gate is post-installation no-motion review.

Open risks:

- Left/right hand mapping still needs visual confirmation against the physical
  installation if not already checked after final tightening.
- Cable constraints near J6/J7 must be converted into a conservative motion
  boundary before wrist motion or manipulation.

## 2026-06-29 - S14 Mechanical And Cable Review Accepted

Phase: S14 末端执行器接入

Goal:
Accept the post-installation mechanical/cable review before any hand
configuration or actuation.

Action:
Operator archived cable photos, confirmed left/right hand mapping, and
confirmed both hands are mechanically stable.

Evidence:

- Natural cable state photo:
  `docs/evidence/pics/S14自然状态线束.jpeg`.
- Wrist-bend cable state photo:
  `docs/evidence/pics/S14手腕弯折状态线束.jpeg`.
- Hand mapping:
  - Arm A: right dexterous hand.
  - Arm B: left dexterous hand.
- Mechanical installation: stable by operator confirmation.
- Cable constraint: J6/J7 cable routing constrains large wrist bends; bends below
  about `70 deg` are reported as non-interfering.

Result:
S14.0 mechanical/cable review is accepted within the temporary cable boundary.
This does not authorize finger motion, Web hand controls, ROS `/control/hand`,
SDK Revo2 control, Cartesian motion, or large J6/J7 wrist motion.

Deployment choices:

- Keep the temporary wrist rule: no large J6/J7 motion beyond the observed about
  `70 deg` cable-bend envelope.
- Next gate is S14.1 no-motion ROS read-only verification.
- Keep Web/ROS hand configuration unchanged until S14.2 records the exact
  `effector_type`, left/right model, load, and TCP choices.

Files changed:
`agent.md`, `config/nero.env`, `docs/status/bringup_checklist.md`,
`docs/status/current_bringup_status.md`, `docs/status/deployment_log.md`,
`docs/evidence/pics/S14自然状态线束.jpeg`,
`docs/evidence/pics/S14手腕弯折状态线束.jpeg`,
`docs/phases/s14_end_effector_preinstall_plan.md`,
`docs/phases/机器人部署与调试行动路线.md`.

Verification:
Local checks passed:

- `bash -n scripts/*.sh`
- `python3 -m py_compile scripts/ros_s13_dual_joint_step.py`
- `git diff --check`

Route updates:
S14 advances from mechanical install reported to S14.1 no-motion ROS read-only
verification.

Open risks:

- J6/J7 cable-safe envelope is still qualitative and must not be treated as a
  calibrated joint limit.
- Hand status and hand motion have not been tested.

## 2026-06-29 - S14 Arm Read-Only Verification Accepted With Singularity Observation

Phase: S14 末端执行器接入

Goal:
Verify the arm feedback path remains healthy after dexterous-hand mechanical
installation, without configuring or actuating the hands.

Action:
Operator verified single publishers for A/B joint-state feedback and captured a
no-motion ROS read-only snapshot.

Publisher-count evidence:

- `/arm_a/feedback/joint_states`: `Publisher count: 1`.
- `/arm_b/feedback/joint_states`: `Publisher count: 1`.
- The single publisher in each namespace is `agx_arm_ctrl_single_node`.

Snapshot evidence:

- Snapshot directory: `docs/evidence/ros_snapshots/20260629_074337/`.
- `Failed capture commands: 0`.
- Arm A joint-state frequency: about `200 Hz`.
- Arm B joint-state frequency: about `200 Hz`.
- Arm A status: `ctrl_mode=1`, `arm_status=3`, `mode_feedback=1`,
  `motion_status=1`, `err_status=0`.
- Arm B status: `ctrl_mode=1`, `arm_status=3`, `mode_feedback=1`,
  `motion_status=1`, `err_status=0`.
- Arm A joint-limit flags: all `false`.
- Arm B joint-limit flags: all `false`.
- Arm A joint-communication flags: all `false`.
- Arm B joint-communication flags: all `false`.
- Topic list contains arm feedback/control topics only; no hand-status topic
  was expected because this snapshot used `effector_type:=none`.

Interpretation:

- S14.1 passes as no-motion arm-controller communication/read-only evidence.
- It does not prove the current posture is ready for motion.
- Upstream documentation maps `arm_status=3` to `奇异点` /
  `SINGULARITY_POINT` and `motion_status=1` to not reached target.

Deployment choices:

- Keep hand controls disabled.
- Do not use Web dexterous-hand UI yet.
- Do not publish ROS `/control/hand` or SDK Revo2 control yet.
- Move next to S14.2 model/parameter decision, then S14.3 Revo2 hand read-only.

Files changed:
`agent.md`, `config/nero.env`, `docs/status/bringup_checklist.md`,
`docs/status/current_bringup_status.md`, `docs/status/deployment_log.md`,
`docs/phases/s14_end_effector_preinstall_plan.md`,
`docs/evidence/ros_snapshots/20260629_074337/`,
`docs/phases/机器人部署与调试行动路线.md`.

Verification:
Local checks passed:

- `bash -n scripts/*.sh`
- `python3 -m py_compile scripts/ros_s13_dual_joint_step.py`
- `git diff --check`

Route updates:
S14 advances from S14.1 no-motion arm read-only to S14.2 model/parameter
decision.

Open risks:

- The current arm posture reports singularity status. Do not use it as a motion
  starting point without a separate posture plan.
- Hand status and hand motion have not been tested.

## 2026-06-29 - S14 Revo2 Read-Only Launch Path Corrected

Phase: S14 末端执行器接入

Goal:
Start Revo2 hand read-only verification without finger actuation.

Action:
Operator attempted to launch the usual dual-arm read-only driver with
host-side `NERO_EFFECTOR_TYPE=revo2` and then checked ROS topics.

Evidence:

- Driver startup succeeded for both arms.
- Both driver logs printed `effector_type: none`.
- `ros2 topic list` showed arm feedback/control topics only.
- `ros2 topic list | grep hand` returned no topics.

Interpretation:
The missing hand topics are explained by the actual launch parameter:
`effector_type` remained `none`. This is an environment/config propagation
issue, not evidence that the Revo2 hardware feedback path failed. The host-side
temporary `NERO_EFFECTOR_TYPE=revo2` assignment was not passed into the Docker
container, and the container-side script sourced `config/nero.env`, whose global
default remains `NERO_EFFECTOR_TYPE="none"`.

Deployment choices:

- Keep the global `NERO_EFFECTOR_TYPE="none"` default for arm-only regression.
- Add `scripts/launch_s14_dual_revo2_readonly.sh` for S14.3 hand read-only.
- The S14.3 retry must confirm `effector_type: revo2` in both A/B driver logs
  before checking `/arm_a/feedback/hand_status` and
  `/arm_b/feedback/hand_status`.
- Continue to prohibit Web hand controls, ROS `/control/hand`,
  `/control/hand_position_time`, SDK Revo2 motion, wrist motion, Cartesian
  motion, and manipulation until later S14 gates are accepted.

Files changed:
`agent.md`, `config/nero.env`, `docs/status/bringup_checklist.md`,
`docs/status/current_bringup_status.md`, `docs/status/deployment_log.md`,
`docs/phases/s14_end_effector_preinstall_plan.md`,
`docs/phases/机器人部署与调试行动路线.md`,
`scripts/launch_s14_dual_revo2_readonly.sh`.

Verification:
Local checks passed:

- `bash -n scripts/*.sh`
- `python3 -m py_compile scripts/ros_s13_dual_joint_step.py`
- `git diff --check`

Live hardware verification is still pending: execute the corrected S14.3
read-only launch from the real desktop terminal.

Route updates:
S14.2 is recorded. S14.3 is not accepted yet; the corrected Revo2 read-only
retry is the next gate.

## 2026-06-29 - S14 Revo2 Endpoints Present But Status Message Pending

Phase: S14 末端执行器接入

Goal:
Verify whether the corrected Revo2 read-only launch produces actual hand-status
messages without sending finger commands.

Action:
Operator launched the corrected S14 Revo2 read-only driver and checked ROS
topics.

Evidence:

- `ros2 topic list` shows:
  - `/arm_a/feedback/hand_status`
  - `/arm_a/control/hand`
  - `/arm_a/control/hand_position_time`
  - `/arm_b/feedback/hand_status`
  - `/arm_b/control/hand`
  - `/arm_b/control/hand_position_time`
- Raw `ros2 topic echo --once /arm_a/feedback/hand_status` waited without
  output.

Interpretation:

- The ROS graph is now in the Revo2 software path.
- A `feedback/hand_status` topic existing in the ROS graph is not yet proof
  that physical hand feedback is being received.
- Upstream `agx_arm_ctrl_single_node.py` publishes `feedback/hand_status` only
  when `self.hand.get_status()` returns a non-`None` result.
- Upstream pyAgxArm virtual CAN tests model Revo2 feedback as a reply after
  host `0x1Bx` command frames, not as a proven periodic no-command feedback
  stream.

Deployment choices:

- Add `scripts/s14_revo2_hand_status_probe.sh` to bound the read-only
  `hand_status` wait and print explicit results.
- Continue to prohibit `/control/hand`, `/control/hand_position_time`, SDK
  Revo2 control, Web hand controls, and finger motion until a separate S14.4
  motion/safety gate.

Verification:
Pending live checks:

- Confirm A/B `feedback/hand_status` publisher count with the probe script.
- Run bounded A/B hand-status waits.
- If no messages arrive, perform passive CAN observation for Revo2 feedback IDs
  before deciding whether a no-motion status stream is expected.

## 2026-06-29 - S14 LinkerHand SDK Review Reorients Hand Path

Phase: S14 末端执行器接入

Goal:
Review the hand SDK that was previously used to debug these two installed
hands, and decide how it changes the S14 route.

Action:
Operator downloaded `https://github.com/LV-Robotics-Lab/linkerhand_sdk` into
the NERO workspace. The source tree was moved to `upstream/linkerhand_sdk/` so
it remains an ignored upstream evidence cache. The source was reviewed locally.

Evidence:

- Local source path: `upstream/linkerhand_sdk/`.
- The local copy is a downloaded tree and has no `.git` commit hash.
- README states this working copy is configured for a dual Linker Hand L6 setup.
- README hardware table:
  - left: SocketCAN `can0`, serial `LHL6-03-253-L-B-1-C`, firmware `2.3.7`;
  - right: SocketCAN `can1`, serial `LHL6-03-240-R-B-1-C`, firmware `2.3.7`.
- `LinkerHand/config/setting.yaml` configures both hands as `L6`, with left
  CAN `can0`, right CAN `can1`, SDK version `3.1.0`.
- `linker_hand_l6.py` provides high-level single-hand and bimanual control,
  status APIs, and side-specific presets.
- `LinkerHand/core/can/linker_hand_l6_can.py` shows LinkerHand L6 CAN IDs:
  - left hand `0x28`;
  - right hand `0x27`;
  - status/function bytes include `0x01` state, `0x33` temperature,
    `0x35` fault, `0x36` current, `0xC0` serial, and `0x64`/`0xC2` version.

Interpretation:

- The installed hands should now be treated as LinkerHand L6 devices unless
  later evidence proves otherwise.
- AgileX Revo2 ROS `feedback/hand_status` is not the preferred evidence path for
  these hands.
- The earlier Revo2 endpoint-without-message result is consistent with a
  protocol/device mismatch.

Deployment choices:

- Add `docs/upstream/s14_linkerhand_sdk_review.md`.
- Change the next gate to `S14.3L LinkerHand read-only identification`.
- Do not publish to AgileX ROS `/control/hand` or
  `/control/hand_position_time`.
- Do not run LinkerHand motion scripts (`test_hand.py`, `gestures.py`,
  `diagnose.py`, `dual_gui.py`) before a separate S14.4 motion gate.
- Do not run `find_linker_hand.sh` blindly while arm CAN interfaces are present,
  because it scans all CAN interfaces and sends `0FF#C0`.

Route updates:
Next live work should identify the actual hand CAN interfaces and read
LinkerHand serial/version/state/current/temperature/fault without finger motion.

## 2026-06-29 - S14 LinkerHand Cable Connected And Targeted Identify Tool Added

Phase: S14 末端执行器接入

Goal:
Prepare a safe next step after the operator connected the available hand-side
cable.

Action:
Added a targeted LinkerHand CAN identification script that only sends
LinkerHand identify/read request frames to an explicitly selected CAN interface.

Files:

- `scripts/s14_linkerhand_identify_can.sh`

Safety behavior:

- The script sends `0FF#C0` and fallback `0FF#01` only to the selected
  interface.
- It refuses to run on configured arm CAN interfaces `can_arm_a` and
  `can_arm_b` unless `--allow-arm-can` is explicitly provided.
- It does not send LinkerHand pose, speed, torque, or finger-motion commands.

Next live work:

1. Stop any ROS/Revo2 hand-test driver terminals.
2. List current CAN interfaces and identify the newly connected hand-side CAN
   interface.
3. Activate that candidate interface at `1000000` bitrate if needed.
4. Run the targeted LinkerHand identification script on the candidate interface.

## 2026-06-30 - S14 J6 Integrated Hand Path Correction

Phase: S14 末端执行器接入

Goal:
Correct the hand communication assumption after the operator clarified the
physical connection.

Action:
Operator clarified that the hands are not directly connected to the computer by
USB-CAN/PCAN adapters. The available hand-side cable is connected from the hand
to the NERO arm J6 end-effector port. Operator then provided passive `can_arm_a`
evidence and Web behavior.

Manual evidence:

- User manual section `2.1.2` says the J6 end connector provides 24 V, 2 A max
  and CAN for supported end-effectors.
- User manual section `2.3.2` says after installing the dexterous hand, connect
  the accessory power/communication cable between the J6 end connector and the
  hand.
- User manual section `6.3` documents a Web dexterous-hand control page with 6
  independent degrees of freedom.

Live evidence:

- `ip -br link show type can`:
  - `can_arm_a` UP;
  - `can_arm_b` UP.
- Passive `candump -tz can_arm_a` sample shows NERO arm feedback frames:
  - `0x2A1`, `0x2A2`, `0x2A3`, `0x2A4`;
  - `0x261` through `0x267`.
- No direct LinkerHand bench-test IDs such as `0x27`, `0x28`, `0x2F`, or
  `0x30` were present in the sample.
- Operator reports Web can enable/control the arm, but cannot enable/control
  the hand.

Interpretation:

- The previous direct LinkerHand CAN assumption is not valid for the current
  robot installation.
- The external arm CAN link is healthy, but the sample does not show direct
  LinkerHand frames.
- J6 hand communication may be internal to the arm controller and not forwarded
  to the external CAN bus.
- Web hand enable failure now points first to Web end-effector configuration,
  J6/hand cable seating, J6 end-effector power/communication, hand compatibility,
  or hand-side fault.

Deployment choices:

- Do not run `scripts/s14_linkerhand_identify_can.sh` on `can_arm_a` or
  `can_arm_b` in the current J6-integrated setup.
- Keep LinkerHand SDK as protocol evidence and previous bench-debug evidence,
  not the immediate live control path.
- Next gate is `S14.3J`: Web end-effector configuration and J6 hand enable-only
  diagnosis.

## 2026-06-30 - S14 Web Hand Configuration Present But No Motion

Phase: S14 末端执行器接入

Goal:
Record Web evidence after the operator reported that hand enable does not error,
but finger commands do not move the hand.

Evidence:

- Screenshots:
  - `docs/evidence/pics/灵巧手01.png`
  - `docs/evidence/pics/灵巧手02.png`
- Web hand page shows:
  - hand type `普通灵巧手`;
  - vendor/model `revo2`;
  - mode `位置控制`;
  - enable toggle active;
  - finger sliders and `发送` button available.
- Web status panel shows:
  - control mode `WEB`;
  - end effector `强脑灵巧手`.
- Web system setting drawer shows:
  - `末端执行器配置` selected as `强脑灵巧手`;
  - `当前配置` marker.
- Operator reports enable has no error, but the hand does not move when
  controlled.

Interpretation:

- The hand is no longer blocked by Web end-effector type being left at
  `默认（无加载）`.
- The next likely blockers are:
  - Web send/apply command not actually being issued;
  - J6 end-effector power/communication problem;
  - internal controller-to-hand bridge problem;
  - hand-side fault or incompatibility.

Next live diagnostic:

Run a small single-finger Web send while passively logging `can_arm_a`, and
capture Web `日志` around the same action. Do not use LinkerHand direct-CAN
scripts or ROS `/control/hand`.

## 2026-06-30 - S14 Web Hand Send Has No Motion And No Revo2 Frames In Sample

Phase: S14 末端执行器接入

Goal:
Interpret the first Web small single-finger send capture after Web hand
configuration was confirmed.

Evidence:

- Operator reports:
  - Web did not show an error;
  - the dexterous hand still did not move.
- The provided `can_arm_a` passive sample includes normal NERO external CAN
  feedback/control-state frames, including:
  - `0x2A1`, `0x2A2`, `0x2A3`, `0x2A4`;
  - `0x251` through `0x257`;
  - `0x261` through `0x267`;
  - `0x2A5`, `0x2A6`, `0x2A7`, `0x2A8`, `0x2A9`.
- Existing local protocol notes identify:
  - `0x251-0x257` as joint high-speed feedback;
  - `0x2A8` as gripper feedback;
  - `0x2A9` as J7 angle feedback.
- Upstream Revo2 code identifies:
  - command frames: `0x1B1`, `0x1B2`, `0x1B3`, `0x1B5`;
  - feedback frames: `0x1C0`, `0x1C1`, `0x1C2`, `0x1C3`.
- The provided sample did not show Revo2 command or feedback IDs.

Interpretation:

- Web end-effector configuration remains plausible, but the live send did not
  produce a visible hand response.
- The provided external CAN sample does not show Revo2 hand-frame evidence.
- Because NERO's J6 accessory bus may be bridged internally, absence of these
  frames on `can_arm_a` alone is not a final hardware-failure proof.
- The next diagnostic should distinguish between:
  - Web/controller not issuing Revo2 commands;
  - J6 accessory power/communication wiring problem;
  - internal bridge not reaching the hand;
  - hand-side compatibility or fault.

Next live diagnostic:

Run a filtered passive capture during one Web small single-finger send:

```bash
timeout 20s candump -tz can_arm_a,1B0:7F0,1C0:7F0
```

If no frames are printed and the hand still does not move, stop Web hand motion
attempts and re-check J6/hand cable seating and accessory power/communication
before escalating to vendor/device-side support.

## 2026-06-30 - Linker Drive Document Set Review

Phase: S14 末端执行器接入

Goal:
Download and review the newer Linker/LinkerHand documents supplied through the
Drive folder, then correct the S14 hand bring-up route if the new evidence
changes the control-path assumptions.

Actions:

- Downloaded all eight files from the supplied Google Drive folder. The local
  artifact cache has been moved to
  `../data-collection/docs/vendor/linker_drive_20260630/raw/`.
- Validated the raw PDFs/zips and recorded SHA256 values in
  `../data-collection/docs/reviews/linker_drive_20260630_review.md`.
- Extracted the three vendor zip archives for offline review.
- Generated text from all PDFs with `pdftotext -layout`.
- Reviewed the L6 product manual, LinkerHand Python SDK, LBOT Python/C SDK,
  Web platform documentation, and control-interface documentation.

Key findings:

- The installed hands should continue to be treated as LinkerHand L6 devices.
- L6 product facts: CAN/RS485, `24 V`, max current `1.4 A`, direct command
  values `0..255`.
- The newer LinkerHand Python SDK confirms direct-CAN right hand ID `0x27` and
  left hand ID `0x28`, but the current robot installation is through NERO J6,
  not a direct hand PCAN/USB-CAN bench setup.
- `api_lk73_v1.0.4` describes a separate Linker/LBOT controller stack with
  default controller IP `192.168.10.21` and Web platform
  `http://192.168.10.21:8000`.
- The LBOT SDK exposes L6 APIs through `LbotRobot("192.168.10.21")`, including
  `l6_set_position`, `l6_set_velocity`, and `l6_set_effort`.
- Vendor demos are unsafe for S14 because they include hand motion, arm motion,
  zero setting, enable/disable, e-stop, and joint-limit modification examples.

Deployment choice:

- Do not continue with Revo2-only assumptions as the first next step.
- New next gate is `S14.3K Linker/LBOT read-only controller probe`:
  `ping -c 2 192.168.10.21` and
  `curl -I --max-time 3 http://192.168.10.21:8000`.
- If reachable, write a custom read-only `LbotRobot` probe for API version,
  controller info, and current state only.
- If unreachable, ask the vendor whether this NERO J6 installation supports
  LinkerHand L6 directly, or whether a Linker/LBOT controller or firmware option
  is required.

Artifacts:

- Review: `../data-collection/docs/reviews/linker_drive_20260630_review.md`.
- Updated: `docs/phases/s14_end_effector_preinstall_plan.md`.
- Updated: `docs/status/current_bringup_status.md`.
- Updated: `docs/status/bringup_checklist.md`.
- Updated: `docs/phases/机器人部署与调试行动路线.md`.

## 2026-06-30 - S14 Hand Connection Kit Photo Analysis

Phase: S14 末端执行器接入

Goal:
Determine whether the newly photographed hand connection equipment is the
Linker/LBOT `192.168.10.21` controller or a direct hand debug kit.

Evidence:

- Network probe:
  - `ip -br addr` showed no host address in `192.168.10.x/24`.
  - `ping -c 2 192.168.10.21` had 100% packet loss.
  - `curl -I --max-time 3 http://192.168.10.21:8000` timed out.
- Photos:
  - `docs/evidence/pics/灵巧手连接设备/灵巧手连接设备01.jpeg`
  - `docs/evidence/pics/灵巧手连接设备/灵巧手连接设备02.jpeg`
  - `docs/evidence/pics/灵巧手连接设备/灵巧手连接设备03.jpeg`
- Visible hardware:
  - WANPTEK bench DC power supply;
  - two blue USB-CAN adapters;
  - screw-terminal labels `120R`, `GND`, `CANL`, `CANH`;
  - yellow/green CAN wires and red/black power leads;
  - no Ethernet/RJ45 port or IP controller.

Interpretation:

- The photographed kit is a direct LinkerHand bench-test/debug setup, not the
  Linker/LBOT network controller described by `api_lk73_v1.0.4`.
- This explains why `192.168.10.21` is not reachable in the current network
  state.
- The kit can be used later to bench-test one hand directly, but doing so is a
  different wiring topology from the current NERO J6 installation.

Deployment choice:

- Do not reconnect the installed hands immediately.
- Keep the current NERO J6 installation unless a deliberate bench-test branch is
  accepted.
- Before any bench test, disconnect the selected hand from NERO J6, test one
  hand at a time, verify the L6 manual XT30(2+2) polarity and CAN_H/CAN_L,
  set bench supply to the manual-confirmed 24 V range with conservative current
  limiting, bring up one USB-CAN adapter at 1 Mbps, and run only read-only
  identity/status checks before any motion command.

## 2026-06-30 - S14 Bench Kit Exposed Wire Risk

Phase: S14 末端执行器接入

Goal:
Record the operator-observed exposed/disconnected wire in
`灵巧手连接设备03.jpeg` and define the minimum handling requirements before this
kit can be used.

Observation:

- A red/orange conductor with exposed stranded/shield-like metal is visible near
  the bench DC power supply and loose harness.
- The photo does not identify whether it is V+, GND, shield/drain, or an unused
  wire.

Decision:

- Treat the exposed conductor as unsafe until proven otherwise.
- Do not energize the bench supply, connect a hand, or connect the USB-CAN
  adapter to a powered hand while this conductor remains bare or unidentified.

Required before bench-test use:

1. Power supply unplugged and output disabled.
2. Use a multimeter continuity test to identify V+, GND, CAN_H, CAN_L, and any
   shield/drain conductor.
3. Verify the mapping against the L6 manual XT30(2+2) pinout.
4. Confirm no short between V+/GND, CAN_H/CAN_L, CAN to V+, or CAN to GND.
5. Properly terminate functional conductors with ferrules/crimps/connectors; no
   loose strands in screw terminals.
6. Individually insulate unused or shield/drain conductors if not intentionally
   terminated.
7. Verify 24 V polarity at the hand-side connector with the hand disconnected.
8. Only then proceed to one-hand read-only identity/status checks.

## 2026-07-02 - S15 RViz Raw Joint-State Visual Mismatch Diagnosed

Phase: S15 双臂双手协调脚本

Goal:
Diagnose why RViz showed both arms horizontal while the real arms were hanging
vertically during S15 observation.

Evidence:

- Operator ran `scripts/s15_rviz_pose_diagnostics.sh`.
- `/arm_a/feedback/joint_states` and `/arm_b/feedback/joint_states` each had
  one publisher and one `robot_state_publisher` subscriber.
- Accepted S11 static TF values were active:
  - `lab_world -> arm_a/world`: `0,0,0,0,-1.5707963,0`
  - `lab_world -> arm_b/world`: `0.260,0,0,3.1415926,-1.5707963,0`
- Live `link7` TFs were horizontal in `lab_world`:
  - Arm A approximately `x=-0.713 m`, `z=0.007 m`
  - Arm B approximately `x=0.977 m`, `z=-0.018 m`

Interpretation:

- This is not a missing feedback topic, not a missing
  `robot_state_publisher` subscription, and not a missing S11 root transform.
- The current raw arm joint feedback no longer matches the visual convention
  used by the accepted S11 RViz posture.

Action:

- Added `scripts/ros_s15_joint_state_visual_anchor.py`.
- Updated `scripts/launch_s11_dual_model_view.sh` so RViz/RSP joint-state topics
  are configurable.
- Updated `scripts/launch_s15_dual_arm_hand_observe.sh` so S15 observation
  defaults to RViz-only anchored topics:
  - `/arm_a/visual/joint_states`
  - `/arm_b/visual/joint_states`
- Updated `scripts/s15_rviz_pose_diagnostics.sh` and S15 documentation.

Deployment choice:

- Keep raw `/arm_*/feedback/joint_states` as the only source for control and
  logging.
- Use `/arm_*/visual/joint_states` only for RViz observation in this S15
  bring-up branch.
- Do not use visual-anchor topics for control, MoveIt planning, joint limits, or
  calibration.

Next:

Relaunch S15 observation in default anchored RViz mode and verify that the
models match the real hanging posture before running any S15 dry-run or motion
execute gate.

## 2026-07-02 - S15 Anchored RViz Revalidation Accepted

Phase: S15 双臂双手协调脚本

Goal:
Revalidate RViz after adding the S15 visual-only joint-state anchor.

Evidence:

- Operator relaunched the S15 observation path with anchored RViz.
- Operator report:
  - robot positions are correct;
  - visual following is correct.

Result:

S15 RViz visual revalidation is accepted for the current session.

Deployment choices:

- Continue treating `/arm_a/visual/joint_states` and
  `/arm_b/visual/joint_states` as RViz-only observation topics.
- Raw `/arm_a/feedback/joint_states` and `/arm_b/feedback/joint_states` remain
  the authoritative feedback topics for control, logs, and safety checks.

Route update:

The next gate is S15 `--side left` dry-run with the observation session still in
read-only mode. Do not execute motion until the dry-run plan is reviewed.

## 2026-07-02 - S15 Left Dry-Run Node Attribute Bug Fixed

Phase: S15 双臂双手协调脚本

Goal:
Handle the first S15 left-side dry-run failure.

Evidence:

- Command:
  `NERO_CONTAINER_NAME=nero-humble-s15-left-dryrun bash scripts/run_humble_container.sh python3 /workspace/nero/scripts/ros_s15_arm_hand_sequence.py --side left`
- Error:
  `AttributeError: can't set attribute 'publishers'`

Cause:

`rclpy.node.Node` already has a read-only `publishers` property. The S15 script
attempted to assign `self.publishers = {}` during node initialization.

Action:

- Renamed the script's internal motion-publisher dictionary to
  `self._move_publishers`.
- Renamed the emergency-stop client dictionary to `self._estop_clients` for
  consistency.

Safety assessment:

No arm or hand command was sent. The failure happened before the script entered
the dry-run planning output stage.

Verification:

- `python3 -m py_compile scripts/ros_s15_arm_hand_sequence.py`
- `git diff --check`

Next:

Retry the same `--side left` dry-run command. Do not add `--execute`.

## 2026-07-02 - S15 Left-Side Dry-Run Accepted

Phase: S15 双臂双手协调脚本

Goal:
Review the S15 left-side dry-run before any real motion.

Command:

```bash
NERO_CONTAINER_NAME=nero-humble-s15-left-dryrun \
  bash scripts/run_humble_container.sh \
    python3 /workspace/nero/scripts/ros_s15_arm_hand_sequence.py \
      --side left
```

Result:

- `execute=False`
- `side_mapping=left->arm_b/can1 right->arm_a/can2`
- active side: `left`
- active arm: `arm_b`
- passive arm: `arm_a`
- requested target: `joint1=30 deg`, `joint2=90 deg`, `joint3=30 deg`
- waypoint count: `9`
- max planned joint delta: `89.868 deg`
- wide motion required: `true`
- hand open pose: `[255, 179, 255, 255, 255, 255]`
- hand close pose: `[67, 151, 0, 0, 0, 0]`

Assessment:

The software dry-run gate passed. This is a wide-motion and full-fist plan, so
execution still requires explicit operator clearance and script confirmations.

Next:

Before left-side execute, confirm Arm B sweep clearance, left-hand closing
clearance, RViz visibility, and J6/J7 cable slack. If any item is not clear,
reduce the target or hand close fraction and rerun dry-run.

## 2026-07-02 - S15 Left Execute Timed Out Before Motion

Phase: S15 双臂双手协调脚本

Goal:
Analyze the first S15 left-side execute attempt.

Command:

```bash
NERO_CONTAINER_NAME=nero-humble-s15-left-execute \
  bash scripts/run_humble_container.sh \
    python3 /workspace/nero/scripts/ros_s15_arm_hand_sequence.py \
      --side left \
      --execute \
      --allow-wide-motion \
      --allow-full-fist \
      --confirm-clearance \
      --confirm-rviz-visible
```

Result:

- The script entered execute mode and published Arm B waypoint `1/9`.
- Arm B feedback did not move from the starting values before timeout:
  - `joint1 last=0.82 target=4.07`
  - `joint2 last=0.13 target=10.12`
  - `joint3 last=101.70 target=93.74`
- The script called A/B emergency stop after timeout.
- The hand sequence was not reached.

Interpretation:

The command did not produce observable motion at all. This points first to
active-driver command reception or driver state, not to mid-trajectory tracking.

Action:

- Added execute preflight checking for active-arm `/control/move_j` subscription
  counts in `scripts/ros_s15_arm_hand_sequence.py`.
- Added `scripts/s15_motion_block_diagnostics.sh` to inspect command-topic
  subscriptions, feedback topics, arm status, and current joint feedback.

Next:

Do not retry execute immediately. Stop/restart the S15 active observation
terminal after the emergency stop, then run the diagnostics script and confirm
the active driver subscribes to `/arm_b/control/move_j`.

## 2026-07-02 - S15 Motion-Block Diagnostics Shows Topic Graph Healthy

Phase: S15 双臂双手协调脚本

Goal:
Review the first motion-block diagnostics output after the S15 left execute
timeout.

Result:

- ROS nodes include both arm drivers, both robot-state publishers, RViz, static
  TF publishers, and the S15 joint-state visual anchor.
- `/arm_a/control/move_j` and `/arm_b/control/move_j` each have one subscriber
  from the corresponding `agx_arm_ctrl_single_node`.
- `/arm_a/feedback/joint_states` and `/arm_b/feedback/joint_states` each have
  one publisher from the corresponding arm driver.
- Arm A and Arm B statuses are normal:
  - `ctrl_mode=1`
  - `arm_status=0`
  - `mode_feedback=1`
  - `motion_status=0`
  - `err_status=0`
  - no joint-limit flags
  - no joint communication flags

Interpretation:

The ROS command topic subscription exists, so a missing subscriber is not the
current blocker. However, read-only arm drivers also create `/control/move_j`
subscribers while being launched with `control_enabled=false`. Topic topology
alone is not enough to prove execute readiness.

Action:

Updated `scripts/s15_motion_block_diagnostics.sh` to print driver parameters:

- `can_port`
- `arm_type`
- `auto_enable`
- `control_enabled`
- `speed_percent`
- `enable_timeout`

Next:

Rerun the updated diagnostics while the observation terminal is in intended
active mode. Before any execute retry, confirm the active Arm B node reports
`control_enabled=true` and `auto_enable=true`.

## 2026-07-02 - S15 Active Driver Parameters Confirmed

Phase: S15 双臂双手协调脚本

Goal:
Confirm whether the current S15 observation terminal is really running active
drivers, not read-only drivers.

Result:

The updated diagnostics showed:

- Arm A:
  - `can_port=can_arm_a`
  - `auto_enable=True`
  - `control_enabled=True`
  - `speed_percent=5`
  - `enable_timeout=5.0`
- Arm B:
  - `can_port=can_arm_b`
  - `auto_enable=True`
  - `control_enabled=True`
  - `speed_percent=5`
  - `enable_timeout=5.0`
- Both arms:
  - `ctrl_mode=1`
  - `arm_status=0`
  - `err_status=0`
  - no joint-limit flags
  - no joint communication flags

Interpretation:

The current ROS session is active and healthy. Missing command subscription or
read-only launch mode is not the current blocker.

If Web enable was changed after the failed S15 left execute attempt, that likely
explains why the first waypoint produced no motion. If Web enable was not
changed, the cause is still unresolved.

Next:

Do not retry the wide S15 left execute immediately. First run a small Arm B
J1 `+2 deg` ROS command-path probe using the accepted S12 isolation script.

## 2026-07-02 - S15 Arm B Command-Path Probe Accepted

Phase: S15 双臂双手协调脚本

Goal:
Verify the current active ROS command path with a small Arm B motion before
retrying the wide S15 left-side sequence.

Procedure:

- Dry-run and execute Arm B J1 `+2 deg` using the accepted S12 isolation script.
- Keep RViz visible.
- Verify Arm B moves and returns while Arm A remains passive.

Result:

The operator reported that the probe passed.

Detailed terminal output was not provided in this turn, so the acceptance is
recorded from operator observation. If exact numeric values are needed later,
append the terminal output to `docs/results/s15_arm_b_command_path_probe_result_20260702.md`.

Interpretation:

The current active ROS command path can execute a small Arm B command. This
supports the hypothesis that the earlier S15 left execute no-motion timeout was
caused by the arm not being fully enabled at the time of that attempt, especially
if Web enable was changed afterward.

Next:

Retry S15 left-side execute only after rechecking active observation, RViz
visibility, Web/driver enable state, Arm B sweep clearance, left-hand closing
clearance, and J6/J7 cable slack.

## 2026-07-02 - S15 Gesture Target Redesign Started

Phase: S15 双臂双手协调脚本

Goal:
Respond to operator feedback that the attempted S15 motion did not match the
intended human-like elbow-curl/fist gesture.

Observation:

The numeric target `joint1=30 deg`, `joint2=90 deg`, `joint3=30 deg` was valid
as a raw joint command, but it was not a validated semantic gesture. The motion
did not match the operator's expected human-like elbow curl.

Decision:

- Stop treating the absolute J1/J2/J3 target as the elbow-curl gesture.
- Add a return-to-initial script that can open both hands and return the arms to
  the S15 field `park` posture.
- Build the elbow-curl/fist action from empirical joint-mapping probes instead
  of assumed joint numbers.

Files added:

- `scripts/ros_s15_return_to_initial.py`
- `docs/phases/s15_return_to_initial_and_elbow_curl_design.md`

Deployment choices:

- `S15 park` is not factory zero and not Web zero calibration.
- `S15 park` is the accepted field posture from the current S15 setup:
  arms hanging/prepared and hands open.
- The first elbow-curl mapping will use Arm B because left side maps to
  Arm B + left LinkerHand on `can1`.

Next:

Run return-to-initial dry-run, then execute only after clearance review. After
that, run small Arm B J2/J3/J4 probes to determine which joint and sign produce
the visible elbow-curl effect.

## 2026-07-02 - S15 Slow Elbow-Curl Candidate Script Added

Phase: S15 双臂双手协调脚本

Goal:
Convert the operator-observed Web gesture into a slow ROS + SDK demo gate.

Observation:

- The return-to-initial script ran successfully by operator report.
- Web control showed that left-side Arm B `J1 -10 deg` and `J4 +10 deg` better
  match the intended human-like elbow-curl demo effect.
- The operator requested a `2 deg` probe first, then a formal `10 deg` demo.
- Speed must be slow.

Implementation:

- Added `scripts/ros_s15_elbow_curl_demo.py`.
- Default dry-run motion is left side, Arm B, `J1 -2 deg`, `J4 +2 deg`.
- Formal motion is supplied by arguments: `--j1-delta-deg -10
  --j4-delta-deg 10`.
- Slow controls:
  - active S15 driver remains at `speed_percent=5`;
  - script default `--max-step-deg 2`;
  - script default `--waypoint-dwell 0.5`;
  - hand default `--hand-speed 20`.
- Execution still requires `--execute`, `--confirm-clearance`, and
  `--confirm-rviz-visible`.
- Deltas above `5 deg` require `--allow-wide-motion`.

Deployment choice:

The current accepted elbow-curl candidate is delta-based, not an absolute joint
target. The old absolute `joint1=30 deg`, `joint2=90 deg`, `joint3=30 deg`
sequence remains deprecated for this demo.

Next:

Run the arm-only `2 deg` probe with `--skip-hand`. If accepted, run the formal
left-side demo with `J1 -10 deg`, `J4 +10 deg`, and half-fist first.

## 2026-07-02 - S15 Elbow-Curl Semantic Motion Accepted, Continuity Issue Found

Phase: S15 双臂双手协调脚本

Goal:
Record the first accepted elbow-curl/fist semantic motion and explain the
observed stop-start behavior.

Operator result:

- The operator executed left-side Arm B with `J1 -10 deg`, `J4 +15 deg`,
  `hand_close_fraction=0.5`.
- The action matched the intended demo semantics.
- The operator observed that the arm and hand were not visually continuous:
  the motion looked like repeated stop/start steps.

Reason:

- The safe segmented script used `waypoint_count=8`.
- For every waypoint, the script published one `move_j`, waited until feedback
  reached the waypoint, then applied `waypoint_dwell=0.5`.
- This forces the controller to decelerate/stop at each intermediate target.
- The hand sequence was also serial: it started only after the curl posture was
  reached and after SDK connection/health/speed setup completed.

Implementation update:

- Added `--arm-profile {segmented,single-target}`.
- `segmented` remains the default safe inspection mode.
- `single-target` sends the arm curl target once, letting the controller
  perform one continuous point-to-point move.
- Added `--hand-timing {after-curl,during-curl}`.
- `during-curl` pre-connects the LinkerHand SDK, sets speed, anchors the open
  pose, then closes/opens the hand in a worker thread during the arm curl.

Next:

Run the same accepted left-side gesture in dry-run and then execute with:
`--arm-profile single-target --hand-timing during-curl`.

## 2026-07-02 - S15 Arm A Reproduction Planned With Larger J1 Offset

Phase: S15 双臂双手协调脚本

Goal:
Prepare the accepted elbow-curl/fist demo for Arm A / right hand.

Operator decision:

- Proceed from the accepted left-side demo to Arm A.
- Use `--side right`, which maps to Arm A and right hand `can2`.
- Set Arm A `J1` delta to `-20 deg` so the path stays away from the support
  column between the two arms.

Implementation update:

- The S15 elbow-curl demo script previously limited J1/J4 deltas to `15 deg`.
- The local demo cap is now `25 deg`.
- The wide-motion gate remains active: any delta above `5 deg` still requires
  `--allow-wide-motion`.

Next:

Run Arm A dry-run with `--side right --j1-delta-deg -20 --j4-delta-deg 15`,
then execute only after the dry-run target summary, RViz, and physical clearance
are accepted.

## 2026-07-02 - S15 Arm A J1 World-Direction Sign Mismatch Found

Phase: S15 双臂双手协调脚本

Goal:
Resolve the mismatch between raw J1 joint signs and the shared `lab_world`
direction semantics during Arm A reproduction.

Operator result:

- Arm A / right hand reproduction ran smoothly and matched the gesture
  expectation.
- The only mismatch was direction: Arm A raw `J1 -20 deg` rotated toward
  `lab_world +X`, while the accepted Arm B left-side gesture used raw
  `J1 -10 deg` to move toward `lab_world -X`.

Cause:

- Arm A and Arm B are mounted facing each other.
- J1 raw signs are local joint signs, not shared world-frame signs.
- The S13 direction-sign correction already showed that local joint sign and
  world-visible direction must be explicitly calibrated.

Implementation update:

- `scripts/ros_s15_elbow_curl_demo.py` now defaults to
  `--j1-delta-frame lab-world-x`.
- In this mode, `--j1-delta-deg` is interpreted as a `lab_world X` semantic
  delta:
  - Arm B raw J1 delta = requested J1 delta.
  - Arm A raw J1 delta = negative requested J1 delta.
- `--j1-delta-frame raw-joint` remains available for explicit low-level
  debugging.

Next:

Rerun Arm A dry-run with the same operator-facing semantic command
`--side right --j1-delta-deg -20 --j4-delta-deg 15`. The dry-run should print
`command_delta_deg={'joint1': 20.0, 'joint4': 15.0}` before execute.

## 2026-07-02 - S15 Dual-Arm Elbow-Curl Gate Prepared

Phase: S15 双臂双手协调脚本

Goal:
Move from accepted single-side elbow-curl/fist demos to the first simultaneous
dual-arm version.

Operator result:

- Arm A/right-side reproduction with unified `lab_world X` J1 semantics was
  accepted by field observation.
- The previous Arm A raw-sign mismatch is resolved at the script level: Arm A
  raw J1 is flipped when `--j1-delta-frame lab-world-x` is active.

Implementation update:

- `scripts/ros_s15_elbow_curl_demo.py` now accepts `--side both`.
- Per-side deltas were added:
  `--left-j1-delta-deg`, `--right-j1-delta-deg`,
  `--left-j4-delta-deg`, and `--right-j4-delta-deg`.
- In dual mode, both arm targets are published in the same waypoint gate.
- Hand open/close/open can run on both LinkerHand SDK connections during the
  curl through one worker thread per hand.

Next:

Dry-run the dual-arm demo with left Arm B semantic `J1 -10/J4 +15` and right
Arm A semantic `J1 -20/J4 +15`. The dry-run should show raw Arm B
`joint1=-10 deg` and raw Arm A `joint1=+20 deg`. Execute only after RViz,
clearance, and active-driver state are confirmed.

## 2026-07-02 - S15 Dual-Arm Coordination Accepted And Zero Return Corrected

Phase: S15 双臂双手协调脚本

Goal:
Record the accepted dual-arm/dual-hand demo result and correct the return
script's default target.

Operator result:

- The dual-hand/dual-arm coordinated elbow-curl/fist demo ran through.
- The final return-to-initial behavior needed correction: the intended default
  initial posture is the current all-joint-zero posture, not the older S15
  field park.

Implementation update:

- `scripts/ros_s15_return_to_initial.py` now defaults to `--pose zero`.
- `--pose zero` commands Arm A and Arm B `joint1..joint7 = 0 deg` and opens
  both hands.
- The previous recorded field park remains available as `--pose s15-park` for
  reproducing older S15 checks.
- The script output now prints an explicit `pose_definition` so dry-runs show
  whether the target is `zero` or `s15-park`.

Safety note:

- `zero` here is a normal joint-space command target. It is not Web zero
  calibration and not automatic zero setting.
