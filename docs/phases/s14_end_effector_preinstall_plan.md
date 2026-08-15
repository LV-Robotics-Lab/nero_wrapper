# S14 End-Effector Installation Plan

Status: S14.3K Linker/LBOT read-only controller probe pending; LinkerHand L6 is now the hand fact source, and AgileX Revo2 is no longer the preferred first diagnostic path.

S14 starts after S13 closed the bare-arm low-risk dual-arm primitive. Installing
the dexterous hands changes mass, TCP, cable routing, collision envelope, and
model/driver parameters. Do not reuse S13 bare-arm assumptions without
revalidation.

## Current Field State

Reported on 2026-06-29:

- Both dexterous hands are mechanically installed.
- Selected hand mapping:
  - Arm A: right dexterous hand.
  - Arm B: left dexterous hand.
- Cable routing constrains wrist motion, especially around J6 and J7.
- Operator reports the cable does not interfere when bends stay below about
  `70 deg`; larger wrist bends may pull or over-bend the cable.

The `70 deg` limit is a cable-bend observation, not a verified joint-angle
limit. Treat it as a field safety constraint until measured against actual
joint poses.

Actual S14.0 result on 2026-06-29:

- Operator archived cable photos:
  - `docs/evidence/pics/S14自然状态线束.jpeg`.
  - `docs/evidence/pics/S14手腕弯折状态线束.jpeg`.
- Left/right hand mapping is confirmed:
  - Arm A: right dexterous hand.
  - Arm B: left dexterous hand.
- Both hands are mechanically stable after installation.
- Cable routing still constrains J6/J7, but the operator reports no interference
  as long as wrist/cable bending does not exceed about `70 deg`.

S14.0 is accepted within this temporary cable boundary. It does not authorize
finger actuation, Web hand controls, or large J6/J7 wrist motion.

## Documented Installation Facts

From the NERO user manual and local images:

- Dexterous hand installation uses the flange path.
- The hand cable outlet should align with the flange notch center.
- The hand is fixed to the flange with four `M3x6` screws.
- The accessory power/communication cable connects to the J6 end connector.
- The end connector reference is `docs/evidence/pics/2.1.2末端连接电器说明.png`.
- The hand size and flange references are:
  - `docs/evidence/pics/4 灵巧手示意图.png`.
  - `docs/evidence/pics/5 灵巧手法兰安装示意图.png`.

From upstream ROS/SDK code:

- ROS launch supports `effector_type:=revo2`.
- NERO model variants include left/right Revo2 hand xacro files.
- The control package exposes `/feedback/hand_status`, `/control/hand`, and
  `/control/hand_position_time`.
- The SDK exposes Revo2 status and position/speed/current/time control APIs.

These capabilities are evidence that the software path exists. They do not
authorize motion before S14 gates are accepted.

## Immediate Gates

### S14.0 Mechanical And Cable Review

Accept only if:

- Left/right hand mapping is physically confirmed: Arm A right hand, Arm B left
  hand.
- All flange screws are present and tightened after orientation check.
- Cable exits are aligned with flange notches.
- Cable slack is checked across the current parked posture.
- J6/J7 cable risk is documented with photos or operator notes.
- No commanded wrist motion exceeds the cable-safe envelope.

Temporary cable rule:

- Do not command J6/J7 large wrist motions in S14.0/S14.1.
- Do not exceed the observed about `70 deg` cable-bend envelope.
- Prefer no wrist motion until a visual cable-clearance test plan is written.

### S14.1 No-Motion Read-Only Verification

Goal:
Confirm the arm controllers remain healthy after hand installation before any
finger or wrist motion.

Accept only if:

- Only one ROS feedback publisher exists per arm feedback topic.
- A/B arm status has `err_status: 0`.
- A/B joint-limit and joint-communication flags are all `false`.
- No dexterous-hand control topic is published by the test.
- No Web dexterous-hand action is used.

Actual S14.1 result on 2026-06-29:

