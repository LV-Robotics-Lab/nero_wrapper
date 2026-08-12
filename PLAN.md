# NERO 双臂双手完整工作流程

本文是当前交付流程的中文主计划。它压缩了 S0-S15 阶段路线，并锁定后续操作默认值，便于项目交付人员复验、交接和继续推进。

## 当前状态

- 当前硬件：两条 NERO 7-DOF 机械臂，双 LinkerHand L6 灵巧手已安装。
- 当前拓扑：Arm A = 右手 = `/arm_a` + `can_arm_a` + hand `can2`；Arm B = 左手 = `/arm_b` + `can_arm_b` + hand `can1`。
- 当前架构：arms 使用 ROS2 `agx_arm_ros`；hands 使用 LinkerHand SDK wrapper。
- 已完成：S10 双臂低速运动、S11 `lab_world` 基线、S12 控制隔离、S13 低风险双臂原语、S14 双手低风险 bring-up、S15 elbow-curl/fist demo。
- 下一 gate：执行 `ros_s15_return_to_initial.py` 默认 `--pose zero` 的回零复验，记录证据并关闭 S15。

## 阶段流程

| 阶段 | 状态 | 交付输出 |
| --- | --- | --- |
| S0 资料基线 | Complete | 手册、CAN 协议、CAD/STEP、关键图片已归档到 `docs/assets/` 和 `docs/evidence/` |
| S1 安全与场地 | Complete for planning | 场地、供电、固定、急停路径和人员边界已记录 |
| S2 主机环境 | Complete | Ubuntu 20.04 host SDK/CAN-only + Docker ROS2 Humble |
| S3 离线模型 | Complete | NERO URDF/xacro/RViz 验证通过 |
| S4-S5 上电/Web | Complete | 双臂 Web 验机、热点身份、版本状态通过 |
| S6-S8 CAN/SDK/ROS 只读 | Complete | 双路 CAN、SDK read-state、ROS feedback/RViz follow 通过 |
| S9 标定配置 | Complete | 安装姿态、负载、TCP、状态快照完成 |
| S10 首次低速运动 | Complete | A/B Web、SDK、ROS 单关节低速运动通过 |
| S11 双臂实验基线 | Complete | `lab_world`、静态 TF、RViz accepted screenshot、post-TF snapshot |
| S12 控制隔离 | Complete | A/B 单臂主动、另一臂 passive monitor 通过 |
| S13 双臂低风险原语 | Complete | 双臂 active/hold 与非接触 joint-space 同步通过 |
| S14 末端执行器 | Complete | 双 LinkerHand L6 health/open/index micro/dual gates 通过 |
| S15 双臂双手协调 | Accepted by operator report | elbow-curl/fist demo 跑通；待 zero-return closure |

## 固定工作循环

每一步都按以下顺序执行：

1. 读取 `docs/status/current_bringup_status.md` 和相关 `docs/phases/` 文档。
2. 说明本次动作属于哪个阶段、为什么可执行。
3. 先 dry-run，再 execute。
4. 用 ROS topic、CAN 状态、RViz、脚本输出或 operator report 验证。
5. 更新 `docs/status/deployment_log.md`。
6. 如阶段状态、设备映射、安全边界或验收结论变化，更新 `docs/status/current_bringup_status.md`、`config/nero.env` 和相关阶段文档。

## S15 标准复验流程

1. 环境和控制源审计：

```bash
source config/nero.env
bash scripts/check_environment.sh
bash scripts/s10_control_source_audit.sh
```

2. 四路 CAN 准备：

```bash
bash scripts/activate_can.sh can_arm_a 1000000 "1-3.4.1:1.0"
bash scripts/activate_can.sh can_arm_b 1000000 "1-3.4.3:1.0"
bash scripts/activate_can.sh can1 1000000 "1-3.4.4:1.0"
bash scripts/activate_can.sh can2 1000000 "1-3.4.2:1.0"
```

3. 启动 readonly observe：

```bash
NERO_CONTAINER_NAME=nero-humble-s15-observe \
  bash scripts/run_humble_container.sh --allow-xhost \
    bash /workspace/nero/scripts/launch_s15_dual_arm_hand_observe.sh --readonly
```

4. 回零 dry-run：

```bash
NERO_CONTAINER_NAME=nero-humble-s15-init \
  bash scripts/run_humble_container.sh \
    python3 /workspace/nero/scripts/ros_s15_return_to_initial.py
```

5. 确认 RViz、clearance 和 active-driver 后，重启 active observe：

```bash
NERO_CONTAINER_NAME=nero-humble-s15-observe \
  bash scripts/run_humble_container.sh --allow-xhost \
    bash /workspace/nero/scripts/launch_s15_dual_arm_hand_observe.sh --active
```

6. 回零 execute：

```bash
NERO_CONTAINER_NAME=nero-humble-s15-init \
  bash scripts/run_humble_container.sh \
    python3 /workspace/nero/scripts/ros_s15_return_to_initial.py \
      --execute \
      --allow-wide-motion \
      --confirm-clearance \
      --confirm-rviz-visible
```

7. S15 demo 复现时使用 accepted 参数，先 dry-run，再 execute：

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

Execute 版本必须追加 `--execute --allow-wide-motion --confirm-clearance --confirm-rviz-visible`。如 full fist 或更大幅度动作被要求，必须另开 gate。

## 故障处理规则

- USB/CAN 或电源重连后等待约 20 秒，再判定 CAN/ROS 反馈是否异常。
- 如果某个 arm interface UP 但 `candump` 或 ROS driver 无响应，先检查线缆和供电，再重新激活 CAN。
- 如果 `/arm_a/feedback/joint_states` 或 `/arm_b/feedback/joint_states` 约 400 Hz，优先检查重复 ROS publisher。
- 如果 RViz 姿态与实物不一致，运行：

```bash
NERO_CONTAINER_NAME=nero-humble-s15-diagnostics \
  bash scripts/run_humble_container.sh \
    bash /workspace/nero/scripts/s15_rviz_pose_diagnostics.sh
```

- `docs/evidence/ros_snapshots` 是 ROS 只读快照归档目录；新快照脚本也写入该路径。

## 后续计划

- 关闭 S15：回零复验、post-motion snapshot、日志和状态更新。
- 建立 ROS2 hand service/action wrapper，将 LinkerHand SDK 包成可调度接口。
- 建立 arm/hand 统一 timeline logging。
- 在任何抓取、接触、handoff、近距离双臂 manipulation 前，新增独立 safety gate、碰撞空间评审和回退脚本。

## 验收检查

- `python -m pip install -e '.[dev]'`
- `ruff check src tests examples/nero_read_state.py`
- `pytest`
- `python -m compileall -q src examples scripts`
- `bash -n config/nero.env setup.sh scripts/*.sh docker/humble/entrypoint.sh`
- `bash scripts/check_environment.sh`
- `rg 'docs/' README.md README_EN.md PLAN.md PLAN_EN.md CONTRIBUTING.md config scripts docs --glob '!docs/vendor/**'` 抽查路径是否有效。
- `git status --short` 只应包含预期的目录移动、文档新增/更新和误生成文件清理。
