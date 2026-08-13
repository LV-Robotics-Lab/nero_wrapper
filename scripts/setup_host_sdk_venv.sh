#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/.." && pwd)"

if [ -f "$repo_root/config/nero.env" ]; then
  # shellcheck disable=SC1091
  . "$repo_root/config/nero.env"
fi

venv_path="$repo_root/${NERO_HOST_SDK_VENV:-.venv/nero-sdk}"
sdk_path="${NERO_PYAGXARM_ROOT:-$repo_root/submodules/pyAgxArm}"
python_bin="/usr/bin/python3"

if [ ! -x "$python_bin" ]; then
  echo "Missing $python_bin. The host SDK venv must use system Python, not Conda Python." >&2
  exit 1
fi

if [ ! -f "$sdk_path/setup.py" ] && [ ! -f "$sdk_path/pyproject.toml" ]; then
  echo "Missing pinned pyAgxArm submodule: $sdk_path" >&2
  echo "Run: git submodule update --init submodules/pyAgxArm" >&2
  exit 1
fi

"$python_bin" -m venv --clear "$venv_path"

# shellcheck disable=SC1091
source "$venv_path/bin/activate"

python -m pip install --upgrade pip setuptools wheel
python -m pip install "python-can>=3.3.4"
python -m pip install "$sdk_path"

python - <<'PY'
import can
from pyAgxArm import create_agx_arm_config, AgxArmFactory, ArmModel, NeroFW
print("python-can:", getattr(can, "__version__", "unknown"))
print("pyAgxArm import ok")
PY

echo "Host SDK venv ready: $venv_path"
echo "Activate it with: source $venv_path/bin/activate"