- Operator confirmed ROS publisher count:
  - `/arm_a/feedback/joint_states`: `Publisher count: 1`.
  - `/arm_b/feedback/joint_states`: `Publisher count: 1`.
- Snapshot: `docs/evidence/ros_snapshots/20260629_074337/`.
- `Failed capture commands: 0`.
- Arm A joint-state feedback: about `200 Hz`.
- Arm B joint-state feedback: about `200 Hz`.
- A/B `err_status: 0`.
- A/B joint-limit flags: all `false`.
- A/B joint-communication flags: all `false`.
- A/B `arm_status=3`; upstream documentation maps this value to `奇异点`
  / `SINGULARITY_POINT`.
- A/B `motion_status=1`; upstream documentation maps this value to not reached
  target.
- The topic list still only contains arm feedback/control topics because this
  snapshot used the normal read-only launch with `effector_type:=none`.

Result:

- S14.1 is accepted as arm-controller read-only communication evidence after
  mechanical hand installation.
- It is not accepted as a motion-ready posture. Before any wrist, Cartesian, or
  finger motion, S14 must either move to or explicitly accept a non-problematic
  posture under a separate gate.

### S14.2 Model And Parameter Decision

Decide before hand motion:

- Whether Web end-effector type is changed, and to what exact value.
- Whether ROS drivers use `effector_type:=revo2`.
- Which `revo2_type` is used for RViz/model per arm:
  - Arm A: `right`.
  - Arm B: `left`.
- Load mode and TCP offset after hand installation.
- Whether hand status is checked through ROS or SDK first.

Actual S14.2 decision on 2026-06-29:

- Keep the global/default arm-only ROS configuration as `effector_type:=none`.
  This preserves the already accepted S9-S13 arm-only regression path.
- For S14 hand read-only only, use a dedicated launch path with
  `effector_type:=revo2`.
- Use the current physical/model mapping:
  - Arm A: right Revo2 hand, model `revo2_type:=right` where a model launch
    needs that argument.
  - Arm B: left Revo2 hand, model `revo2_type:=left` where a model launch needs
    that argument.
- Do not use Web dexterous-hand controls yet.
- Do not publish ROS `/control/hand` or `/control/hand_position_time` yet.
- Keep TCP offset at zero for read-only checks. This is not a final manipulation
  TCP calibration.
- Keep the current load/TCP state out of motion acceptance until the hand mass,
  center of gravity, and TCP are measured or explicitly accepted.
- Because S14.1 observed A/B `arm_status=3` / singularity, do not start wrist,
  Cartesian, or finger motion from the current posture without a separate
  posture/safety gate.

### S14.3 Hand Read-Only

Goal:
Read hand status without finger motion.

Accept only if:

- Revo2/hand status topic or SDK status is present for the selected arm.
- Hand left/right flag matches the physical mapping where available.
- No motor blocked/over-current/over-temperature/error state is reported.
- Feedback frequency is stable enough to trust before motion.

First S14.3 attempt on 2026-06-29:

- Operator started the usual dual-arm read-only script with a host-side
  `NERO_EFFECTOR_TYPE=revo2` assignment.
- The ROS driver logs still printed `effector_type: none` for both arms.
- `ros2 topic list` contained no `hand` topics.
- Interpretation: this is not evidence of Revo2 hardware feedback failure. The
  host-side environment override was not passed into the Docker container, and
  the container-side script sourced `config/nero.env`, whose global default is
  still `NERO_EFFECTOR_TYPE="none"`.

Corrected S14.3 retry path:

- Use `scripts/launch_s14_dual_revo2_readonly.sh`.
- The corrected driver terminal must print `effector_type=revo2` in the script
  banner and `effector_type: revo2` in both driver logs.
- Expected topic evidence after startup:
  - `/arm_a/feedback/hand_status`
  - `/arm_b/feedback/hand_status`
  - `/arm_a/control/hand` and/or `/arm_a/control/hand_position_time` may appear
    as advertised control endpoints, but they must not be published to in
    S14.3.
  - `/arm_b/control/hand` and/or `/arm_b/control/hand_position_time` may appear
    as advertised control endpoints, but they must not be published to in
    S14.3.

