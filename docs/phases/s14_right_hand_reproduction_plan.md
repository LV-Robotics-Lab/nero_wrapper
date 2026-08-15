# S14 Right LinkerHand L6 Reproduction Plan

Date: 2026-06-30

## Goal

Repeat the accepted left-hand independent CAN bench-test process on the right
LinkerHand L6. The field setup has been corrected: the left and right hands now
each have their own CAN cable connected to the USB-C adapter path, so the
workflow first fixes physical USB/CAN positions and validates which SocketCAN
interface belongs to each hand.

This plan does not authorize bimanual or synchronized hand control. Synchronized
control starts only after the right hand passes the same health, open-anchor,
and index-micro gates.

## Preconditions

- Left hand first-motion baseline is accepted:
  `docs/results/s14_left_hand_index_micro_result_20260630.md`.
- Power supply can be cut immediately.
- Both hand CAN cables are separate from `can_arm_a` and `can_arm_b`.
- The right hand is disconnected from NERO J6 before bench testing.
- Bench wiring follows the same reviewed LinkerHand L6 XT30(2+2) CAN/power
  discipline used for the left hand.
- SocketCAN interface names must be verified by SDK identity/health, not by
  physical guesswork.
- The hand is empty and clear of tools, cables, and fingers.

Expected right-hand facts from `upstream/linkerhand_wrapper`:

- Side: `right`
- CAN ID: `0x27`
- Expected serial: `LHL6-03-240-R-B-1-C`
- SDK open preset: `[255, 70, 255, 255, 255, 255]`
- Index micro target with `delta=-10`: `[255, 70, 245, 255, 255, 255]`

Live CAN inventory result:

- Recorded in `docs/results/s14_hand_can_inventory_result_20260630.md`.
- `can1` is the accepted left-hand interface, driver `peak_usb`, bus-info
  `1-3.4.4:1.0`.
- `can2` is the right-hand candidate, driver `peak_usb`, bus-info `1-3.4.2:1.0`.
- `can2` was DOWN during inventory and must be activated before right-hand SDK
  health.

## S14.9R.0 Fix Hand CAN Positions

1. Keep the left and right hand CAN cables in their intended USB-C adapter
   positions.
2. Label or photograph the physical positions before running commands.
3. Confirm no hand CAN cable is connected to `can_arm_a` or `can_arm_b`.
4. Inventory CAN interfaces:

   ```bash
   bash scripts/s14_hand_can_inventory.sh
   ```

5. If both hand interfaces are temporary names such as `can0`/`can1`, record
   each interface's `bus_info` and physical USB position.
6. Prefer stable names after identity is verified:
   `can_hand_left` and `can_hand_right`.

Acceptance:

- Two non-arm hand CAN candidates are visible.
- Their driver and `bus_info` are recorded.
- NERO arm CAN interfaces are not used for hand tests.

For the current right-hand candidate, activate `can2` at 1 Mbps before SDK
health:

```bash
sudo ip link set can2 up type can bitrate 1000000
```

## S14.9R.1 SDK Health

Current right-hand candidate interface: `can2`.

```bash
.venv/nero-sdk/bin/python scripts/s14_linkerhand_l6_sdk_health.py \
  --can can2 \
  --side right
```

Acceptance:

- SDK connects to the selected right-hand interface.
- Serial matches right hand, expected `LHL6-03-240-R-B-1-C`.
- Embedded version is readable.
- Fault samples are all zero.
- Temperature and current raw values are stable.
- No physical motion occurs.

Live result:

- Accepted on 2026-06-30; see
  `docs/results/s14_right_hand_sdk_health_result_20260630.md`.
- `can2` is UP/ERROR-ACTIVE at `1000000`.
- SDK identified hand ID `0x27`, serial `LHL6-03-240-R-B-1-C`, embedded version
  `[2, 3, 7]`.
- Three fault samples were all zero.
- Temperature/current raw values were stable.

## S14.9R.2 Open-Anchor Dry Run

```bash
.venv/nero-sdk/bin/python scripts/s14_linkerhand_l6_sdk_motion_gate.py \
  --can can2 \
  --side right \
  --mode open-anchor
```

Acceptance:

- `execute=False`.
- `base_pose=[255, 70, 255, 255, 255, 255]`.
- `sequence=send_base_pose_once`.
- No SDK motion command is sent.

## S14.9R.3 Open-Anchor Execute

```bash
.venv/nero-sdk/bin/python scripts/s14_linkerhand_l6_sdk_motion_gate.py \
  --execute \
  --can can2 \
  --side right \
  --mode open-anchor
```

Acceptance:

- Pre/post fault values are all zero.
- Temperature and current raw values are stable.
- Physical behavior is no motion or only a small open-pose correction.
- No abnormal bench supply behavior.

Live result:

- Accepted from SDK/software health on 2026-06-30; see
  `docs/results/s14_right_hand_open_anchor_result_20260630.md`.
- Operator observed thumb, middle, ring, and pinky motion.
- Operator did not observe visible index motion.
- The missing index visible motion is not yet a confirmed fault because the
  open-anchor target for index is already `255`, but it must be resolved by the
  next index-micro gate before synchronized control.

## S14.9R.4 Index-Micro Dry Run

```bash
.venv/nero-sdk/bin/python scripts/s14_linkerhand_l6_sdk_motion_gate.py \
  --can can2 \
  --side right \
  --mode index-micro \
  --joint index \
  --delta -10 \
  --speed 30
```

Acceptance:

- `execute=False`.
- Base pose is `[255, 70, 255, 255, 255, 255]`.
- Target pose is `[255, 70, 245, 255, 255, 255]`.
- Sequence is target, then return to base.

## S14.9R.5 Index-Micro Execute

```bash
.venv/nero-sdk/bin/python scripts/s14_linkerhand_l6_sdk_motion_gate.py \
  --execute \
  --can can2 \
  --side right \
  --mode index-micro \
  --joint index \
  --delta -10 \
  --speed 30
```

Acceptance:

- The right index finger makes a small expected motion and returns to open.
- Faults remain all zero before and after.
- Temperature/current remain stable.
- Bench supply remains near 24 V without abnormal current jump.

Live result:

- Accepted from SDK/software health on 2026-06-30; see
  `docs/results/s14_right_hand_index_micro_result_20260630.md`.
- Dry-run and execute both used target pose `[255, 70, 245, 255, 255, 255]`,
  changing only right index raw value `255 -> 245`, then returning to open.
- Pre/post fault values were all zero and temperature/current raw values were
  stable.
- Physical observation is still pending. Synchronized control remains blocked
  until the right index visible response is confirmed or diagnosed.

## After Right-Hand Acceptance

The next stage is synchronized control planning:

- Bring both hands to a known open preset independently.
- Decide whether synchronization is sequential dual-command through one CAN bus
  or true dual-adapter simultaneous control.
- Prefer two separate CAN adapters for real synchronization; one adapter can
  only send commands serially on one bus.
- Start with dry-run pose planning for both hands before any synchronized
  execute.
