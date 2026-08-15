# S14 Left LinkerHand L6 CAN Bring-Up Plan

Date: 2026-06-30

## Correction From Live Device Evidence

The left hand was initially described as connected through a computer serial
path. The live host evidence corrects that interpretation:

- `ls -l /dev/serial/by-id/` produced no device.
- `ls -l /dev/ttyUSB* /dev/ttyACM*` produced no device.
- `dmesg` showed a PEAK-System PCAN-USB adapter:
  - USB product: `XCAN-USB`;
  - USB ID: `0c72:000c`;
  - driver: `peak_usb`;
  - attached SocketCAN interface: `can1`;
  - USB bus path after the USB-C hub: `1-3.4.4:1.0`.

Therefore the active left-hand bench branch is CAN over SocketCAN, not
RS485/Modbus. The earlier RS485 plan is superseded unless a real `/dev/ttyUSB*`
or `/dev/ttyACM*` serial adapter appears later.

## Current Evidence

- The selected hand is the left LinkerHand L6.
- The hand is disconnected from NERO arm/J6.
- Bench photo:
  `docs/evidence/pics/灵巧手连接设备/灵巧手左手上电操控示意图.jpeg`.
- The photo shows about `24.00 V` and `0.122 A` on the WANPTEK supply.
- The host sees the hand debug adapter as SocketCAN `can1`.
- Existing NERO arm CAN names remain `can_arm_a` and `can_arm_b`; do not probe
  those with LinkerHand frames.

## Interface Facts

From `upstream/linkerhand_wrapper`:

- LinkerHand L6 native CAN bitrate: `1000000`.
- Left hand CAN ID: `0x28`.
- Right hand CAN ID: `0x27`.
- L6 read request frames use the hand CAN ID and a one-byte command.
- Responses are accepted by the SDK from the hand ID or hand ID plus `8`, so the
  left hand should respond on `0x28` or `0x30`.
- Motion commands use the same frame type with six payload values. First
  bring-up must avoid those payload commands.

Read-only request frame set for the left hand:

| Request | Meaning |
| --- | --- |
| `028#64` | version query |
| `028#C0` | serial query |
| `028#33` | motor temperature query |
| `028#35` | motor fault query |
| `028#36` | current query |

Do not send six-byte position, speed, or torque payloads before S14.8.

Live correction after S14.6C:

- The first version of the project probe also sent `028#01` and `028#02`.
- The operator observed the hand physically opening during that probe.
- Therefore `0x01` is no longer treated as safe read-only in this process, even
  though the SDK names it as a current-state request when sent without payload.
- `0x02` is also excluded from the default safe probe because it shares the frame
  type used by torque-limit writes when payload is present.
- The default probe is now identity/health-only: `0x64`, `0xC0`, `0x33`, `0x35`,
  and `0x36`.

## S14.5C CAN Interface Baseline

Goal: make the hand CAN interface deterministic and avoid collisions with arm
CAN interfaces.

Recommended live checks:

```bash
ip -br link show type can
ethtool -i can1
ip -details link show can1
```

If `can1` is DOWN, activate it:

```bash
sudo ip link set can1 up type can bitrate 1000000
```

Preferred stabilization after first proof:

- Rename the hand interface to a stable project name such as `can_hand_left`.
- Record USB bus-info `1-3.4.4:1.0`.
- Keep the hand CAN interface separate from `can_arm_a` and `can_arm_b`.

Acceptance:

- Hand interface exists and is UP at `1000000`.
- Driver is `peak_usb`.
- No LinkerHand frame is sent on `can_arm_a` or `can_arm_b`.

## S14.6C CAN Read-Only Probe

Goal: prove LinkerHand identity and health without motion.

Run the project read-only probe:

```bash
bash scripts/s14_linkerhand_l6_can_readonly_probe.sh can1 left
```

The script sends only one-byte read requests and captures responses.

Acceptance:

- Responses appear on `0x28` or `0x30`.
- Version or serial response appears.
- Temperature response `0x33` returns plausible values.
- Fault response `0x35` returns all zero values.
- Supply current remains stable around idle.
- No physical hand motion occurs during the revised identity/health-only probe.

Stop conditions:

- No response after confirming `can1` is UP at `1000000`.
- Any nonzero fault code.
- Current rises unexpectedly, or the hand heats, twitches, or makes abnormal
  noise during read-only queries.
- Any physical hand motion occurs during a probe that is expected to be
  identity/health-only.