Corrected S14.3 observation on 2026-06-29:

- The corrected Revo2 launch exposed the expected ROS endpoints:
  - `/arm_a/feedback/hand_status`
  - `/arm_b/feedback/hand_status`
  - `/arm_a/control/hand`
  - `/arm_a/control/hand_position_time`
  - `/arm_b/control/hand`
  - `/arm_b/control/hand_position_time`
- `ros2 topic echo --once /arm_a/feedback/hand_status` waited without output.

Interpretation:

- The ROS graph has switched into the Revo2 software path.
- A visible `hand_status` topic is not yet proof of physical hand feedback.
- Upstream code publishes `feedback/hand_status` only after the SDK has a
  non-empty `get_hand_status()` result.
- The upstream pyAgxArm Revo2 virtual CAN test models Revo2 feedback as a reply
  after host `0x1Bx` command frames, not as a proven periodic no-command
  stream. Therefore, no output from a strict no-command `echo --once` may mean
  either no passive feedback is expected, or that the physical hand feedback
  path is not yet active.

Next read-only probe:

- Use `scripts/s14_revo2_hand_status_probe.sh` instead of raw
  `ros2 topic echo --once` so the check has a bounded timeout and explicit
  result.
- Do not publish `/control/hand` or `/control/hand_position_time` until a
  separate S14.4 motion/safety gate is written and accepted.

### S14.3b LinkerHand SDK Source Review

New field information on 2026-06-29:

- The two installed hands were previously debugged with
  `https://github.com/LV-Robotics-Lab/linkerhand_wrapper`.
- This SDK should be treated as the preferred hand-side software reference once
  its source is available locally and reviewed.

Current access status:

- Initial direct clone was blocked because GitHub requested credentials.
- The operator downloaded the source tree manually.
- The local source is now stored at `upstream/linkerhand_wrapper/`.
- The local copy is a downloaded tree, not a git clone, so no commit hash is
  available locally.

Decision:

- Pause any attempt to solve the hand through AgileX `effector_type:=revo2`
  control commands.
- Do not publish to AgileX ROS `/control/hand` or
  `/control/hand_position_time` while LinkerHand source review is pending.
- Review result is recorded in `docs/upstream/s14_linkerhand_sdk_review.md`.

Key review findings:

- The installed hands should be treated as LinkerHand `L6` unless later evidence
  proves otherwise.
- The SDK expects direct CAN communication, not AgileX Revo2 ROS feedback:
  - left hand default CAN: `can0`;
  - right hand default CAN: `can1`;
  - CAN bitrate: `1000000`;
  - left hand CAN ID: `0x28`;
  - right hand CAN ID: `0x27`.
- Expected serials from the local README:
  - left: `LHL6-03-253-L-B-1-C`;
  - right: `LHL6-03-240-R-B-1-C`.
- LinkerHand L6 pose/state order is
  `[thumb_flex, thumb_abduct, index, middle, ring, pinky]`, each `0..255`.
- The local wrapper provides `get_state`, `get_current`, `get_torque`,
  `get_temperature`, `get_fault`, and `get_serial_number`.

Updated S14.3 decision:

- Replace the Revo2 hand-read-only gate with `S14.3L LinkerHand read-only
  identification`.
- Stop using AgileX Revo2 ROS `feedback/hand_status` as the primary evidence for
  these hands.
- Do not run `find_linker_hand.sh` blindly because it scans every CAN interface
  and sends `0FF#C0`; arm CAN interfaces may also be present.
- Identify actual hand CAN interfaces first, preferably using targeted
  interface checks against known hand CAN ports.
- Do not run `test_hand.py`, `gestures.py`, `diagnose.py`, or `dual_gui.py`
  before a separate S14.4 motion gate; those tools can command finger movement.

S14.3L is accepted only after LinkerHand read-only evidence records:

