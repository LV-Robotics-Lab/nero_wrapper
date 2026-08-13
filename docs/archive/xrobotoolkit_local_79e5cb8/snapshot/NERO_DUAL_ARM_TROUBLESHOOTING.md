# Nero双臂遥操作问题诊断与解决方案

## 问题概述

你在CAN总线上连接了两个Nero手臂，想用Quest控制器进行双臂遥操作，但遇到以下问题：
1. 程序无法启动可视化（meshcat报错）
2. Meshcat中模型缺少部分

## 根本原因

### 问题1: 库依赖冲突
**症状**: `ImportError: /lib/x86_64-linux-gnu/libstdc++.so.6: version CXXABI_1.3.15 not found`

**原因**: conda环境中的ICU库需要新版libstdc++，但系统优先加载了旧版系统库

**解决方案**: 在启动程序前设置正确的库路径
```bash
export LD_LIBRARY_PATH=/home/lvrobotics/miniconda3/envs/nero/lib:$LD_LIBRARY_PATH
```

### 问题2: Meshcat模型加载缓慢/不完整
**症状**: 浏览器中打开meshcat URL，模型显示不完整

**原因**: 
- DAE mesh文件过大（尤其是link2.dae = 24MB）
- 浏览器需要时间下载和渲染大型mesh文件
- Meshcat通过WebSocket传输几何体数据，大文件会导致加载延迟

**解决方案**: 
1. **等待加载完成** - 打开浏览器后等待1-2分钟让所有mesh加载
2. **使用STL替代DAE** - STL文件更小更快（见下文）
3. **降低mesh分辨率** - 简化mesh以减小文件大小

## 当前状态验证

### ✅ 已确认正常的部分:
- URDF文件存在且路径正确
- Mesh文件（DAE/STL）都存在
- 双臂URDF生成正确（19个links）
- Placo模型加载成功（16个visual几何体）
- 硬件连接正常（readonly模式可以读取双臂状态）
- FK验证通过（arm_a=0.012mm/0.003deg, arm_b=0.014mm/0.003deg）
- 两臂固件版本: 1.121，使用v112驱动

### ⚠️ 需要修复的部分:
- Meshcat可视化启动需要正确的环境变量
- 大型DAE文件加载缓慢

## 快速启动指南

### 方法1: 使用提供的启动脚本（推荐）

```bash
# 1. 确保Quest已连接并运行XRoboToolkit PC Service
# 2. 确保CAN接口已配置：
#    - can0 -> Arm A (左手控制器)
#    - can1 -> Arm B (右手控制器)

# 3. 运行shadow模式（安全，不发送命令到硬件）
/tmp/run_nero_shadow_with_quest.sh

# 4. 在浏览器中打开: http://127.0.0.1:7000
# 5. 等待1-2分钟让mesh加载完成
# 6. 释放两个握把键，然后握紧开始控制
```

### 方法2: 手动运行

```bash
# 激活环境并设置库路径
source /home/lvrobotics/miniconda3/etc/profile.d/conda.sh
conda activate nero
export LD_LIBRARY_PATH=/home/lvrobotics/miniconda3/envs/nero/lib:$LD_LIBRARY_PATH

# 进入项目目录
cd /home/lvrobotics/workspace/XRoboToolkit-Teleop-Sample-Python

# 运行shadow模式（只IK，不发送命令）
python scripts/hardware/teleop_dual_nero_hardware.py \
    --mode shadow \
    --layout bench \
    --arm-a-can can0 \
    --arm-b-can can1 \
    --visualize-placo

# 或者不使用可视化（如果meshcat有问题）
python scripts/hardware/teleop_dual_nero_hardware.py \
    --mode shadow \
    --layout bench \
    --arm-a-can can0 \
    --arm-b-can can1
```

### 方法3: 运行readonly模式（测试硬件连接）

```bash
source /home/lvrobotics/miniconda3/etc/profile.d/conda.sh
conda activate nero
export LD_LIBRARY_PATH=/home/lvrobotics/miniconda3/envs/nero/lib:$LD_LIBRARY_PATH
cd /home/lvrobotics/workspace/XRoboToolkit-Teleop-Sample-Python

python scripts/hardware/teleop_dual_nero_hardware.py \
    --mode readonly \
    --arm-a-can can0 \
    --arm-b-can can1
```

## 安全说明

### 运行模式
1. **readonly**: 只读取硬件状态，不使能，不发送命令 ✅ 安全
2. **shadow**: IK计算 + 可视化，不使能硬件，不发送命令 ✅ 安全  
3. **execute**: 真实控制，需要明确的live confirmation ⚠️ 需要验证和安全措施

