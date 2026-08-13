#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/.." && pwd)"

if [ -f "$repo_root/config/nero.env" ]; then
  # shellcheck disable=SC1091
  . "$repo_root/config/nero.env"
fi

can_port="${1:-${NERO_CAN_PORT:-can0}}"
bitrate="${2:-${NERO_CAN_BITRATE:-1000000}}"
usb_port="${3:-}"
workspace="${NERO_ROS_WS:-${HOME}/agx_arm_ws}"

usage() {
  cat <<USAGE
Usage:
  bash scripts/activate_can.sh [can_port] [bitrate] [usb_port]

Examples:
  bash scripts/activate_can.sh can0 1000000
  bash scripts/activate_can.sh can_arm_a 1000000 "3-1.4:1.0"
  bash scripts/activate_can.sh can_arm_b 1000000 "3-1.1:1.0"

The vendor scripts support the official AgileX CAN module. If they are not
available, this helper falls back to a plain SocketCAN activation command.
USAGE
}

if [ "${1:-}" = "-h" ] || [ "${1:-}" = "--help" ]; then
  usage
  exit 0
fi

vendor_script=""

for candidate in \
  "$repo_root/submodules/agx_arm_ros/scripts/can_activate.sh" \
  "$repo_root/submodules/pyAgxArm/scripts/ubuntu/can_activate.sh" \
  "$workspace/src/agx_arm_ros/scripts/can_activate.sh" \
  "$workspace/src/pyAgxArm/scripts/ubuntu/can_activate.sh" \
  "./agx_arm_ros/scripts/can_activate.sh" \
  "./pyAgxArm/scripts/ubuntu/can_activate.sh"
do
  if [ -f "$candidate" ]; then
    vendor_script="$candidate"
    break
  fi
done

if [ -n "$vendor_script" ]; then
  echo "Using vendor CAN activation script: $vendor_script"
  if [ -n "$usb_port" ]; then
    bash "$vendor_script" "$can_port" "$bitrate" "$usb_port"
  else
    bash "$vendor_script" "$can_port" "$bitrate"
  fi
else
  echo "Vendor script not found. Falling back to SocketCAN commands."
  echo "This assumes the interface is already named $can_port."
  sudo ip link set "$can_port" down 2>/dev/null || true
  sudo ip link set "$can_port" up type can bitrate "$bitrate"
fi

ip -details link show "$can_port"