- detected left/right CAN interface mapping;
- serial numbers matching the expected left/right devices;
- firmware/version data;
- state/current/temperature/fault data;
- no active hand fault condition.

Field update on 2026-06-29:

- Operator reported the available hand-side cable has been connected.
- Next action is to identify the hand CAN interface without scanning arm CAN
  interfaces.
- Use `scripts/s14_linkerhand_identify_can.sh <can_iface>` for targeted
  LinkerHand identification after the candidate hand CAN interface is known and
  UP at `1000000` bitrate.
- The script refuses to run on `can_arm_a` or `can_arm_b` unless
  `--allow-arm-can` is explicitly supplied. Do not use that override before a
  documented bus review.

Correction on 2026-06-30:

- Operator clarified that the installed hands are not connected directly to the
  computer through USB-CAN/PCAN adapters. They are connected to the NERO arm
  through the J6 end-effector power/communication cable.
- The direct LinkerHand CAN path in `upstream/linkerhand_wrapper/` describes a
  previous bench/debug setup, not the current robot installation.
- Do not run `scripts/s14_linkerhand_identify_can.sh` on `can_arm_a` or
  `can_arm_b` for the current J6-integrated setup.

Observed evidence on 2026-06-30:

- `ip -br link show type can` shows only:
  - `can_arm_a` UP;
  - `can_arm_b` UP.
- Passive `candump -tz can_arm_a` showed normal NERO arm feedback frames such as
  `0x2A1`, `0x2A2`, `0x2A3`, `0x2A4`, and `0x261..0x267`.
- No direct LinkerHand-style `0x27`, `0x28`, `0x2F`, or `0x30` frames were
  observed in the provided sample.
- Operator can enable/control the arm in Web, but cannot enable/control the
  hand in Web.

Additional Web evidence on 2026-06-30:

- Screenshots:
  - `docs/evidence/pics/灵巧手01.png`
  - `docs/evidence/pics/灵巧手02.png`
- Web dexterous-hand page shows:
  - hand type: `普通灵巧手`;
  - vendor/model field: `revo2`;
  - mode: `位置控制`;
  - enable toggle appears active;
  - finger sliders and a `发送` button are present.
- Web status panel shows:
  - control mode: `WEB`;
  - end effector: `强脑灵巧手`.
- Web configuration drawer shows:
  - `末端执行器配置` selected as `强脑灵巧手`;
  - green `当前配置` marker.
- Operator reports enable produced no Web error, but finger control did not move
  the hand.

Additional Web-send/CAN evidence on 2026-06-30:

- Operator ran a Web small single-finger send while passively logging
  `can_arm_a`.
- Web did not show an error.
- The hand still did not move.
- The provided external CAN sample included:
  - `0x2A1`, `0x2A2`, `0x2A3`, `0x2A4`;
  - `0x251` through `0x257`;
  - `0x261` through `0x267`;
  - `0x2A5`, `0x2A6`, `0x2A7`, `0x2A8`, `0x2A9`.
- Local protocol notes and upstream parser code identify:
  - `0x251-0x257` as NERO joint high-speed feedback;
  - `0x2A8` as gripper feedback;
  - `0x2A9` as J7 angle feedback;
  - Revo2 command frames as `0x1B1`, `0x1B2`, `0x1B3`, `0x1B5`;
  - Revo2 feedback frames as `0x1C0`, `0x1C1`, `0x1C2`, `0x1C3`.
- The provided sample did not show Revo2 `0x1B*` command or `0x1C*` feedback
  frames.

Current interpretation:

- External arm CAN is healthy.
- The provided passive sample does not prove that J6 end-effector CAN is
  forwarded to the external arm CAN bus.
- Web end-effector configuration is no longer the primary suspected blocker
  because the screenshots show `强脑灵巧手` as current configuration.
- Web can accept a hand send without visible error, but no physical hand motion
  has been observed.
- The remaining likely blockers are J6 hand power/communication, hand-side
  fault/compatibility, Web command not being sent to the Revo2 bridge, or an
  internal controller-to-hand bridge issue.