## S14.7C Optional Tactile Read-Only Probe

Only after S14.6C is accepted, query the tactile/matrix frames. This is optional
before first motion and should be kept separate from the identity/health gate.

## S14.8C First Micro Motion

Goal: prove one actuator can track a small command and return.

Safety gate:

- S14.6C accepted.
- No object is in or near the hand.
- Left hand is the only hand on the bench control path.
- Power supply is still `24 V`; current is stable.
- A human is ready to cut power.
- The motion plan explicitly accounts for the S14.6C observation that `0x01`
  can cause hand motion on this device.

SDK-first policy after S14.6C:

- Prefer the local tuned repository `upstream/linkerhand_wrapper` over manual CAN
  guessing.
- Do not run the SDK demos directly for first motion. `test_hand.py`,
  `gestures.py`, `diagnose.py`, `dual_gui.py`, and the high-level wrapper
  context manager can send large or implicit hand motions.
- Do not call SDK `get_state()` or `get_torque()` during the first-motion gate,
  because those map to frame types that were involved in the S14.6C physical
  opening event.
- Use project-local safety wrappers that import the SDK API and preset table,
  but expose dry-run and explicit `--execute` gates.

Current SDK health gate:

```bash
.venv/nero-sdk/bin/python scripts/s14_linkerhand_l6_sdk_health.py \
  --can can1 \
  --side left
```

Live S14 SDK health result:

- Accepted on 2026-06-30; see
  `docs/results/s14_left_hand_sdk_health_result_20260630.md`.
- SDK version `3.1.0` connected to `can1` over SocketCAN.
- Embedded version `[2, 3, 7]`.
- Serial `LHL6-03-253-L-B-1-C`.
- Three fault samples were all `[0, 0, 0, 0, 0, 0]`.
- Temperature samples were stable at `[36, 37, 36, 36, 36, 36]`.

Recommended first motion sequence:

1. Confirm SDK health: identity, temperature, current, and all-zero faults.
   This is complete for the left hand.
2. Send only the SDK `open` preset once as an anchor pose:

   ```bash
   .venv/nero-sdk/bin/python scripts/s14_linkerhand_l6_sdk_motion_gate.py \
     --can can1 \
     --side left \
     --mode open-anchor
   ```

   Add `--execute` only after the dry-run is reviewed.
   The dry-run was accepted on 2026-06-30; see
   `docs/results/s14_left_hand_open_anchor_dry_run_result_20260630.md`.

   Next authorized command:

   ```bash
   .venv/nero-sdk/bin/python scripts/s14_linkerhand_l6_sdk_motion_gate.py \
     --execute \
     --can can1 \
     --side left \
     --mode open-anchor
   ```
3. If the open-anchor command is accepted, run a small index micro-motion:

   The open-anchor execute gate was accepted from SDK/software health on
   2026-06-30; see
   `docs/results/s14_left_hand_open_anchor_execute_result_20260630.md`. The operator
   should still confirm physical observation and bench supply stability before
   any index-micro execute.

   ```bash
   .venv/nero-sdk/bin/python scripts/s14_linkerhand_l6_sdk_motion_gate.py \
     --can can1 \
     --side left \
     --mode index-micro \
     --joint index \
     --delta -10 \
     --speed 30
   ```

4. Monitor supply voltage/current and physical motion throughout. Stop on any
   unexpected jump, heat, noise, nonzero fault, or motion inconsistent with the
   printed target pose.

Live S14 index-micro result:

- Accepted from SDK/software health on 2026-06-30; see
  `docs/results/s14_left_hand_index_micro_result_20260630.md`.
- Dry-run target was `[255, 179, 245, 255, 255, 255]`, changing only `index`
  from `255` to `245`.
- Execute sent target then returned to `[255, 179, 255, 255, 255, 255]`.
- Pre/post fault values were all zero.
- Temperature and current raw values stayed stable.
- Operator physical observation was normal and matched expectation.
- This closes the left-hand first-motion baseline. Next branch is right-hand
  reproduction under `docs/phases/s14_right_hand_reproduction_plan.md`.

Do not use `test_hand.py`, `gestures.py`, `dual_gui.py`, or SDK demo scripts for
the first motion.

## S14.9C Right Hand Reproduction

After the left hand passes:

1. Power down and disconnect the left hand.
2. Connect the right hand with the same bench wiring discipline.
3. Use right hand CAN ID `0x27`.
4. Repeat the CAN interface, read-only, and first micro-motion gates.
