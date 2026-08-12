# NERO Setup Framework

本文是项目工程框架说明，详细阶段路线见 [机器人部署与调试行动路线](../phases/机器人部署与调试行动路线.md)。

## 工程分层

| 层级 | 目标 | 工具/资料 | 当前可做 |
| --- | --- | --- | --- |
| 资料基线 | 统一事实源 | 用户手册、CAN 协议、STEP 模型 | 已完成初版整理 |
| 主机环境 | SDK/CAN 工具 + Docker ROS2 | Ubuntu 20.04 host、Docker、ROS2 Humble container、can-utils | 可离线准备 |
| 离线模型 | URDF/RViz/CAD 验证 | `agx_arm_ros`、STEP | 可离线准备 |
| Web 验机 | 状态、版本、模式、错误 | Wi-Fi/以太网 Web | 需真机 |
| CAN 只读 | SocketCAN 和反馈帧 | `candump`、协议表 | 需真机 |
| SDK 只读 | Python API 状态读取 | `pyAgxArm` | 需真机 |
| ROS 只读 | ROS topic 与 RViz 跟随 | `agx_arm_ros` | 需真机 |
| 标定配置 | 安装、TCP、负载、限位 | Web 优先 | 需真机 |
| 低速运动 | 最小闭环控制 | Web/SDK/ROS | 需真机且通过闸口 |
| 应用集成 | MoveIt/任务/采集 | 项目节点 | 后置 |

## 推荐目录

```text
~/agx_arm_ws/
  src/
    pyAgxArm/
    agx_arm_ros/
  build/
  install/
  log/

/home/lv-robotics/workspace/nero_wrapper/
  README.md
  pyproject.toml
  config/
  docs/
  docker/
  examples/
  scripts/
  src/nero_wrapper/
  tests/
  upstream/
```

`upstream/` 是本项目的只读证据缓存，用于记录已经阅读过的上游源码状态。正式运行和
构建使用共享主机上的 `~/agx_arm_ws`，并在 Docker ROS2 Humble 容器中执行。

## 硬件事实

| 项目 | 值 |
| --- | --- |
| 自由度 | 7 |
| 有效负载 | 3 kg |
| 本体重量 | 4.8 kg |
| 重复定位精度 | +/- 0.1 mm |
| 工作半径 | 580 mm |
| 标准供电 | DC24V |
| 外部供电上限 | 不超过 25V，电流能力不小于 10A |
| 功耗 | 最大 <= 150W，综合 <= 60W |
| 通讯 | CAN / HTTP / TCP |
| 底座安装 | 70 mm x 70 mm，4 x Ø5.4 through holes，M5 fastening |
| 环境 | -20 到 50 摄氏度，25%-85% RH，非冷凝 |

## 关节范围与速度

| 关节 | 范围 | 最大速度 |
| --- | --- | --- |
| J1 | -157 到 157 deg | 180 deg/s |
| J2 | -15 到 190 deg | 180 deg/s |
| J3 | -160 到 160 deg | 180 deg/s |
| J4 | -60 到 125 deg | 225 deg/s |
| J5 | -160 到 160 deg | 225 deg/s |
| J6 | -43 到 58 deg | 225 deg/s |
| J7 | -90 到 90 deg | 225 deg/s |

调试阶段不要按最大速度运行，首次运动使用低速、小角度。

## 网络与 Web 默认值

| 项目 | 值 |
| --- | --- |
| Wi-Fi SSID | `agx-7ax-xx` |
| Wi-Fi 密码 | 从实验室凭据存储获取；不写入仓库 |
| Wi-Fi Web 地址 | `http://192.168.31.1/` |
| Web 账号 | `admin` |
| Web 密码 | 从实验室凭据存储获取；不写入仓库 |
| 有线默认 IP | `10.90.0.150` |
| 主机静态 IP 示例 | `10.90.0.153/24` |
| 网关 | 留空 |
| DNS | `8.8.8.8` |

手册同时提到内网接口用于技术支持。现场不要把维护/内网口当作未授权控制入口。

## CAN 协议基线

| 项目 | 值 |
| --- | --- |
| 标准 | CAN2.0B 标准帧 |
| 波特率 | 1000K |
| 数据格式 | Motorola/MSB |
| CAN_H | 黄色 |
| CAN_L | 蓝色 |

关键反馈：

