# NERO Bring-Up Checklist

现场执行时按顺序勾选。任一阶段未通过，不进入下一阶段。

## S0 资料与配置

- [ ] 已阅读 [机器人部署与调试行动路线](../phases/机器人部署与调试行动路线.md)。
- [ ] 已确认 `docs/assets/manuals/nero 用户手册.md` 可访问。
- [ ] 已确认 `docs/assets/manuals/机械臂通信协议V1.2.1.xlsx` 为 CAN 协议主文件。
- [ ] 已确认 `docs/assets/cad/nero3d.stp` 和末端工具 STEP 文件存在。
- [ ] 已确认 `docs/evidence/pics/` 关键图片存在。
- [ ] 已执行 `source config/nero.env` 或明确覆盖默认变量。
- [ ] 已记录本次目标：只读调试、首次低速运动、末端工具接入或应用集成。

## S1 安全与机械准备

- [ ] 操作区域空旷，人员离开 NERO 工作半径。
- [ ] 已确认最大负载不超过 3 kg。
- [ ] 底座按安装图固定完成：70 mm x 70 mm 孔位，4 x Ø5.4 贯穿孔，M5 紧固件。
- [ ] 线束不会被 J6/J7 或末端工具拉扯。
- [ ] 已确认急停路径：Web 急停、必要时断电、后续 CAN `0x150`。
- [ ] 已理解失能/断电时机械臂可能下落。
- [ ] 已准备记录：照片、视频、终端日志、Web 截图。

## S2 主机环境

- [ ] 已阅读 `docs/upstream/upstream_repo_analysis.md`。
- [ ] 已阅读 `docs/phases/s2_hybrid_host_container_plan.md`。
- [ ] `bash scripts/check_environment.sh` 已运行。
- [ ] 已确认当前路线为 S2A 主机 SDK/CAN-only + S2B Docker ROS2 Humble。
- [ ] 安装 `docker.io` 前已向操作者说明必要性和共享主机权限风险。
- [ ] 安装 `ethtool` 前已向操作者说明必要性和低风险性质。
- [ ] `docker` 可用，且本项目暂用 `sudo docker`，未默认加入 `docker` 组。
- [ ] 若执行 S2A，当前主机 `python-can` 版本满足 `>=3.3.4`。
- [ ] 若执行 S2A，`pyAgxArm` 可 import。
- [ ] `candump`、`cansend` 可用。
- [ ] `ethtool` 可用。
- [ ] 若执行 S2B，Docker image `nero-humble:local` 已构建。
- [ ] 若执行 S2B，容器内 OS/ROS 为 Ubuntu 22.04 + ROS2 Humble。
- [ ] 若执行 S2B，容器内 `ros2` 可用。
- [ ] 若执行 S2B，容器内 `colcon` 可用。
- [ ] 若执行 S2B，`~/agx_arm_ws` 已完成 `colcon build`。
- [ ] 若执行 S2B，`source ~/agx_arm_ws/install/setup.bash` 已执行。
- [ ] 未把 Conda Python 3.13 混入 ROS apt 工作区。

## S3 离线模型

- [ ] 已阅读 `docs/phases/s3_model_validation.md`。
- [ ] Docker Humble 容器内 `xacro` 和 `check_urdf` 通过裸臂 NERO 模型。
- [ ] Docker Humble 容器内 `robot_state_publisher` 可加载 `nero_description.urdf`。
- [ ] RViz 可显示 `arm_type:=nero`；桌面会话中已确认 X11/RViz 路径可用。
- [ ] 7 个关节名称、父子链路、主要尺寸已核对。
- [ ] J2 URDF 限位与手册机械范围的零位/角度映射差异已记录，等待真机反馈确认。
- [ ] 末端工具配置选择已确认：`none`、夹爪、示教器或灵巧手。
- [ ] 安装姿态已确认：正装、侧装或倒装。
- [ ] 初始 TCP offset 已记录。

## S4 机械与电气连接

