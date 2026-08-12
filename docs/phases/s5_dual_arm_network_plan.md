# S5 Dual-Arm Network Identity Plan

Date: 2026-06-24, updated 2026-06-25

## Current Facts

- The site has two physical NERO arms.
- The two arms are independently powered.
- The currently observed arm is treated as Arm A.
- Arm A Web UI is reachable at `http://192.168.31.1/#/welcome`.
- Arm A Web footer shows version `v1.121` and model `7ax`.
- Arm A all seven joint status tabs have been reported normal by the operator.
- Arm B also passed Web read-only validation.
- Arm A network configuration screenshot:
  `docs/evidence/pics/网络配置页面截图.png`.
- Earlier Arm A hotspot configuration visible in the screenshot:
  - hotspot name: `agx-7ax-xin`
  - hotspot password: redacted; obtain the current value from the lab credential store
  - hotspot channel: `9`
- The operator later changed the hotspots to unique names:
  - Arm A: `agx-7ax-armA`
  - Arm B: `agx-7ax-armB`
- The Ethernet configuration form is visible, but the screenshot does not prove
  a committed Ethernet IP value. Treat Arm A wired IP as not yet verified.

Manual facts:

- Default Wi-Fi SSID pattern: `agx-7ax-xx`.
- Default Wi-Fi password: redacted; do not copy credentials into tracked documentation.
- Default Wi-Fi Web address: `http://192.168.31.1/`.
- Default wired controller IP: `10.90.0.150`.
- Wired access requires the PC to use a static IP in the same subnet, for
  example `10.90.0.153/255.255.255.0`.
- The Web configuration page supports network-port configuration and hotspot
  configuration.

## Risk

If both arms keep the same default network identity, the operator may connect to
the wrong arm without noticing. If both controllers are placed on the same wired
LAN with the same static IP, `10.90.0.150`, the network will be ambiguous.

The manual also warns not to set two arms as slave mode simultaneously and not
to enable CAN push on two connected arms simultaneously, otherwise external CAN
communication can fail and the devices may need restart.

## Decision

Treat the deployment as a two-arm system, but continue S5/S6/S7/S8 one arm at a
time until each arm has a unique identity and independent feedback path.

Use labels:

| Label | Meaning | Current network identity |
| --- | --- | --- |
| Arm A | The first verified arm | Wi-Fi hotspot `agx-7ax-armA`; Web `192.168.31.1` when connected to its hotspot |
| Arm B | The second verified arm | Wi-Fi hotspot `agx-7ax-armB`; Web `192.168.31.1` when connected to its hotspot |

Do not infer left/right names yet. Assign `left` and `right` only after the
physical installation side is confirmed and photographed.

## Recommended Next Steps

1. Keep physical labels `Arm A` and `Arm B`.
2. Save Web screenshots for each arm:
   - home/status page
   - `关节1` through `关节7`
   - network configuration page
   - version/status page if available
3. Do not change network settings again unless the new value is written
   down first.
4. If wired simultaneous Web access is needed later, assign unique wired static
   IPs in the same subnet, for example:
   - Arm A: `10.90.0.151`
   - Arm B: `10.90.0.152`
   - Host PC: `10.90.0.153`
   - Netmask: `255.255.255.0`
   - Gateway: empty, following the manual's direct-connection example

## Rules Before S6 CAN

- Do not connect both arms to the same CAN bus.
- Do not enable CAN push on both arms while they are connected together.
- First S6 should be performed per arm, one arm and one USB-CAN module at a
  time.
- Dual-arm CAN should use independent CAN interfaces, such as `can_left` and
  `can_right`, only after both official CAN modules and their USB port mapping
  are recorded.
