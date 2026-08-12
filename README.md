# nero_wrapper

面向 AgileX NERO 双七自由度机械臂 + 双 LinkerHand L6 的安全 Python wrapper 和现场操作仓库。它提供无 ROS 依赖的类型化配置、只读状态访问、主机/CAN 诊断和可复用安全门；已经在真机上验收的 ROS2 与动作入口仍保留在 `scripts/`，避免重构改变现场语义。

当前 package API 故意不提供运动方法。真实动作仍必须使用已验收脚本，并遵守 dry-run、急停、空间清空、控制源互斥和反馈可见性门禁。

English entry: [README_EN.md](README_EN.md)  
完整流程计划: [PLAN.md](PLAN.md) / [PLAN_EN.md](PLAN_EN.md)

## 重要文档

- [贡献与真机安全规则](CONTRIBUTING.md): 代码边界、验证方式和真机门禁。
- [文档地图](docs/README.md): 当前操作文档与历史证据的边界。
- [当前 Bring-Up 状态](docs/status/current_bringup_status.md): 当前配置、验收结果和下一步。
- [部署日志](docs/status/deployment_log.md): 每一步真实执行、证据、风险和后续动作。
- [Bring-Up Checklist](docs/status/bringup_checklist.md): 现场复验清单。
- [Setup Framework](docs/status/setup_framework.md): 工程分层、硬件事实、默认配置。
- [机器人部署与调试行动路线](docs/phases/机器人部署与调试行动路线.md): 历史阶段路线和详细记录。

## 目录结构

```text
.
├── src/nero_wrapper/       # 可安装、无 ROS 依赖的只读 wrapper
├── tests/                  # 配置、SDK 生命周期、诊断和安全门测试
├── config/                 # 非敏感默认值和本地配置模板
├── docker/                 # ROS2 Humble 容器
├── examples/               # package 兼容入口
├── rviz/                   # RViz 配置
├── scripts/                # 已验收现场脚本和历史开发入口
├── docs/
│   ├── status/             # 当前状态、日志、checklist、工程框架
│   ├── phases/             # 历史阶段计划、设计和操作流程
│   ├── results/            # 验收结果、audit、diagnostics
│   ├── evidence/           # 图片证据和 ROS 快照
│   ├── assets/             # 手册、协议表、CAD/STEP/STL
│   └── upstream/           # 上游仓库分析和 review
└── upstream/               # ignored，本地上游源码证据缓存
```

## 安装和只读自检

```bash
./setup.sh
source .venv/bin/activate
source config/nero.env

nero-config
nero-doctor --skip-can
nero-read-state --arm arm_a
```

`nero-read-state` 默认只打印配置，不连接硬件。确认 SocketCAN 已激活并安装厂商 `pyAgxArm` SDK 后，显式加 `--connect` 才读取反馈；它仍不会使能或移动机械臂。机器专属设置从 `config/nero.local.env.example` 复制到被 git 忽略的 `config/nero.local.env`。

## 固定控制架构

| 设备 | 本机接口 | 控制路径 |
| --- | --- | --- |
| Arm A / 右侧 | `can_arm_a`, USB `1-3.4.1:1.0`, ROS `/arm_a` | ROS2 `agx_arm_ros` |
| Arm B / 左侧 | `can_arm_b`, USB `1-3.4.3:1.0`, ROS `/arm_b` | ROS2 `agx_arm_ros` |
| Left hand | `can1`, USB `1-3.4.4:1.0` | LinkerHand SDK wrapper |
| Right hand | `can2`, USB `1-3.4.2:1.0` | LinkerHand SDK wrapper |

不要在 ROS arm driver active 时运行 arm SDK motion。不要在项目 hand wrapper active 时运行 LinkerHand GUI/demo/gesture 脚本。

## Getting Started

目标：一个新操作员按本节从上电开始，完成双臂双手 elbow-curl/fist 演示。默认需要两只终端：Terminal 1 持续运行 ROS driver + RViz，Terminal 2 下发演示命令。

### 1. 上电和现场检查

1. 确认双臂底座固定，工作空间内无人、无线缆会被 J6/J7 或灵巧手拉扯。
2. 确认急停/断电路径可立即触达。
3. 插好航插和电源；航插红点对齐，XT30 防呆接头插到位。
4. 给两条臂和双手供电。
5. 观察每条臂底座状态灯：绿色/闪烁绿色可继续；红色表示异常，先在 Web 首页查看状态，不要继续执行。
6. 等待硬件稳定，不要立即判断 CAN/ROS 状态。

### 2. 逐台进入 Web 控制并使能