- [ ] 使用 DC24V 供电。
- [ ] 外部供电不超过 25V。
- [ ] 外部供电电流能力不小于 10A。
- [ ] 航插红点对齐，插接无硬插。
- [ ] 黄色线接 CAN_H。
- [ ] 蓝色线接 CAN_L。
- [ ] 红色 VCC、黑色 GND 确认无误。
- [ ] 电源分支和 CAN 分支已分开确认，红/黑不接入 USB-CAN。
- [ ] 航插红点对齐后插入，无硬插。
- [ ] USB-CAN 端子线芯在压片中心，轻拉不脱落。
- [ ] 末端 XT30 2+2 为 24V、2A MAX。
- [ ] 末端 XT30 2+2 图示方向已确认：上方电源 +/-，下方 CAN H/L。
- [ ] 未将第三方 CAN 设备接入末端 CAN。

## S5 Web 验机

- [ ] 当前操作对象已贴物理标签：Arm A 或 Arm B。
- [ ] Wi-Fi `agx-7ax-xx` 可连接，或以太网同网段配置完成。
- [ ] Web 地址 `http://192.168.31.1/` 或 `http://10.90.0.150/` 可访问。
- [ ] 已从实验室凭据存储取得账号和密码并成功登录，未把凭据写入仓库。
- [ ] 状态灯绿色；若红色，已记录 Web 状态页错误。
- [ ] 已记录软件版本和关节固件版本。
- [ ] `关节1` 到 `关节7` 的电压、温度、错误和失能/使能状态已逐项记录。
- [ ] 已确认 Web 显示的 `7ax` 是当前这一条 NERO 7 轴臂。
- [ ] 双臂现场已逐台完成 S5；热点名为 `agx-7ax-armA` 和 `agx-7ax-armB`。
- [ ] 若需要有线同时接入，两条臂已有唯一有线 IP。
- [ ] 已单独记录每条臂的控制器/IP/供电/CAN 接入计划。
- [ ] 已确认当前模式。
- [ ] 未执行运动命令。

## S6 CAN 只读

- [ ] 双臂现场未把两条臂接到同一个 CAN 总线上。
- [ ] 当前操作对象已确认：Arm A 或 Arm B。
- [ ] 已用 `bash scripts/find_can_ports.sh` 记录两个 USB-CAN 模块的 bus-info。
- [ ] `bash scripts/activate_can.sh can_arm_a 1000000 "<Arm A USB bus-info>"` 成功。
- [ ] `bash scripts/activate_can.sh can_arm_b 1000000 "<Arm B USB bus-info>"` 成功。
- [ ] `ip -details link show can_arm_a` 显示 CAN UP 且 bitrate `1000000`。
- [ ] `ip -details link show can_arm_b` 显示 CAN UP 且 bitrate `1000000`。
- [ ] `can_arm_a` 和 `can_arm_b` 均为 `ERROR-ACTIVE`。
- [ ] 已记录物理 USB 口：Arm A 竖向 USB 口，Arm B 横向 USB 口。
- [ ] Web 端 CAN 通讯开关状态已确认。
- [ ] `candump can_arm_a` 能收到帧。
- [ ] `candump can_arm_b` 能收到帧。
- [ ] 两条链路均收到 `0x2A1` 状态反馈。
- [ ] 两条链路均收到 `0x2A5-0x2A7` 和 `0x2A9` 关节角反馈。
- [ ] 拔掉 Arm A CAN 时只停止 `can_arm_a` 反馈。
- [ ] 拔掉 Arm B CAN 时只停止 `can_arm_b` 反馈。
- [ ] 状态无急停、无解、奇异、超限、通信异常、碰撞、过温。
- [ ] 此阶段未发送 `cansend` 控制帧。

## S7 SDK 只读