New Drive document review on 2026-06-30:

- Downloaded and reviewed the newer Linker document set from the supplied
  Google Drive folder.
- Review record: `../data-collection/docs/reviews/linker_drive_20260630_review.md`.
- The documents confirm LinkerHand L6 as a CAN/RS485 hand with `24 V` power and
  native `0..255` L6 commands.
- The direct LinkerHand SDK uses right hand CAN ID `0x27` and left hand CAN ID
  `0x28`.
- The `api_lk73_v1.0.4` package describes a Linker/LBOT robot controller stack:
  default controller IP `192.168.10.21`, Web platform
  `http://192.168.10.21:8000`, and L6 APIs
  `l6_set_position`, `l6_set_velocity`, and `l6_set_effort`.
- This controller stack is not proven to be present on the current NERO
  installation, whose accepted arm path is direct host USB-CAN plus NERO Web at
  `http://192.168.31.1/#/welcome`.
- Therefore the next diagnostic should first check whether the Linker/LBOT
  controller exists before continuing Revo2-specific assumptions.

Updated next gate: `S14.3K Linker/LBOT read-only controller probe`.

Read-only checks:

```bash
ip -br addr
ping -c 2 192.168.10.21
curl -I --max-time 3 http://192.168.10.21:8000
```

Accept the gate if the result is recorded either way:

- reachable: write a custom read-only `LbotRobot("192.168.10.21")` probe for
  API version, controller info, and current state only;
- unreachable: treat the new SDK as evidence for a different/additional
  controller stack and ask the vendor whether NERO J6 supports LinkerHand L6
  directly or requires a Linker/LBOT controller or firmware option.

Do not run vendor demos from `api_lk73_v1.0.4`; some demos command hand motion,
arm motion, zero setting, enable/disable, e-stop, and joint-limit changes.

Photo evidence on 2026-06-30:

- Operator provided photos under `docs/evidence/pics/灵巧手连接设备/`.
- The photos show a WANPTEK bench DC supply and two blue USB-CAN adapters whose
  terminal labels include `120R`, `GND`, `CANL`, and `CANH`.
- No Ethernet/RJ45 network controller, Raspberry Pi, or router is visible.
- Interpretation: this is a LinkerHand direct bench-test/debug kit, not the
  Linker/LBOT `192.168.10.21` controller.
- This explains why the current network probe does not reach
  `192.168.10.21`; the observed kit is not an IP device.
- This does not mean the installed hands should be reconnected immediately.
  Current installation remains through NERO J6 until a deliberate bench-test
  branch is accepted.

Revised S14.3K conclusion:

- The Linker/LBOT network controller is not currently evidenced by the network
  probe or the photos.
- Next decision should be made before touching wiring:
  - keep the J6-integrated installation and ask vendor which NERO firmware/Web
    setting supports LinkerHand L6; or
  - intentionally switch one hand to a direct bench-test setup using the shown
    24 V supply plus USB-CAN kit.

Bench-test branch, if selected later:

1. Test only one hand at a time.
2. Power down and disconnect that hand from NERO J6 first; do not connect one
   hand simultaneously to J6 and the bench CAN/power kit.
3. Verify L6 manual XT30(2+2) polarity and CAN_H/CAN_L before energizing.
4. Set bench supply to the manual-confirmed `24 V` range with conservative
   current limiting before connection.
5. Bring up only the selected USB-CAN interface at `1000000` bitrate.
6. Run identity/status reads first, not gestures or position commands.

Update on 2026-06-30:

- The bench-test branch has now been selected for the left hand only.
- The operator reports the selected left hand is disconnected from the NERO arm
  and powered independently.
- The new evidence image is
  `docs/evidence/pics/灵巧手连接设备/灵巧手左手上电操控示意图.jpeg`.
- The image shows about `24.00 V` and `0.122 A` on the WANPTEK supply.
- The operator initially described the computer connection as serial, but live
  host evidence corrected that interpretation: no `/dev/serial/by-id/`,
  `/dev/ttyUSB*`, or `/dev/ttyACM*` was present.