主机内置 Wi-Fi 同一时间只能连一个机械臂热点，所以按 Arm A、Arm B 逐台操作。Web 地址默认为 `http://192.168.31.1/`；账号与密码从实验室凭据存储获取，并只写入本机 `config/nero.local.env`，不要提交到仓库。

1. 连接 Wi-Fi `agx-7ax-armA`，打开 `http://192.168.31.1/`。
2. 确认首页没有红色异常；如有异常，先记录并处理。
3. 点击右上角 `web模式` / Web control 按钮。
4. 点击 `使能`，选择使能全部关节。
5. 断开 Arm A Wi-Fi，连接 Wi-Fi `agx-7ax-armB`。
6. 重复第 2-4 步，使能 Arm B 全部关节。
7. Web 操作完成后，回到主机终端；双臂实时控制走 USB-CAN，不依赖 Wi-Fi 同时在线。

### 3. 绑定四路 CAN 端口

在仓库根目录执行：

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

四路接口都应为 `UP`，bitrate 为 `1000000`。如果刚刚重插 USB-CAN、重启电源或重新上电，先等 20 秒：

```bash
sleep 20
```

### 4. Terminal 1: 启动 driver 和 RViz

保持这个终端运行。它会启动双臂 ROS driver、静态坐标、RViz 和观察链路。

```bash
NERO_CONTAINER_NAME=nero-dual-arm-hand-observe \
  bash scripts/run_humble_container.sh --allow-xhost \
    bash /workspace/nero/scripts/launch_dual_arm_hand_observe.sh --active
```

在 RViz 中确认左右臂位置和现场一致。如果 RViz 显示水平零位或与实物不一致，先停止，不要执行动作，运行诊断：

```bash
NERO_CONTAINER_NAME=nero-rviz-diagnostics \
  bash scripts/run_humble_container.sh \
    bash /workspace/nero/scripts/rviz_pose_diagnostics.sh
```

### 5. Terminal 2: 执行双臂双手演示

确认工作空间清空、RViz 可见、双手线束没有拉扯风险后，在第二个终端执行：

```bash
NERO_CONTAINER_NAME=nero-dual-arm-hand-demo \
  bash scripts/run_humble_container.sh \
    python3 /workspace/nero/scripts/dual_arm_hand_elbow_curl_demo.py \
      --side both \
      --left-j1-delta-deg -20 \
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

演示完成后，必要时回到初始姿态：

```bash
NERO_CONTAINER_NAME=nero-return-initial \
  bash scripts/run_humble_container.sh \
    python3 /workspace/nero/scripts/return_to_initial.py \
      --execute \
      --allow-wide-motion \
      --confirm-clearance \
      --confirm-rviz-visible
```

完成后在 Terminal 1 按 `Ctrl-C` 停止 driver/RViz。

### 备注：dry-run

如果更换了场地、线缆、姿态、操作者，或对当前状态不确定，先做 dry-run。把 Terminal 2 命令里的 `--execute --allow-wide-motion --confirm-clearance --confirm-rviz-visible` 去掉即可；dry-run 不发送运动命令。

## 硬安全边界

- Web 端红灯或状态异常时，不继续执行脚本。
- 外部供电不超过 25V，电流能力不小于 10A；末端 XT30 2+2 为 24V、2A MAX。
- RViz visual anchor 只用于观察，不用于控制、规划、限位、标定或语义验收。
- 任何新控制路径、较大动作、接触式任务、MoveIt execute、Cartesian motion、raw CAN motion、MIT 控制、零点设置、固件升级、碰撞等级修改，都需要单独计划和验收。
- 如果 `/arm_a/feedback/joint_states` 或 `/arm_b/feedback/joint_states` 频率异常接近 400 Hz，先排查重复 ROS publisher。

## 上游依赖复现

```bash
mkdir -p upstream

git clone https://github.com/agilexrobotics/agx_arm_ros.git upstream/agx_arm_ros
git -C upstream/agx_arm_ros checkout c73d33f2ab377447261423f1b881bd89c6663627

git clone https://github.com/agilexrobotics/pyAgxArm.git upstream/pyAgxArm
git -C upstream/pyAgxArm checkout a226840db0c3d5c5dc7f3ec78d6cef1a6800f9e6

git clone https://github.com/agilexrobotics/piper_ros.git upstream/piper_ros
git -C upstream/piper_ros checkout 2dc30fca68cbf4e04d1d0bc15c123d026380ece7
```

LinkerHand SDK 为用户提供或私有访问来源：

```bash
git clone https://github.com/LV-Robotics-Lab/linkerhand_sdk upstream/linkerhand_sdk
```