- [ ] 已根据 Web 版本选择 `--firmware default/v111/v112/v120`。
- [ ] `python3 examples/nero_read_state.py --firmware <selector>` dry run 成功。
- [ ] `python3 examples/nero_read_state.py --connect --channel can_arm_a --firmware <selector>` 成功。
- [ ] `python3 examples/nero_read_state.py --connect --channel can_arm_b --firmware <selector>` 成功。
- [ ] SDK 关节角反馈连续。
- [ ] SDK TCP 位姿反馈连续。
- [ ] SDK 状态与 Web/CAN 一致。
- [ ] 无通信错误。

## S8 ROS 只读

- [x] 驱动 launch 成功。
- [x] 启动时显式设置 `auto_enable:=false control_enabled:=false`。
- [x] `/arm_a/feedback/joint_states` 连续。
- [x] `/arm_a/feedback/tcp_pose` 连续。
- [x] `/arm_a/feedback/arm_status` 连续。
- [x] `/arm_b/feedback/joint_states` 连续。
- [x] `/arm_b/feedback/tcp_pose` 连续。
- [x] `/arm_b/feedback/arm_status` 连续。
- [x] RViz 使用 `follow:=true control:=false`。
- [x] RViz 姿态与实物一致。
- [x] 未使用 MoveIt execute。
- [x] 未向 `/control/*` 下发运动。

## S9 标定与配置

- [x] 安装姿态已在 Web 设置并记录。
- [x] 末端执行器当前为 `默认（无加载）` 并已记录。
- [x] TCP offset 当前 ROS 默认值已记录。
- [x] 负载级别与实际一致。
- [x] 关节限位不超过手册范围。
- [x] 速度/加速度已记录。
- [x] 碰撞保护等级已记录，未设为常规 0 检测。
- [x] 零点页面已只读记录；未执行零点设置。
- [x] S9 ROS 只读快照已保存。
- [x] S9.2 三项决策已记录。
- [x] A/B 负载模式已从 `满载` 改为当前裸臂对应的空载/无负载选项。
- [x] 负载模式变更后 ROS 只读快照正常。

## S10 首次低速运动

- [x] Web/SDK/ROS/CAN 反馈均已通过。
- [x] 只有一个控制源启用。
- [x] 已阅读 `docs/phases/s10_first_motion_plan.md`。
- [x] 已选择单条机械臂：Arm A。
- [x] ROS 只读驱动已停止，Web 是唯一控制源。
- [x] Web 已切换到 `WEB` 模式。
- [x] Web 速度百分比已设为最低可用值，优先 `5%` 或更低。
- [x] 工作空间无人。
- [x] 急停路径已确认。
- [x] 已确认 J6/J7 周围无线缆张力。
- [x] Arm A Web 使能成功。
- [x] Arm A Web 关节控制成功。
- [x] Arm A 7 个自由度均运动成功。
- [x] 停止后状态正常。
- [x] Web 动作后 ROS 只读快照已保存：`docs/evidence/ros_snapshots/20260625_060810/`。
- [x] Web 动作后 A/B `err_status: 0`，关节限位和通信异常均为 `false`。
- [ ] 急停后恢复流程实际触发测试通过。
- [ ] 已阅读 `docs/phases/s10_2_sdk_motion_plan.md`。
- [x] SDK J7 dry-run 已通过且未运动。
- [x] SDK J1 `+1 deg` dry-run 已通过且未运动。
- [x] J1 小角度扫掠区域已确认空旷。
- [x] SDK J1 `+2 deg` 目标确认为 Arm A J1-only `+2 deg`。
- [x] SDK 低速单关节运动通过。
- [x] SDK 动作后 ROS 只读快照已保存：`docs/evidence/ros_snapshots/20260625_062910/`。
- [x] SDK 动作后 A/B `err_status: 0`，关节限位和通信异常均为 `false`。
- [x] 已阅读 `docs/phases/s10_3_ros_motion_plan.md`。
- [x] ROS Arm A control driver 已以 `auto_enable:=true control_enabled:=true speed_percent:=5` 启动。
- [x] ROS dry-run 目标确认为 Arm A `joint1`-only `+2 deg`。
- [x] ROS 低速单关节运动通过。
- [x] ROS 动作后 ROS 只读快照已保存：`docs/evidence/ros_snapshots/20260625_064243/`。
- [x] ROS 动作后 A/B `err_status: 0`，关节限位和通信异常均为 `false`。
- [x] 已阅读 `docs/results/s10_4_stop_recovery_closure.md`。
- [x] `scripts/s10_control_source_audit.sh` 语法检查通过。
- [x] Arm A ROS control driver 已停止或确认未运行。
- [x] 已在真实桌面终端运行 `bash scripts/s10_control_source_audit.sh`。
- [x] 已确认无 SDK/ROS motion 脚本运行。
- [x] 已确认 Web 无主动运动命令。
- [x] 已记录交接状态，推荐为 `handoff_to_arm_b`。
- [x] S10.4 停止/恢复/安全收束流程通过。