- `dmesg` shows PEAK-System `XCAN-USB`, USB ID `0c72:000c`, driver `peak_usb`,
  attached as SocketCAN `can1` at USB bus path `1-3.4.4:1.0`.
- The active branch is therefore LinkerHand CAN, not RS485/Modbus.
- Detailed plan: `docs/phases/s14_left_hand_can_bringup_plan.md`.

Revised next gate:

1. Confirm `can1` is the hand-only PEAK adapter and not `can_arm_a` or
   `can_arm_b`.
2. Bring `can1` UP at bitrate `1000000` if needed.
3. Use LinkerHand L6 left hand CAN ID `0x28`.
4. Run `bash scripts/s14_linkerhand_l6_can_readonly_probe.sh can1 left`.
5. Do not run GUI, `test_hand.py`, `gestures.py`, or SDK motion examples before
   S14.6C read-only acceptance.

S14.6C live result:

- `can1` was brought UP at `1000000` and reported `ERROR-ACTIVE`.
- The original project probe confirmed left serial `LHL6-03-253-L-B-1-C`,
  plausible temperature values, and all-zero fault values.
- The operator observed physical hand opening during the probe.
- Therefore the original probe is not accepted as motion-free read-only.
- `0x01` is treated as motion-risk, and `0x02` is removed from the default safe
  probe until semantics are reviewed.
- The updated probe now sends only identity/health requests: `0x64`, `0xC0`,
  `0x33`, `0x35`, and `0x36`.
- Result record:
  `docs/results/s14_left_hand_can_readonly_result_20260630.md`.

Revised next gate after this observation:

1. Stop sending raw/manual CAN commands.
2. Passive `timeout 5s candump -tz can1` produced no idle frames while the bench
   supply stayed stable at about `24 V` and `0.135 A`; this is now treated as an
   idle-device fact, not a communication failure.
3. Use the local tuned repository `upstream/linkerhand_wrapper` as the primary hand
   control source, but only through project safety wrappers for the first gates.
4. Run SDK-backed identity/health with:

   ```bash
   .venv/nero-sdk/bin/python scripts/s14_linkerhand_l6_sdk_health.py \
     --can can1 \
     --side left
   ```

5. Redesign S14.8C first micro motion around the SDK preset table, with explicit
   acceptance that `0x01` can physically move the hand. Do not run full SDK demos
   or GUI tools before this gate passes.

S14 SDK health result:

- Accepted on 2026-06-30; see
  `docs/results/s14_left_hand_sdk_health_result_20260630.md`.
- The local SDK identified left hand serial `LHL6-03-253-L-B-1-C` on `can1`.
- Embedded version was `[2, 3, 7]`.
- Three fault samples were all zero, with stable temperature and current raw
  values.
- Next gate is `scripts/s14_linkerhand_l6_sdk_motion_gate.py --mode open-anchor`
  dry-run.
- The open-anchor dry-run was accepted on 2026-06-30; see
  `docs/results/s14_left_hand_open_anchor_dry_run_result_20260630.md`.
- The next gate is the explicit open-anchor execute command, which sends one
  SDK `open` preset to the left hand on `can1`.
- The open-anchor execute gate was accepted from SDK/software health on
  2026-06-30; see
  `docs/results/s14_left_hand_open_anchor_execute_result_20260630.md`.
- The final `Bad file descriptor` line occurred after completion and is treated
  as SDK receive-thread shutdown noise. The wrapper now joins the receive thread
  before shutting down the bus.
- The left index micro-motion dry-run and execute gates were accepted from
  SDK/software health on 2026-06-30; see
  `docs/results/s14_left_hand_index_micro_result_20260630.md`.
- Operator reported the open-anchor and index-micro physical observation as
  normal and expected.
- Next gate is right-hand independent bench reproduction under
  `docs/phases/s14_right_hand_reproduction_plan.md`. Synchronized control remains
  blocked until the right hand passes the same gates.
