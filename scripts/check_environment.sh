#!/usr/bin/env bash
set -u

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/.." && pwd)"

if [ -f "$repo_root/config/nero.env" ]; then
  # shellcheck disable=SC1091
  . "$repo_root/config/nero.env"
fi

fail_count=0
warn_count=0

ok() {
  printf '[ OK ] %s\n' "$1"
}

warn() {
  warn_count=$((warn_count + 1))
  printf '[WARN] %s\n' "$1"
}

info() {
  printf '[INFO] %s\n' "$1"
}

fail() {
  fail_count=$((fail_count + 1))
  printf '[FAIL] %s\n' "$1"
}

has_cmd() {
  command -v "$1" >/dev/null 2>&1
}

check_cmd() {
  local cmd="$1"
  local hint="${2:-}"
  if has_cmd "$cmd"; then
    ok "command found: $cmd"
  else
    if [ -n "$hint" ]; then
      fail "missing command: $cmd ($hint)"
    else
      fail "missing command: $cmd"
    fi
  fi
}

check_file() {
  local path="$1"
  local label="$2"
  if [ -f "$repo_root/$path" ]; then
    ok "$label: $path"
  else
    fail "missing $label: $path"
  fi
}

check_executable_file() {
  local path="$1"
  local label="$2"
  if [ -x "$repo_root/$path" ]; then
    ok "$label: $path"
  elif [ -f "$repo_root/$path" ]; then
    fail "$label is not executable: $path"
  else
    fail "missing $label: $path"
  fi
}

check_optional_file() {
  local path="$1"
  local label="$2"
  if [ -f "$repo_root/$path" ]; then
    ok "$label: $path"
  else
    info "optional $label not present: $path"
  fi
}

check_optional_cmd() {
  local cmd="$1"
  local hint="${2:-}"
  if has_cmd "$cmd"; then
    ok "command found: $cmd"
  else
    if [ -n "$hint" ]; then
      warn "missing optional command: $cmd ($hint)"
    else
      warn "missing optional command: $cmd"
    fi
  fi
}

printf 'NERO environment check\n'
printf '======================\n'

if [ -r /etc/os-release ]; then
  # shellcheck disable=SC1091
  . /etc/os-release
  ok "os: ${PRETTY_NAME:-unknown}"
else
  warn "cannot read /etc/os-release"
fi

printf 'kernel: %s\n' "$(uname -srmo)"

check_cmd git "required to clone upstream repositories"
check_cmd python3 "required by pyAgxArm and ROS2"
if [ "${NERO_DEPLOYMENT_MODE:-}" = "host20_docker_humble" ]; then
  check_optional_cmd pip3 "host SDK uses a project venv; global pip3 is not required"
  check_cmd docker "required to run the ROS2 Humble container"
  check_optional_cmd ros2 "expected inside the ROS2 Humble container, not on the Ubuntu 20.04 host"
  check_optional_cmd colcon "expected inside the ROS2 Humble container, not on the Ubuntu 20.04 host"
else
  check_cmd pip3 "required to install Python dependencies"
  check_cmd ros2 "source your ROS2 setup file, for example /opt/ros/humble/setup.bash"
  check_cmd colcon "install python3-colcon-common-extensions"
fi
check_cmd ip "install iproute2"
check_cmd candump "install can-utils"
check_cmd cansend "install can-utils"
check_cmd ethtool "install ethtool"
check_optional_cmd curl "useful for Web endpoint checks"
check_optional_cmd ping "useful for Web endpoint checks"

python_path="$(command -v python3 2>/dev/null || true)"
pip_path="$(command -v pip3 2>/dev/null || true)"
if [ -n "$python_path" ]; then
  printf 'python3 path: %s\n' "$python_path"
  case "$python_path" in
    *conda*|*miniconda*|*anaconda*)
      warn "python3 resolves to a Conda environment; ROS apt work should use a clean system Python shell"
      ;;
  esac
fi
if [ -n "$pip_path" ]; then
  printf 'pip3 path: %s\n' "$pip_path"
fi
if [ -x /usr/bin/python3 ]; then
  printf 'system python3: %s\n' "$(/usr/bin/python3 --version 2>&1)"