## S10.5 Arm B 首次 Web 运动复刻

- [x] 已阅读 `docs/phases/s10_5_arm_b_first_motion_plan.md`。
- [x] 已确认当前操作对象为 Arm B。
- [x] 已连接 Arm B Web：`agx-7ax-armB` / `http://192.168.31.1/`。
- [x] 已运行 `bash scripts/s10_control_source_audit.sh` 并确认无 NERO 控制进程。
- [x] `can_arm_b` 为 UP、ERROR-ACTIVE、bitrate `1000000`。
- [x] Arm B J1 扫掠区域空旷。
- [ ] Arm A 未被命令。
- [x] Web 是唯一运动控制源。
- [x] Web 速度已设为最低可用值，优先 `5%` 或更低。
- [x] Arm B Web 使能成功。
- [x] Arm B J1 `+2 deg` 小角度运动成功。
- [x] Arm B J1 已回到原角度。
- [x] Web 停止后无主动运动命令。
- [x] Arm B Web 动作后 ROS 只读快照已保存：`docs/evidence/ros_snapshots/20260625_072129/`。
- [x] 动作后 A/B `err_status: 0`，关节限位和通信异常均为 `false`。

## S10.6/S10.7 Arm B SDK/ROS 复刻

- [x] S10.5 Web 复刻已通过。
- [x] Arm B SDK J1 `+2 deg` dry-run 已通过且未运动。
- [x] SDK dry-run 后 ROS 只读快照已保存：`docs/evidence/ros_snapshots/20260625_072742/`。
- [x] Arm B SDK J1 `+2 deg` 低速运动通过并回原角。
- [x] SDK 动作后 ROS 只读快照已保存且正常：`docs/evidence/ros_snapshots/20260625_074048/`。
- [x] 已阅读 `docs/phases/s10_7_arm_b_ros_motion_plan.md`。
- [x] 双臂只读 driver 已停止。
- [x] Arm B ROS control driver 已以 `auto_enable:=true control_enabled:=true speed_percent:=5` 启动。
- [x] Arm B ROS `joint1 +2 deg` dry-run 已通过且未运动。
- [x] Arm B ROS `joint1 +2 deg` 低速运动通过并回原角。
- [x] ROS 动作后 ROS 只读快照已保存且正常：`docs/evidence/ros_snapshots/20260625_074953/`。

## S10.8 双臂首次运动收束

- [x] Arm B ROS control driver 已停止或确认未运行。
- [x] 已运行 `bash scripts/s10_control_source_audit.sh`。
- [x] 已确认无 Web/SDK/ROS motion 脚本运行。
- [x] 已记录下一阶段选择：S11 双臂实验基线与坐标闭环。

## S11 双臂实验基线与坐标闭环

