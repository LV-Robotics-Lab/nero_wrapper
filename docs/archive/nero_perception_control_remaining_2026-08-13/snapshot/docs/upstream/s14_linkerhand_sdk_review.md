# S14 LinkerHand SDK Review

Date: 2026-06-29

Source path: `upstream/linkerhand_sdk/`

Source origin:

- User-provided local download from
  `https://github.com/LV-Robotics-Lab/linkerhand_sdk`.
- The local copy was provided as a downloaded source tree, not a git clone, so
  no upstream commit hash is available locally.
- The directory is kept under `upstream/`, which is ignored by this project git
  repository.

## What This Repository Is

`linkerhand_sdk` is a Linker Hand Python SDK working copy configured for a dual
Linker Hand L6 setup. It wraps the upstream Linker Hand SDK and adds local
high-level tools for a left/right hand pair.

Important repository facts from its README and source:

- Hand model: Linker Hand `L6`.
- Left hand:
  - default SocketCAN: `can0`;
  - serial: `LHL6-03-253-L-B-1-C`;
  - firmware: `2.3.7`.
- Right hand:
  - default SocketCAN: `can1`;
  - serial: `LHL6-03-240-R-B-1-C`;
  - firmware: `2.3.7`.
- Hardware expected by the local README:
  - 2x PEAK PCAN-USB adapters, `lsusb` ID `0c72:000c`;
  - one XT30 2+2 connector per hand: `VCC / GND / CAN_H / CAN_L`;
  - CAN bitrate `1000000`;
  - power `24 V +/- 10%`.
- Python SDK version in `LinkerHand/config/setting.yaml`: `3.1.0`.
- Upstream README_CN says the Python SDK supports Ubuntu 20.04+ and Python
  3.8+.

## Functions Provided

High-level local wrapper: `linker_hand_l6.py`

- `LinkerHandL6.left(can="can0")`
- `LinkerHandL6.right(can="can1")`
- `BimanualL6.auto(left_can="can0", right_can="can1")`
- per-hand commands:
  - `set_pose([0..255] * 6)`;
  - `set_finger(index, value)`;
  - presets: `open`, `fist`, `thumb_up`, `ok`, `point`, `two`, `three`,
    `four`, `five`;
  - `set_speed([0..255] * 6)`;
  - `set_torque([0..255] * 6)`.
- read APIs:
  - `get_state()`;
  - `get_current()`;
  - `get_torque()`;
  - `get_temperature()`;
  - `get_fault()`;
  - `get_serial_number()`.

The L6 joint value order is:

1. `thumb_flex`
2. `thumb_abduct`
3. `index`
4. `middle`
5. `ring`
6. `pinky`

All L6 pose values are integer ranges `0..255`.

The local wrapper uses side-specific gesture values. In particular,
`thumb_abduct` differs between left and right. For example:

- left open: `[255, 179, 255, 255, 255, 255]`;
- right open: `[255, 70, 255, 255, 255, 255]`.

This matters because identical raw values are not necessarily anatomically
mirrored across both hands.

Utility scripts:

- `find_linker_hand.sh`: scans CAN interfaces by sending `0FF#C0`; expected
  response ID `0x28` means left hand and `0x27` means right hand.
- `find_can.sh`: reports CAN interface USB bus-info through `ethtool`.
- `test_hand.py`: open -> half -> open motion cycle for left/right/both.
- `gestures.py`: runs a gesture sequence.
- `diagnose.py`: reads state/current/torque/temperature/fault and commands
  diagnostic motions.
- `dual_gui.py`: GUI for both hands.

## CAN Protocol Implications

This repository does not use the AgileX Revo2 ROS topic/status path as the
primary interface. It communicates with the hand directly through LinkerHand CAN
frames.

Source findings from `LinkerHand/core/can/linker_hand_l6_can.py`:

- left hand CAN ID: `0x28`;
- right hand CAN ID: `0x27`;
- responses are accepted on `can_id` and `can_id + 8`;
- frame byte `0x01`: joint position/status;
- frame byte `0x02`: torque limit;
- frame byte `0x05`: speed;
- frame byte `0x33`: motor temperature;
- frame byte `0x35`: motor fault code;
- frame byte `0x36`: current;
- frame byte `0xC0`: serial number;
- frame byte `0x64` / `0xC2`: version.

This is incompatible with the previous AgileX Revo2 assumption that status would
arrive through `/arm_*/feedback/hand_status` using Revo2 feedback IDs such as
`0x1C0`/`0x1C1`.

## Impact On NERO S14