fi

printf '\nImportant documents\n'
printf '%s\n' '-------------------'
check_file "README.md" "Chinese README"
check_file "README_EN.md" "English README"
check_file "PLAN.md" "Chinese workflow plan"
check_file "PLAN_EN.md" "English workflow plan"
check_file "CONTRIBUTING.md" "contributing and safety rules"
check_file "pyproject.toml" "Python package metadata"
check_file "docs/README.md" "documentation map"
check_file "docs/status/current_bringup_status.md" "current bring-up status"
check_file "docs/status/deployment_log.md" "deployment log"
check_file "docs/status/bringup_checklist.md" "bring-up checklist"
check_file "docs/status/setup_framework.md" "setup framework"
check_file "docs/phases/机器人部署与调试行动路线.md" "deployment route"

printf '\nOperator script entry points\n'
printf '%s\n' '----------------------------'
check_executable_file "scripts/check_environment.sh" "environment check"
check_executable_file "scripts/activate_can.sh" "CAN activation script"
check_executable_file "scripts/run_humble_container.sh" "Humble container runner"
check_executable_file "scripts/launch_dual_arm_hand_observe.sh" "dual-arm observation launcher"
check_executable_file "scripts/rviz_pose_diagnostics.sh" "RViz diagnostics wrapper"
check_executable_file "scripts/dual_arm_hand_elbow_curl_demo.py" "elbow-curl demo wrapper"
check_executable_file "scripts/return_to_initial.py" "return-to-initial wrapper"

printf '\nManual evidence images\n'
printf '%s\n' '----------------------'
check_file "${NERO_PANEL_IMAGE:-docs/evidence/pics/2.1.1控制面板说明.png}" "panel image"
check_file "${NERO_END_CONNECTOR_IMAGE:-docs/evidence/pics/2.1.2末端连接电器说明.png}" "end connector image"
check_file "${NERO_BASE_MOUNT_IMAGE:-docs/evidence/pics/2.3.1 底座安装说明.png}" "base mounting image"
check_file "${NERO_CAN_WIRING_IMAGE:-docs/evidence/pics/3.1can线链接.jpg}" "CAN wiring image"
check_file "${NERO_CAN_TERMINAL_IMAGE:-docs/evidence/pics/3.1can线链接1.png}" "CAN terminal image"
check_file "${NERO_POWER_SEQUENCE_IMAGE:-docs/evidence/pics/3.2上电使用说明.png}" "power sequence image"
check_file "${NERO_AVIATION_CONNECTOR_IMAGE:-docs/evidence/pics/航插接口示意图.jpg}" "aviation connector image"
check_file "${NERO_HAND_DIMENSION_IMAGE:-docs/evidence/pics/4 灵巧手示意图.png}" "dexterous hand dimension image"
check_file "${NERO_HAND_FLANGE_IMAGE:-docs/evidence/pics/5 灵巧手法兰安装示意图.png}" "dexterous hand flange image"

printf '\nIgnored local asset archive\n'
printf '%s\n' '---------------------------'
check_optional_file "${NERO_USER_MANUAL:-docs/assets/manuals/nero 用户手册.md}" "local user manual"
check_optional_file "${NERO_CAN_PROTOCOL:-docs/assets/manuals/机械臂通信协议V1.2.1.xlsx}" "local CAN protocol"
check_optional_file "${NERO_BASE_STEP:-docs/assets/cad/nero3d.stp}" "local base STEP model"
check_optional_file "${NERO_GRIPPER_STEP:-docs/assets/cad/nero带夹爪以及带灵巧手模型/NERO夹爪版外发.STEP}" "local gripper STEP model"
check_optional_file "${NERO_DEXTEROUS_HAND_STEP:-docs/assets/cad/nero带夹爪以及带灵巧手模型/NERO带灵巧手.STEP}" "local dexterous hand STEP model"

