# XRoboToolkit local NERO snapshot

This directory preserves the NERO-owned portion of the uncommitted worktree
that was found in `XRoboToolkit-Teleop-Sample-Python` on 2026-08-13. The
upstream baseline was commit `79e5cb8a56e3455515ce1b476e993c764ec58739`.

The files under `snapshot/` are byte-for-byte copies of the modified worktree
files. They are retained for historical recovery and review; maintained NERO
drivers, models, safety checks and command lifecycle remain under
`src/nero_wrapper`, `scripts/`, and `tests/`.

`manifest.sha256` is sorted by snapshot-relative path and is the deletion audit
boundary for this portion of the retired worktree.