S14 hand work must be reoriented:

- The installed hands should be treated as LinkerHand L6 devices unless later
  evidence proves otherwise.
- AgileX `effector_type:=revo2` is no longer the preferred hand-side software
  path for these installed hands.
- The previous result where ROS Revo2 endpoints appeared but
  `/feedback/hand_status` produced no messages is explained by a likely
  protocol/device mismatch, not by a normal Revo2 no-command feedback behavior.
- Do not publish to AgileX ROS `/control/hand` or
  `/control/hand_position_time` for these hands.
- The next S14 gate should be LinkerHand CAN identification and read-only status,
  not Revo2 ROS `hand_status`.

Current physical mapping to reconcile:

- NERO Arm A has the right hand.
- NERO Arm B has the left hand.
- LinkerHand SDK defaults:
  - left hand on `can0`;
  - right hand on `can1`.

Therefore the expected logical mapping is likely:

- Arm A hand = right LinkerHand L6 = SDK `hand_type="right"`;
- Arm B hand = left LinkerHand L6 = SDK `hand_type="left"`.

Correction on 2026-06-30:

- The SDK README describes the previous bench/debug setup, where LinkerHand L6
  devices were controlled directly from the computer through PEAK PCAN-USB
  adapters.
- The current robot installation is different: the hand cable is connected to
  the NERO arm J6 end-effector port through the accessory power/communication
  cable.
- Therefore the live system should not be expected to expose a separate
  `can0`/`can1` hand interface on the computer.
- The LinkerHand direct-CAN scripts remain useful protocol evidence, but they
  are not the immediate control path for the installed robot unless the hand is
  disconnected from J6 and placed back on a direct bench-test CAN adapter.

The actual J6-integrated hand communication path must be verified through the
NERO controller/Web/arm-CAN evidence before any command or read probe.

## Safety Notes

- The SDK can auto-open CAN interfaces using `sudo` and the password stored in
  `LinkerHand/config/setting.yaml`. Do not rely on that behavior for the NERO
  bring-up path; activate CAN interfaces explicitly through our existing
  controlled scripts.
- `find_linker_hand.sh` scans all CAN interfaces and sends `0FF#C0`. Do not run
  it blindly while arm CAN interfaces are also UP. Prefer a targeted version
  against known hand CAN interfaces only.
- `test_hand.py`, `gestures.py`, and `diagnose.py` publish finger motion
  commands. They are not read-only and are not accepted for S14.3.
- First LinkerHand read-only checks may still send request frames such as
  `0x01`, `0x33`, `0x35`, `0x36`, and `0xC0`. Treat those as read/status
  request frames, not motion commands, but run them only after the hand CAN bus
  is identified.

## Recommended Next Gate

S14.3 should be replaced by `S14.3L LinkerHand read-only identification`:

1. Stop any AgileX Revo2 driver terminal used for hand tests.
2. Verify the physical J6 hand cable, orientation, and seating on the selected
   arm and hand.
3. Verify Web end-effector configuration and the Web hand page in read-only or
   enable-only mode, without changing finger positions.
4. Check arm external CAN only passively. Do not expect direct LinkerHand
   `0x27`/`0x28` frames unless NERO forwards end-effector CAN to the external
   bus.
5. Accept the J6-integrated read-only path only if Web/controller evidence can
   identify the hand or report a healthy hand status. If direct LinkerHand
   serials are exposed, they should match:
   - left: `LHL6-03-253-L-B-1-C`;
   - right: `LHL6-03-240-R-B-1-C`;
   and fault values are normal.

No finger movement is authorized by this review.

## 2026-06-30 Linker Drive Update

A newer Drive document set was moved to the sibling data-collection workspace and reviewed in
`../data-collection/docs/reviews/linker_drive_20260630_review.md`.

Additional conclusions:

- The newer documents confirm the hand-side device class as LinkerHand L6:
  CAN/RS485, 24 V, direct SDK values `0..255`, right hand ID `0x27`, left hand
  ID `0x28`.
- They also introduce a separate Linker/LBOT robot controller stack with
  default controller IP `192.168.10.21` and Web platform
  `http://192.168.10.21:8000`.
- Because our accepted NERO path currently uses direct host USB-CAN arm
  interfaces and NERO Web at `http://192.168.31.1/#/welcome`, the next
  highest-value check is whether that `192.168.10.21` controller exists on the
  actual machine.

This supersedes the previous Revo2-first next gate. The next live S14 check is
`S14.3K Linker/LBOT read-only controller probe`. Do not run vendor demo motion
scripts.
