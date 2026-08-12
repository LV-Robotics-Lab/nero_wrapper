#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
venv_dir="${NERO_WRAPPER_VENV:-$script_dir/.venv}"
python_bin="${NERO_WRAPPER_PYTHON:-}"

if [ -z "$python_bin" ]; then
  for candidate in python3.12 python3.11 python3.10 python3; do
    if command -v "$candidate" >/dev/null 2>&1 &&
      "$candidate" -c 'import sys; raise SystemExit(sys.version_info < (3, 10))'; then
      python_bin="$candidate"
      break
    fi
  done
fi

if [ -z "$python_bin" ]; then
  printf 'nero_wrapper requires Python 3.10 or newer.\n' >&2
  exit 1
fi

if [ ! -d "$venv_dir" ]; then
  "$python_bin" -m venv "$venv_dir"
fi

if ! "$venv_dir/bin/python" -c 'import sys; raise SystemExit(sys.version_info < (3, 10))'; then
  printf 'Existing venv uses an unsupported Python: %s\n' "$venv_dir" >&2
  printf 'Remove that generated venv or choose a new NERO_WRAPPER_VENV.\n' >&2
  exit 1
fi

"$venv_dir/bin/python" -m pip install --upgrade pip
"$venv_dir/bin/python" -m pip install -e "$script_dir"

printf 'Installed nero_wrapper in %s\n' "$venv_dir"
printf 'Activate with: source %s/bin/activate\n' "$venv_dir"