printf '\nNERO defaults\n'
printf '%s\n' '-------------'
printf 'deployment_mode: %s\n' "${NERO_DEPLOYMENT_MODE:-native_ros2}"
printf 'container_image: %s\n' "${NERO_CONTAINER_IMAGE:-not_set}"
printf 'can_port: %s\n' "${NERO_CAN_PORT:-can0}"
printf 'can_bitrate: %s\n' "${NERO_CAN_BITRATE:-1000000}"
printf 'web_eth: %s\n' "${NERO_ETH_WEB_URL:-http://10.90.0.150/}"
printf 'web_wifi: %s\n' "${NERO_WIFI_WEB_URL:-http://192.168.31.1/}"
printf 'joint_limits: %s\n' "${NERO_JOINT_LIMITS_DEG:-unknown}"

if [ "${NERO_DEPLOYMENT_MODE:-}" = "host20_docker_humble" ]; then
  warn "ROS_DISTRO is expected inside the Docker container, not necessarily on the host"
else
  if [ -n "${ROS_DISTRO:-}" ]; then
    case "$ROS_DISTRO" in
      humble|jazzy)
        ok "ROS_DISTRO=$ROS_DISTRO"
        ;;
      *)
        warn "ROS_DISTRO=$ROS_DISTRO, upstream docs mention humble and jazzy"
        ;;
    esac
  else
    warn "ROS_DISTRO is not set"
  fi
fi

if python3 - <<'PY' >/tmp/nero_python_can_check.txt 2>&1
import can
print(getattr(can, "__version__", "unknown"))
PY
then
  ok "python-can import: $(cat /tmp/nero_python_can_check.txt)"
else
  warn "python-can is not importable by python3"
fi
rm -f /tmp/nero_python_can_check.txt

if python3 - <<'PY' >/tmp/nero_pyagxarm_check.txt 2>&1
from pyAgxArm import create_agx_arm_config, AgxArmFactory, ArmModel, NeroFW
print("pyAgxArm import ok")
PY
then
  ok "$(cat /tmp/nero_pyagxarm_check.txt)"
else
  warn "pyAgxArm is not importable by python3"
fi
rm -f /tmp/nero_pyagxarm_check.txt

host_sdk_python="$repo_root/${NERO_HOST_SDK_VENV:-.venv/nero-sdk}/bin/python"
if [ "${NERO_DEPLOYMENT_MODE:-}" = "host20_docker_humble" ]; then
  if [ -x "$host_sdk_python" ]; then
    if "$host_sdk_python" - <<'PY' >/tmp/nero_host_sdk_check.txt 2>&1
import can
from pyAgxArm import create_agx_arm_config, AgxArmFactory, ArmModel, NeroFW
print("host sdk venv ok, python-can=" + str(getattr(can, "__version__", "unknown")))
PY
    then
      ok "$(cat /tmp/nero_host_sdk_check.txt)"
    else
      warn "host SDK venv exists but cannot import python-can/pyAgxArm"
    fi
    rm -f /tmp/nero_host_sdk_check.txt
  else
    warn "host SDK venv not found at $host_sdk_python"
  fi
fi

if has_cmd ip; then
  if ip -details link show type can >/tmp/nero_can_links.txt 2>/dev/null; then
    if [ -s /tmp/nero_can_links.txt ]; then
      ok "CAN interfaces detected:"
      sed 's/^/       /' /tmp/nero_can_links.txt
    else
      warn "no CAN interfaces detected yet"
    fi
  else
    warn "could not query CAN interfaces"
  fi
  rm -f /tmp/nero_can_links.txt
fi

workspace="${NERO_ROS_WS:-${HOME}/agx_arm_ws}"
if [ -d "$workspace/src/agx_arm_ros" ]; then
  ok "agx_arm_ros found at $workspace/src/agx_arm_ros"
else
  warn "agx_arm_ros not found at $workspace/src/agx_arm_ros"
fi

if [ -d "$workspace/src/pyAgxArm" ]; then
  ok "pyAgxArm found at $workspace/src/pyAgxArm"
else
  warn "pyAgxArm not found at $workspace/src/pyAgxArm"
fi

printf '\nSummary: %s failure(s), %s warning(s)\n' "$fail_count" "$warn_count"

if [ "$fail_count" -gt 0 ]; then
  exit 1
fi
