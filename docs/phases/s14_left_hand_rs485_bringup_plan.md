# S14 Left LinkerHand L6 RS485 Bring-Up Plan

Date: 2026-06-30

Status: Superseded by live CAN device evidence on 2026-06-30.

The operator's live checks showed no `/dev/serial/by-id/`, `/dev/ttyUSB*`, or
`/dev/ttyACM*` device. The USB-C hub instead exposed a PEAK-System PCAN-USB
adapter as SocketCAN `can1`. Continue with
`docs/phases/s14_left_hand_can_bringup_plan.md` unless a real serial/RS485 adapter is
connected later.

## Current Evidence

- The selected hand is the left LinkerHand L6.
- The hand has been disconnected from the NERO arm/J6 end-effector cable.
- New bench photo:
  `docs/evidence/pics/灵巧手连接设备/灵巧手左手上电操控示意图.jpeg`.
- The photo shows the WANPTEK supply at about `24.00 V` and `0.122 A`.
- This idle current is plausible against the L6 manual's static-current value
  of about `0.2 A`.
- The operator reports that the hand is connected to the computer through a
  serial path. Treat this as the LinkerHand SDK's RS485/Modbus path unless later
  evidence proves it is actually SocketCAN.

## Priority

The priority is to validate one hand independently without disturbing the
accepted dual-arm NERO baseline.

1. Keep the hand electrically isolated from NERO J6.
2. Establish a reproducible hand-only communication path.
3. Run read-only identity and health checks before any motion.
4. Permit only one small, reversible, single-joint motion after read-only data is
   accepted.
5. Record all results before reproducing the process on the other hand.

## Documented Interface Facts

From the LinkerHand SDK and L6 documents:

- Model: LinkerHand `L6`.
- Working power: `DC24V +/- 10%`.
- Current reference: static about `0.2 A`, no-load average about `0.75 A`,
  maximum about `1.4 A`.
- L6 communication options: CAN or RS485/Modbus.
- RS485 support exists in
  `upstream/linkerhand_wrapper/LinkerHand/core/rs485/linker_hand_l6_rs485.py`.
- RS485 serial parameters in the SDK:
  - `115200` baud;
  - `8N1`;
  - timeout `0.05 s`.
- Hand IDs in `LinkerHandApi`:
  - left hand: `0x28`;
  - right hand: `0x27`.
- The SDK config says RS485 ports usually appear as `/dev/ttyUSB*` or
  `/dev/ttyACM*`.
- In the SDK, setting `MODBUS` to a device path disables the CAN path for that
  hand.

Do not run the SDK motion demos as-is. The demo and convenience scripts contain
large open/fist/gesture commands.

## S14.5 Bench Electrical And Serial Baseline

Goal: prove the physical setup is safe enough for read-only software access.

Operator checks:

1. Confirm the left hand is still disconnected from NERO J6.
2. Confirm no bare conductor remains near the supply, serial adapter, CAN
   terminals, or the hand cable.
3. Confirm supply output is about `24 V`.
4. Confirm idle current is stable and roughly in the expected low-current range.
   The current photo shows about `0.122 A`, which is acceptable as an initial
   observation.
5. Confirm the hand is not heating, buzzing, twitching, or mechanically loaded.
6. Identify the serial device:

```bash
ls -l /dev/serial/by-id/ 2>/dev/null
ls -l /dev/ttyUSB* /dev/ttyACM* 2>/dev/null
dmesg -T | tail -n 40
```

Acceptance:

- One candidate serial device is identified.
- The device identity is recorded, preferably `/dev/serial/by-id/...` instead
  of only `/dev/ttyUSB0`.
- No motion command has been sent.

## S14.6 RS485 Read-Only Probe

Goal: read identity and health data through RS485 without commanding motion.

Use left-hand ID `0x28` and the detected port. The first probe should read:

- version registers;
- joint angles;
- torques;
- speeds;
- temperatures;
- error/fault codes.

Acceptance:

- The port opens at `115200 8N1`.
- The SDK returns six values for angles, torques, speeds, temperatures, and
  faults.
- Fault values are all `0`.
- Temperatures are plausible and stable.
- Three repeated samples are consistent.
- Bench supply current remains stable during reads.

Stop conditions:

- Serial connection fails repeatedly on both `/dev/ttyUSB*` and
  `/dev/serial/by-id/...`.
- Any fault code is nonzero.
- Idle current rises unexpectedly, the hand heats, twitches, or makes abnormal
  sound.

## S14.7 Optional Pressure Read-Only Probe

Goal: verify tactile/matrix data only after S14.6 passes.

The SDK can read matrix pressure data through the RS485 class. This should be
treated as optional because it reads many registers and is not required before
first motion.

Acceptance:

- Pressure reads complete without Modbus errors.
- Data shape is recorded for each finger.
- No finger motion is commanded.

## S14.8 First Micro Motion

Goal: prove one left-hand actuator can track a small command and return.

Safety gate before motion:

- S14.6 accepted.
- Supply output is still `24 V`.
- No object is in or near the hand.
- A human is ready to cut power.
- Only the left hand is connected.

Recommended motion strategy:

1. Read the current six joint values.
2. Set conservative speed and torque, for example low values in the `0..255`
   SDK range.
3. Choose one visible non-thumb joint first, preferably index flexion
   `joint index 2`.
4. Move by a small raw-value delta, for example `10`.
5. Read state and fault immediately after motion.
6. Return to the original six joint values.
7. Read state, fault, temperature, and supply current again.

Acceptance:

- Only the selected finger visibly moves.
- The reported joint state changes in the expected direction.
- The hand returns close to the original joint state.
- Fault codes stay `0`.
- Supply current stays below the L6 manual maximum and does not show a stall
  signature.

Stop conditions:

- Unexpected multi-finger motion.
- Any finger binds or continues moving after command.
- Fault code appears.
- Current spikes or stays high.
- Temperature rises quickly.

## S14.9 Reproduce On The Right Hand

After the left-hand branch passes:

1. Power down.
2. Disconnect the left hand from the bench setup.
3. Connect the right hand with the same wiring discipline.
4. Use right-hand ID `0x27`.
5. Repeat S14.5 through S14.8.

## S14.10 Reintegration Decision

After both hands pass independent bench tests, decide how they return to the
dual-arm robot:

- If vendor confirms NERO J6 supports LinkerHand L6 directly, reconnect through
  J6 and run a J6 read-only and tiny-motion gate.
- If NERO J6 does not support the L6 path, keep hands on an independent
  LinkerHand control bus and integrate at the application layer with explicit
  ownership between arm motion and hand motion.

No dual-arm manipulation experiment should depend on the hands until the chosen
reintegration path has its own read-only, first-motion, and stop-recovery gates.