### Execute模式注意事项
在运行execute模式前必须：
1. 通过readonly和shadow模式验证
2. 确认物理急停可用
3. 确认工作空间无障碍物
4. 确认TCP标定正确
5. 添加 `--live-confirmation MOVE_NERO` 参数

```bash
# Execute模式示例（谨慎使用）
python scripts/hardware/teleop_dual_nero_hardware.py \
    --mode execute \
    --layout bench \
    --arm-a-can can0 \
    --arm-b-can can1 \
    --visualize-placo \
    --live-confirmation MOVE_NERO
```

## 优化Meshcat加载速度

### 方法1: 使用STL替代DAE

修改 `xrobotoolkit_teleop/hardware/nero_model.py`:

```python
def _rewrite_mesh_paths(element: ET.Element, mesh_root: Path) -> None:
    package_prefix = "package://agx_arm_description/agx_arm_urdf/nero/meshes/"
    for mesh in element.findall(".//mesh"):
        filename = mesh.get("filename", "")
        if filename.startswith(package_prefix):
            relative_path = filename[len(package_prefix) :]
            # 使用STL而不是DAE
            if relative_path.startswith("dae/"):
                relative_path = relative_path.replace("dae/", "").replace(".dae", ".stl")
            mesh.set("filename", str((mesh_root / relative_path).resolve()))
```

### 方法2: 简化Visual模型

创建一个低分辨率的可视化URDF，只包含简单的几何体（box/cylinder）替代复杂的mesh。

## 坐标系配置

当前bench布局的坐标系配置：

```python
BENCH_BASE_TRANSFORMS = {
    "arm_a": BaseTransform(
        xyz=(0.0, 0.0, 0.0),           # lab_world原点
        rpy=(π, π/2, 0.0)              # 朝向: 对置，joint2指向下
    ),
    "arm_b": BaseTransform(
        xyz=(0.260, 0.0, 0.0),         # 距离arm_a 260mm
        rpy=(0.0, π/2, 0.0)            # 朝向: 对置，joint2指向下
    ),
}

# 硬件到模型的关节偏移
HARDWARE_TO_MODEL_JOINT_OFFSETS = {
    "arm_a": (0.0, -π/2, 0.0, 0.0, 0.0, 0.0, 0.0),  # joint2偏移-90度
    "arm_b": (0.0, -π/2, 0.0, 0.0, 0.0, 0.0, 0.0),  # joint2偏移-90度
}
```

## 控制器映射

```
Quest左手控制器 -> Arm A (can0) -> 左侧机械臂
Quest右手控制器 -> Arm B (can1) -> 右侧机械臂

握把键(grip) >= 0.7: 启用增量控制
握把键 < 0.2: 释放控制，保持当前位置
```

## 已知警告（可以忽略）

```
WARNING: Robot has the following self collisions in neutral position:
  -arm_a_link5_0 collides with arm_a_link6_0
  -arm_b_link5_0 collides with arm_b_link6_0
```

这是link5和link6在初始姿态下的预期碰撞，属于正常现象（相邻关节的碰撞被允许）。

## 故障排除

### Meshcat显示"Can Upgrade only to WebSocket"
这是正常的，说明HTTP服务运行正常。在浏览器中访问 http://127.0.0.1:7000 即可。

### 模型部分不显示
1. 等待1-2分钟让大型mesh文件加载
2. 打开浏览器控制台查看是否有加载错误
3. 检查网络面板，确认mesh文件正在下载
4. 尝试使用STL替代DAE（见优化章节）

### arm_b feedback=0Hz
某一臂的反馈频率为0Hz通常表示：
1. CAN连接不稳定
2. 该臂处于紧急停止状态
3. 需要重新插拔CAN适配器或重启硬件

### "XRoboToolkit returned an invalid timestamp"
确保Quest上的XRoboToolkit PC Service正在运行并已连接。

## 参考文档

- 官方Nero接口: `dependencies/agx_arm_ros/docs/CAN_USER.md`
- 另一个Nero项目: `/home/lvrobotics/workspace/nero-quest-DM-remote-control/`
- Placo文档: https://placo.readthedocs.io/

## 下一步

1. ✅ 验证readonly模式可以读取双臂状态
2. ✅ 验证shadow模式IK计算正常
3. ⏳ 测试Quest控制器输入
4. ⏳ 验证meshcat可视化完整性
5. ⏳ 标定TCP工具坐标系
6. ⏳ Execute模式安全测试

完成以上所有步骤后，才能进入真实的遥操作控制。