- `0x2A1`：机械臂状态、模式、故障码。
- `0x2A2-0x2A4`：TCP 位姿。
- `0x2A5-0x2A7`：J1-J6 角度。
- `0x2A9`：J7 角度。
- `0x2A8`：夹爪反馈。
- `0x251-0x257`：关节高速反馈，20 ms。
- `0x261-0x267`：关节低速反馈，100 ms。

关键控制：

- `0x150`：快速急停、轨迹、拖动示教。
- `0x151`：CAN 控制模式、MOVE 模式、速度百分比、安装位置、CAN 推送。
- `0x152-0x154`：TCP 目标。
- `0x155-0x157`：J1-J6 目标角。
- `0x170`：J7 目标角。
- `0x159`：夹爪控制。
- `0x471`：电机使能/失能。
- `0x475`：零点、加速度、清除错误。
- `0x47A/0x47B`：碰撞保护等级设置/反馈。

原始 CAN 手写控制默认禁止，必须先通过 Web、SDK、ROS 只读链路验收。

## Manual Images

关键图片已经保存在 `docs/evidence/pics/`：

| File | Use |
| --- | --- |
| `2.1.1控制面板说明.png` | 底座面板布局：Wi-Fi 天线、航插、状态灯、网口、内网接口 |
| `航插接口示意图.jpg` | 航插红点对齐 |
| `2.1.2末端连接电器说明.png` | 末端 XT30 2+2：上方电源 `+/-`，下方 CAN `H/L` |
| `2.3.1 底座安装说明.png` | 底座 `70 mm x 70 mm`、4 x `Ø5.4` 贯穿孔 |
| `3.1can线链接.jpg` | 红/黑电源分支、黄/蓝 USB-CAN 分支 |
| `3.1can线链接1.png` | USB-CAN 端子压接方向 |
| `3.2上电使用说明.png` | 首次上电连接顺序 |
| `4 灵巧手示意图.png` | 灵巧手尺寸 |
| `5 灵巧手法兰安装示意图.png` | 灵巧手法兰安装 |

## ROS/SDK 默认策略

- ROS2 工作区：`~/agx_arm_ws`
- 当前部署模式：Ubuntu 20.04 host + Docker Ubuntu 22.04/ROS2 Humble
- 主机职责：SDK/CAN-only、SocketCAN、USB-CAN、基础诊断
- 容器职责：`agx_arm_ros`、RViz、ROS topic、MoveIt/应用集成
- Docker image：`nero-humble:local`
- Docker 权限策略：先使用 `sudo docker`，不默认加入 `docker` 组
- CAN 口：`can0`
- CAN bitrate：`1000000`
- ROS arm type：`nero`
- 默认末端：`none`
- 计划末端：灵巧手，S14 末端执行器阶段再启用
- 初始 TCP offset：`[0.0, 0.0, 0.0, 0.0, 0.0, 0.0]`
- SDK 固件 selector：先用 Web 读实际固件，再选择 `default`、`v111`、`v112`、`v120`
- Noetic：不作为默认路线；仅在硬性 legacy ROS1 要求下单独验证。

真机首次 RViz 在 ROS2 Humble 容器内执行。需要 GUI 时先从主机启动容器：

```bash
bash scripts/run_humble_container.sh --allow-xhost
```

容器内启动 RViz follow：

```bash
ros2 launch agx_arm_ctrl start_single_agx_arm_rviz.launch.py \
  can_port:=can0 \
  arm_type:=nero \
  effector_type:=none \
  follow:=true \
  control:=false
```

## 控制源策略

| 场景 | 推荐控制源 | 禁止项 |
| --- | --- | --- |
| 首次上电 | Web 只读 | 运动命令 |
| CAN 验证 | `candump` 只读 | `cansend` 控制 |
| SDK 验证 | SDK read-state | SDK motion |
| ROS 验证 | topic echo + RViz follow | MoveIt execute |
| 首次运动 | Web 单关节低速 | 点位/圆弧/MIT/主从 |
| 应用集成 | 单一上层控制源 | 多控制源并发 |

## 高风险动作

以下动作必须单独记录审批、现场复核、保留日志：

- 自动/手动设置零点。
- 固件升级。
- MIT 控制。
- 主从联动。
- 修改碰撞保护等级。
- 修改关节限位或最大速度。
- 使用旧 Piper 夹爪并修改夹爪 ID。
- 原始 CAN 下发运动或参数设置帧。