- [x] 已定义 `lab_world` 坐标系。
- [x] 已验收 `lab_world -> arm_a/world`：`x=0, y=0, z=0, roll=0, pitch=-1.5707963, yaw=0`。
- [x] 已验收 `lab_world -> arm_b/world`：`x=0.260 m, y=0, z=0, roll=3.1415926, pitch=-1.5707963, yaw=0`。
- [x] 已记录测量方法、工具、误差估计和照片；工具/误差未定量报告，已作为 S11 第一工程基线限制记录。
- [x] 已建立并验证静态 TF 发布方案。
- [x] RViz 中双臂相对位置与实物一致，且分别移动两臂时 RViz 会跟随。
- [x] 成功版 RViz 截图已保存：`docs/evidence/pics/S11_RViz_accepted_dual_arm_layout.png`。
- [x] post-TF ROS 只读快照已通过：`docs/evidence/ros_snapshots/20260626_055339/`。
- [x] 当前 TCP 定义已记录，裸臂阶段保持默认 TCP。
- [x] rosbag / snapshot / 实验日志命名规范已确定。

## S12 控制隔离与日志闭环

- [x] S12 控制隔离计划已建立：`docs/phases/s12_control_isolation_plan.md`。
- [x] S12 目标动作已定义为可见 J1 `30 deg`，仍然单臂轮流执行。
- [x] Arm A `joint1 +30 deg` dry-run 目标正确。
- [x] Arm A `joint1 +30 deg` 执行时 Arm B 不动，最大被动偏差 `0.005 deg`。
- [x] Arm A `joint1 +30 deg` post-motion 双臂只读快照通过：`docs/evidence/ros_snapshots/20260626_080809/`。
- [x] Arm B `joint1 -30 deg` dry-run 目标正确。
- [x] Arm B `joint1 -30 deg` 执行时 Arm A 不动，最大被动偏差 `0.008 deg`。
- [x] Arm B `joint1 -30 deg` post-motion 双臂只读快照通过：`docs/evidence/ros_snapshots/20260626_083210/`。
- [x] 同时启动两个 driver 时 namespace、CAN、日志互不混淆；每次仅目标臂 `control_enabled=true`。
- [x] 每次实验均记录命令、反馈、状态、快照/等价日志和 git commit；S12 未录 rosbag，按脚本输出与快照作为等价验收证据。
- [x] 异常停止和恢复记录格式已确定；未执行 intentional emergency-stop 测试。

## S13 低风险双臂协同原语

- [x] S13 低风险双臂原语计划已建立：`docs/phases/s13_low_risk_dual_arm_primitives_plan.md`。
- [x] 双臂同时 active driver 启动稳定。
- [x] 双臂同时 enable / hold，无位移，`hold_max_dev_deg <= 1.0`；实测 A/B 均为 `0.0 deg`。
- [x] A/B 同时 J1 dry-run 目标正确：Arm A `+30 deg`，Arm B `-30 deg`。
- [x] A/B 同时 `30 deg` joint-space 动作已安全执行并回原位；A/B `err_status=0`，非目标关节偏差小于 `1.0 deg`。
- [x] S13 原始符号世界方向语义已判定失败：Arm A `+30 deg` / Arm B `-30 deg` 被现场观察为同向运动，不作为通过原语。
- [x] S13 post-motion 双臂只读快照通过：`docs/evidence/ros_snapshots/20260626_090214/`。
- [x] S13 修正符号 dry-run 通过：Arm A `joint1 +30 deg`，Arm B `joint1 +30 deg`，A/B `err_status=0`，hold 偏差小于 `1.0 deg`。
- [x] S13 修正符号执行通过：Arm A `joint1 +30 deg`，Arm B `joint1 +30 deg`，操作者确认可见方向符合预期，A/B final `err_status=0`。
- [x] `docs/evidence/ros_snapshots/20260626_093414/` 已记录为不验收：A/B 状态健康、`Failed capture commands: 0`，但 joint-state 约 `400 Hz`。
- [x] `docs/evidence/ros_snapshots/20260629_043358/` 已记录为不验收：A/B 状态健康、`Failed capture commands: 0`，但 joint-state 仍约 `400 Hz`。
- [x] 重跑前已确认 `/arm_a/feedback/joint_states` 和 `/arm_b/feedback/joint_states` 均为 `Publisher count: 1`。
- [x] S13 修正符号执行后双臂只读快照通过：`docs/evidence/ros_snapshots/20260629_043441/`。
- [x] 未进入笛卡尔、MoveIt 或 manipulation primitive 之前已完成快照验收。

