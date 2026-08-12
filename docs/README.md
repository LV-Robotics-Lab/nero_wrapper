# Documentation map

The repository separates current operator guidance from historical bring-up
evidence. Historical material is preserved for provenance; it is not an active
runbook unless linked from the current status page.

## Current

- [`../README.md`](../README.md): Chinese quick start
- [`../README_EN.md`](../README_EN.md): English quick start
- [`status/current_bringup_status.md`](status/current_bringup_status.md): current accepted state
- [`status/bringup_checklist.md`](status/bringup_checklist.md): field revalidation checklist
- [`status/setup_framework.md`](status/setup_framework.md): hardware and deployment model
- [`../CONTRIBUTING.md`](../CONTRIBUTING.md): code and real-robot safety rules
- [`refactor_review.md`](refactor_review.md): refactor findings and compatibility boundary

## Historical evidence

- `phases/`: phase-specific plans and procedures
- `results/`: accepted and rejected result reports
- `evidence/`: ROS snapshots and images
- `archive/`: retired configuration kept only for provenance
- `upstream/`: review notes for pinned vendor dependencies

Do not copy credentials or machine-local settings from historical evidence into
source code. Use the ignored `config/nero.local.env` file instead.