- Field correction: the left and right hands now each have their own CAN cable
  connected through the USB-C adapter path. Before right-hand health, inventory
  and fix both hand CAN positions with `scripts/s14_hand_can_inventory.sh`.
- Inventory result: `can1` is accepted left hand; `can2` is right-hand
  candidate and was DOWN during inventory. Activate `can2` at `1000000` before
  right-hand SDK health.
- Right-hand SDK health was accepted on `can2` on 2026-06-30; see
  `docs/results/s14_right_hand_sdk_health_result_20260630.md`.
- Right-hand open-anchor was accepted from SDK/software health on 2026-06-30;
  see `docs/results/s14_right_hand_open_anchor_result_20260630.md`.
- Operator observed non-index finger motion but no visible index motion.
  Resolve with right-hand index-micro verification before any synchronized
  control.
- Right-hand index-micro passed from SDK/software health on 2026-06-30; see
  `docs/results/s14_right_hand_index_micro_result_20260630.md`.
- Physical observation of right index response was confirmed by the operator.
- Dual-hand synchronization planning is recorded in
  `docs/phases/s14_dual_hand_sync_plan.md`; the first allowed software step is
  dual open-anchor dry-run only.
- Dual open-anchor passed from SDK/software health on 2026-06-30; see
  `docs/results/s14_dual_open_anchor_result_20260630.md`.
- No visible response was observed, which is expected when both hands are
  already near open. Next gate is dual index-micro dry-run, not fist/full-hand
  motion.
- Dual index-micro passed from SDK/software health on 2026-06-30; see
  `docs/results/s14_dual_index_micro_result_20260630.md`.
- Next phase is S15 hybrid arm+hand coordination. Arms should use ROS2
  `agx_arm_ros`; hands should continue through LinkerHand SDK wrappers until a
  ROS hand bridge is implemented.

Blocking wiring issue before any bench-test:

- `docs/evidence/pics/灵巧手连接设备/灵巧手连接设备03.jpeg` shows an exposed/frayed
  conductor near the bench supply and loose harness.
- Its role is not identifiable from the photo. It may be power, ground, shield,
  or unused wire.
- Do not energize the bench supply or connect a hand to this kit until every
  conductor is identified with a multimeter, the L6 manual XT30(2+2) pinout is
  verified, and the exposed conductor is either properly terminated or
  individually insulated.
- No bare strands may remain near the power binding posts or CAN terminals.
- A continuity check must confirm no short between power and CAN lines before
  connecting a hand.

Deferred S14.3J Revo2/J6 gate:

1. Confirm which arm J6 the connected hand cable is plugged into.
2. Keep Web `6.8.5 末端执行器配置` as `强脑灵巧手`; do not change load/TCP values
   during this diagnostic step.
3. Run a filtered passive CAN check during another Web small single-finger
   send, focused on Revo2 frames:
   `timeout 20s candump -tz can_arm_a,1B0:7F0,1C0:7F0`.
4. Record whether any `0x1B*` command or `0x1C*` feedback appears.
5. Re-check physical cable seating at J6 and the hand connector, using the
   manual references `2.1.2` and `2.3.2`.
6. If the Linker/LBOT controller is not present, and no Revo2 frames or hand
   motion are observed, escalate from software settings to J6 accessory
   power/communication and vendor/device-side support.

### S14.4 First Finger Motion

Deferred. Requires the SDK-backed S14.8C dry-run/safety gate. First finger
motion starts with the LinkerHand SDK `open` preset as an anchor command, then a
small index micro-motion only after the anchor is accepted. No object may be in
the hand.

## Stop Conditions

Stop immediately if:

- Cable starts to pull, twist sharply, or rub across J6/J7.
- The installed hand does not match the expected left/right side.
- A screw or flange component shifts under hand weight.
- Web, ROS, or SDK reports non-zero error status.
- Hand feedback is missing but control commands would be sent.
- Any finger moves without an explicit S14 motion gate.