## S14 末端执行器

- [x] 两只灵巧手机械安装已完成，当前按 Arm A 右手、Arm B 左手记录。
- [x] 已记录线束限制：J6/J7 附近存在运动约束，约 `70 deg` 以上大幅弯折可能影响线束。
- [x] S14.0 线束照片已归档：`docs/evidence/pics/S14自然状态线束.jpeg`、`docs/evidence/pics/S14手腕弯折状态线束.jpeg`。
- [x] 左右手映射和机械安装稳定性已确认：Arm A 右手、Arm B 左手。
- [x] 末端工具供电/通讯线在当前临时边界内无干涉；超过约 `70 deg` 的 J6/J7 大幅弯折仍禁止。
- [ ] 夹爪/示教器/灵巧手类型与 Web/ROS 配置一致。
- [ ] 如使用旧 Piper 夹爪，已完成 ID 更改确认。
- [ ] 灵巧手安装后已复核 `docs/evidence/pics/4 灵巧手示意图.png` 和 `docs/evidence/pics/5 灵巧手法兰安装示意图.png`，并确认出线位置与法兰缺口居中。
- [x] S14.1 双臂 no-motion ROS 只读快照通过：`docs/evidence/ros_snapshots/20260629_074337/`；A/B `Publisher count: 1`。
- [x] S14.1 观察项已记录：A/B `arm_status=3`，按上游说明为 `奇异点`，因此后续不从当前姿态直接做腕部/笛卡尔/手指动作。
- [x] S14.2 Web/ROS `effector_type:=revo2`、左右手模型、负载和 TCP 决策已记录：全局默认仍为 `none`，S14 手部只读专用脚本显式使用 `revo2`。
- [x] S14.3 首次 Revo2 topic 检查已诊断：driver 实际日志为 `effector_type: none`，因此没有 `hand` topic 不是硬件反馈失败。
- [x] S14.3 修正后的 Revo2 只读路径已暴露 A/B `hand` endpoint：`/feedback/hand_status`、`/control/hand`、`/control/hand_position_time`。
- [x] S14.3 raw `ros2 topic echo --once /arm_a/feedback/hand_status` 长时间无输出已记录；后续改用带超时探针。
- [x] LinkerHand SDK 已下载并移入 `upstream/linkerhand_wrapper/`；审阅记录见 `docs/upstream/s14_linkerhand_sdk_review.md`。
- [x] S14 手部事实源已改为 LinkerHand L6 优先；AgileX Revo2 ROS `hand_status` 不再作为这些手的主验收路径。
- [x] 已新增目标接口 LinkerHand 识别脚本：`scripts/s14_linkerhand_identify_can.sh`。
- [x] 现场已澄清当前装机路径为手部三排线接 NERO J6 末端接口，不是电脑直连手部 USB-CAN。
- [x] 2026-06-30 `can_arm_a` 被动抓包仅见臂本体反馈；Web 可使能手臂但不能使能机械手。
- [x] S14.3L 直连 LinkerHand CAN 识别已判定为当前装机形态不适用；不在 `can_arm_a`/`can_arm_b` 上运行。
- [x] S14.3J Web `6.8.5 末端执行器配置` 已截图/记录：当前配置为 `强脑灵巧手`，不是默认无加载。
- [x] S14.3J Web `6.3 灵巧手` 已截图/记录：`普通灵巧手`、`revo2`、`位置控制`、enable 无报错。
- [x] S14.3J Web 小幅单指 `发送` 同步 `candump` 证据已记录：Web 无报错但手未动，样本未见 Revo2 `0x1B*` / `0x1C*` 帧。
- [x] 2026-06-30 新 Linker Drive 文档包已下载、校验、解压并审阅；记录见 `../data-collection/docs/reviews/linker_drive_20260630_review.md`。
- [x] 新资料已将下一步修正为 S14.3K：先确认 Linker/LBOT `192.168.10.21` 控制器是否存在，再继续 Revo2/J6 假设。
- [x] S14.3K Linker/LBOT 只读网络探针已完成：当前主机无 `192.168.10.x` 地址，`ping -c 2 192.168.10.21` 丢包，`curl -I --max-time 3 http://192.168.10.21:8000` 超时。
- [x] `docs/evidence/pics/灵巧手连接设备/` 照片已分析：设备为 bench DC 电源 + USB-CAN 调试工装，不是 Linker/LBOT `192.168.10.21` 网络控制器。
- [x] `灵巧手连接设备03.jpeg` 裸露/断开线头风险已记录：该工装在修复、绝缘、万用表确认 pinout 前禁止上电或接手。
- [ ] 已向供应商确认 NERO J6 是否支持 LinkerHand L6、是否需要 Linker/LBOT 控制器或固件选项。
- [ ] 若改走手部直连 bench-test，一只手断开 NERO J6 后已按单独 checklist 做 24V/CAN 极性核对和只读身份/状态读取。
- [ ] bench-test 工装所有裸露线头已正确压接/绝缘，且已确认 V+/GND/CAN_H/CAN_L 与 L6 手册一致。
- [ ] S14.3J 过滤 Revo2 帧复验已完成：`timeout 20s candump -tz can_arm_a,1B0:7F0,1C0:7F0`。（仅在 S14.3K 结论后继续。）
- [ ] S14.3J J6 末端供电通讯线和手端接头已重新断电复插并复验。
- [ ] 若未来改回手部直连 bench-test，S14.3L LinkerHand 左/右手串码、版本、state/current/temperature/fault 只读结果已记录。
- [ ] 夹爪 `0x2A8` 或上层反馈正常。
- [ ] 低速小行程动作正常。
- [ ] 无过流、过温、传感器异常。

