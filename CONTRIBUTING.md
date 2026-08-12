# Contributing and real-robot safety

`nero_wrapper` controls a dual-arm real-robot system. A green unit test is not
authorization to move hardware.

## Change boundaries

- Keep the reusable package under `src/nero_wrapper/` independent of ROS.
- Keep ROS2-specific launch and motion paths under `scripts/` until they have
  been revalidated on the physical rig.
- Do not change joint limits, collision levels, firmware, calibration, CAN IDs,
  coordinate semantics, or accepted motion parameters without a separate
  hardware validation plan and evidence.
- Default every new motion command to dry-run. Execution must require explicit
  clearance, emergency-stop readiness, exclusive-control, and feedback gates.
- Never commit credentials, local topology overrides, logs, bags, build output,
  SDK downloads, or raw vendor archives.

## Before a pull request

```bash
python -m pip install -e '.[dev]'
ruff check src tests examples/nero_read_state.py
pytest
python -m compileall -q src examples scripts
bash -n config/nero.env setup.sh scripts/*.sh docker/humble/entrypoint.sh
```

Hardware execution is a separate, operator-supervised acceptance step. Record
the exact branch, commit, configuration, command, and outcome under `docs/`.
