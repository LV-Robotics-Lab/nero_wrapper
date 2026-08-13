# DataMaster integration split — NERO-owned migration

Source audited on 2026-08-13:

```text
/home/lvrobotics/workspace/Nero_TacClaw_DataMaster/
  src/nero_datamaster_teleop/nero_datamaster_teleop/payload_protocol.py
```

The source integration root was not a valid Git repository. Its frozen file checksum is recorded by `datamaster_wrapper/docs/migration/source_manifest.sha256`.

Migrated in this step:

- Exact NERO V1.2.1 payload level bytes for CAN command `0x477`.
- Linux classic-CAN frame packing and strict unpacking.
- Payload-setting ACK recognition on `0x476` instruction `0x77`.
- Ordered NERO joint names and seven hardware joint-limit intervals, exposed
  independently so retargeting code does not duplicate robot-owned constants.
- Explicit-path dual-NERO URDF composition, TCP attachment and collision-pair
  generation. The old host-specific absolute URDF default was removed.
- Optional payload-only gravity compensation with absolute torque clipping and
  per-cycle slew limiting. Pinocchio is lazy and the algorithm is fake-backend tested.
- The optional cuRobo dual-arm backend, packaged collision spheres and its
  hardware-independent step/collision-escape tests. CUDA/curobo are checked only
  when the backend is explicitly constructed.
- The optional Placo dual-NERO backend with explicit URDF input and the shared
  prefixed dual model. Importing the module does not construct a solver.

Remote read-only model smoke on the NERO host loaded the official URDF, built
both prefixed arms, synchronized fourteen zero joint values and returned finite
4x4 TCP transforms for both arms. Placo printed its pre-filter neutral-model
adjacent-link warning for link5/link6 on each arm; this smoke is therefore model
loading evidence, not a collision-free or motion acceptance claim.

The module is a pure codec and opens no CAN interface. The ROS2 payload configuration node and gravity compensation path remain outside the package until their driver lifecycle, robot model assets and real-hardware safety gates are migrated independently.
