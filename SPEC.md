# P48 → 8 V PIP adapter: design notes

Engineering and provenance notes for the miniature phantom-power to plug-in-
power adapter generated from [`netlist.py`](netlist.py). See
[README.md](README.md) for the user-facing overview (architecture, BOM,
manufacturing, fit test). This file records **where the numbers came from** and
why the layout is shaped the way it is.

> **Status (rev-E):** `netlist.py`, the board, the fab package and the schematic
> figure are all the rev-E low-noise design (emitter-bypass buffer CB2/CB3+RB2/RB3,
> R1→7.5k, R1/R2 in 1206, R8→1k, R9→47k, C4→47µF, XLR_CLEARANCE 3.5 mm), verified
> by the `sim/` harness. The inner copper is now two **solid GND planes** with via
> stitching (git.koti #1) and the supply nets carry a real **Power** netclass (#7).

## Netlist provenance

The schematic originally delivered with the design carried **no connectivity**.
The netlist below was reconstructed from the architecture description (buffered,
impedance-balanced, ~3 mA/pin) and standard P48→PIP practice, and is now the
single source of truth in `netlist.py`. The design is **schematic-free**: the
board (`build_pcb.py`) is synthesized directly from the netlist and the schematic
figure (`scripts/gen_schematic.py` → `images/schematic.webp`) is drawn from the
same netlist, so they can never drift apart.

Component **values are nominal**: they follow from the topology and typical
practice, not from a bench-tuned prototype. Bias values in particular may want
tuning before a production run; the topology is what drives layout and routing.

### Derived netlist (authoritative)

| Net | Connections (ref.pad) | Function |
| :-- | :-- | :-- |
| **GND** | J1.1, MIC1.2, D1.A, C4.2, C5.2, C1.2, R4.2, R7.2, C3.2, Q2.C, Q3.C | XLR pin 1 / 0 V (solid In1/In2 planes) |
| **P2** | J1.2, R1.1, RB2.2 | XLR pin 2 (hot), Q2 draws ~3 mA |
| **P3** | J1.3, R9.1, Q1.C, R2.1, RB3.2 | XLR pin 3 (cold), Q3 + regulator draw ~3 mA |
| **VPIP** | Q1.E, C1.1, C5.1, R10.1, R3.1, R6.1 | ~7.5 V plug-in-power rail |
| **VREF** | R9.2, D1.K, C4.1, R8.1 | filtered 8.2 V Zener reference |
| **Q1B** | R8.2, Q1.B | regulator base (buffered VREF) |
| **MICOUT** | MIC1.1, R10.2, C2.1 | capsule signal node |
| **Q2B** | R3.2, R4.1, C2.2, Q2.B | hot buffer base (bias + AC-coupled signal) |
| **Q2E** | R1.2, Q2.E, CB2.1 | hot buffer emitter (low-Z output node) |
| **Q3B** | R6.2, R7.1, C3.1, Q3.B | cold buffer base (AC-grounded) |
| **Q3E** | R2.2, Q3.E, CB3.1 | cold buffer emitter (low-Z output node) |
| **NB2** | CB2.2, RB2.1 | hot emitter-bypass mid-node |
| **NB3** | CB3.2, RB3.1 | cold emitter-bypass mid-node |

Pad roles: SOT-23 pad 1 = B, 2 = E, 3 = C (matches the KiCad MMBT390x symbols);
D_Zener pad 1 = K (cathode), 2 = A (anode); R/C pads 1, 2. The **emitter-bypass
network** (rev-E) AC-couples each buffer's low-impedance emitter to its phantom
pin: `Q2E → CB2(22µF) → NB2 → RB2(47Ω) → P2` (and the cold-side mirror), dropping
the output impedance from ~10 kΩ to ~78 Ω while R1/R2 still set the DC current.

### Circuit derivation

**Reference / PIP supply** (fed from XLR pin 3, the "cold/quiet" pin):
`P3 → R9(47k) → VREF`; D1 (8.2 V Zener) clamps VREF to GND; C4 (47 µF) filters it
(R9·C4 ≈ 0.07 Hz, sub-1 Hz). Q1 (NPN) is an emitter follower: base = VREF via
the R8 (1 k) stopper, collector = P3, emitter = VPIP (~7.5 V), bypassed by
C1 (22 µF) + C5 (10 µF).

**Capsule bias:** `VPIP → R10(6.8k) → MICOUT`; the capsule sits between MICOUT and
GND.

**Hot buffer** (draws ~3 mA from pin 2, carries the audio): Q2 (PNP) base = Q2B,
set by the R3/R4 divider off VPIP with the capsule signal AC-coupled in through
C2; emitter = Q2E fed from P2 through R1 (7.5 k). The rev-E emitter-bypass network
`Q2E → CB2(22µF) → NB2 → RB2(47Ω) → P2` AC-couples the low-impedance emitter to
the pin, so the output impedance is ~78 Ω (not R1's 7.5 kΩ) while R1 still sets
the DC current; collector = GND. Signal current modulates the pin-2 current →
audio on the hot leg.

**Cold buffer** (draws a matched ~3 mA from pin 3, no signal): Q3 (PNP)
identical to Q2 but with its base Q3B AC-grounded by C3; divider R6/R7; emitter
= Q3E fed from P3 through R2 (10 k) with the matching `CB3/RB3` bypass to P3;
collector = GND. It matches the pin-2 output impedance so the source looks
balanced to the preamp.

## Board geometry

```
BOARD_W = 11.1 mm     fixed by the NC3MXX chuck bore
BOARD_T = 0.8 mm      the edge must slip between the XLR pins
BOARD_L = 35.3 mm     DERIVED (see below)
```

**Nothing is placed by absolute-coordinate patching.** Positions come from a
two-column auto-placer working from the real footprint pad sizes, so the layout
is reproducible from `netlist.py` alone.

- **Why two columns:** KiCad's 1206 courtyard is 4.69 mm wide, so only two wide
  parts fit across an 11.1 mm board. The 22 SMD parts are ordered by signal flow
  and snaked into the two columns so connected parts stay adjacent: mic/Q2 input
  and its CB2/RB2 emitter-bypass, then reference/regulator, then the Q3 cold
  buffer and its CB3/RB3 bypass. Keeping each output stage's bypass beside its
  transistor is both a routing win and a low-noise win (tight bypass loops).
- **Row pitch** is set by the *actual* pad-copper extents plus a copper-to-copper
  gap, so no pad ever shorts to its neighbour even where courtyards overlap.
- **Board length is derived, not chosen.** The XLR solder pad is 8 mm long
  (5 mm internal pin + 3 mm past the tip for solder access). The last component
  row, plus a required 5 mm pin-tip-to-component clearance, plus the pad and a
  small edge gap, fix `BOARD_L`. Change the component set and the board length
  follows automatically.

## Stackup and design rules

- 4 layers: F.Cu (signal + parts + GND pour), **In1.Cu + In2.Cu (both solid GND
  planes)**, B.Cu (GND pour + signal escapes + the XLR pin-3 pad).
- The inner planes are a real shield for the µV front end. Signal routing is
  confined to the outer layers (the DSN relabels In1/In2 as plane layers) so the
  planes stay unbroken; a grid of GND through vias stitches all four layers and
  a fanout via ties every GND pad to the planes.
- Track 0.15 mm, clearance 0.125 mm, vias 0.6 mm / 0.3 mm drill.
- Copper-to-edge ≥ 0.25 mm (an edge keepout enforces a fab-safe margin).
- Supply nets **P2, P3, VPIP, VREF** carry a wider 0.25 mm "Power" netclass
  (`build_pcb.patch_project_netclass`); GND is distributed by the planes, not a
  track, so it stays on the default class.

All within JLCPCB / PCBWay standard 4-layer capability.

## Custom footprints

Two footprints are built inline by `build_pcb.py` rather than pulled from a
library:

- **`XLR_SolderCup`**: three THT face pads at the NC3MXX cup spacing. Pins 1
  and 2 sit on the front face (x = 1.90, 9.52 mm), pin 3 on the back face
  (x = 5.71 mm, centred). Each pad is 8 mm long. This is the "sandwich" mount:
  the board edge goes between the pins, so `BOARD_T` (0.8 mm) must be less than
  the pin-1/2 to pin-3 gap.
- **`MIC_2pad`**: two through-hole solder points at the top edge for the
  AOM-5024 capsule leads (0.8 mm drill, 1.4 mm pad).

## Known trade-offs

- **Courtyard overlap.** Six 1206 caps and two 1206 resistors on an 11.1 mm board
  force the assembly courtyards to overlap. There are **no copper shorts**
  (pad-to-pad clearance is enforced), so `courtyards_overlap` is downgraded to a
  warning rather than an error. Move the 1206 parts to smaller packages or widen
  the board to eliminate it.
- **Hidden silkscreen designators.** At this density the reference designators
  are illegible, so they're hidden. Assemble from the BOM and placement data.
- **Freerouting determinism.** Routing is done by Freerouting; re-running
  `route.py` regenerates a pristine board and re-routes from scratch (importing
  onto an already-routed board can leave stale inner-layer traces). The routed
  result committed here is what the fab package and previews are built from.

## Verification status

- **DRC:** 0 errors, 0 unconnected pads, 0 footprint errors (`kicad-cli pcb drc`).
- **No separate ERC:** the design is schematic-free. `netlist.py` is the
  connectivity source of truth, `build_pcb.py` synthesizes the board directly
  from it, and `scripts/gen_schematic.py` draws the schematic figure from the
  same netlist, so board and schematic cannot disagree.
- Fab outputs regenerate cleanly from `export_gerbers.py`.