## S15 应用集成

- [x] S15 RViz 视觉姿态重新验收通过：真实双臂垂悬时，RViz 使用当前会话的观测链显示同样姿态。
- [x] 已确认 `/arm_*/visual/joint_states` 只用于 RViz 观察，不用于控制、规划、限位或标定。
- [x] S15 初始化脚本已修正：默认 `--pose zero`，回到 A/B `joint1..joint7 = 0 deg` 并打开手；旧 field park 仅通过 `--pose s15-park` 显式使用。
- [x] S15 曲肘候选动作已按 Web/ROS 观察修正为左侧 Arm B `J1 -10 deg` / `J4 +10..15 deg`，语义动作符合预期。
- [x] S15 曲肘握拳正式动作的连续性已通过：single-target arm motion + hand during-curl，手 open -> close -> open，并返回初始位。
- [x] S15 Arm A / right hand 复刻动作顺滑且手臂/手语义符合预期；发现 raw Arm A `J1 -20 deg` 世界方向相反。
- [x] S15 J1 已按 `lab_world X` 语义复验通过：`--side right --j1-delta-deg -20` dry-run 打印 Arm A raw `joint1 +20 deg`，执行时朝 `lab_world -X` 避开中间支撑柱。
- [x] S15 双臂协同曲肘握拳已通过：`--side both`，左侧 Arm B semantic `J1 -10/J4 +15`，右侧 Arm A semantic `J1 -20/J4 +15`，双手 open -> half close -> open，并返回初始位。
- [ ] MoveIt 先规划不执行，轨迹可达且不越限。
- [ ] 应用节点有速度、加速度、限位保护。
- [ ] rosbag 或日志记录已配置。
- [ ] 异常状态会停止任务。
- [ ] 版本、启动命令、参数文件已归档。
- [ ] 连续运行验收时长达标。
