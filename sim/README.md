# P48 → 8 V PIP adapter — ngspice simulation harness

Headless SPICE verification of the adapter circuit. The deck is **generated from
`../netlist.py`**, the same single source of truth the schematic and the PCB
derive from, so the simulation cannot drift away from the board.

> **Note:** the result tables below reflect the *baseline* circuit. `netlist.py`
> is now rev-E (emitter-bypass buffer etc.); `run.ps1` is retargeted to it and
> passes (Zout ~78 Ω, gain ~0 dB, balanced pins). See the closed git.koti issues
> #2/#3/#5/#11 for the rev-E numbers.

```
sim/
├── gen_deck.py            # imports ../netlist.py, writes p48.cir (stdlib only)
├── run.ps1               # regenerate → run ngspice → parse → assert (exit code)
├── models/
│   ├── zener_bzx84c8v2.lib   # D1, datasheet-derived (Nexperia BZX84-C8V2)
│   ├── bjt_mmbt390x.lib      # Q1 (NPN 3904), Q2/Q3 (PNP 3906)
│   └── jfet_j201.lib         # capsule stand-in (NOT a board part)
├── p48.cir               # GENERATED — do not edit (git-ignored)
└── out.log              # ngspice listing (git-ignored)
```

## Install ngspice (Windows)

KiCad 10 ships only `ngspice.dll` (its Eeschema engine) — there is **no CLI**
under `%LOCALAPPDATA%\Programs\KiCad\10.0\bin`, so install the standalone CLI:

1. Download the official Windows build (64-bit) from the ngspice project on
   SourceForge — current release **v46**, file `ngspice-46_64.7z`
   (`ng-spice-rework/46/`). Verify the md5 shown on the download page.
2. Extract with 7-Zip; it unpacks to `Spice64\`. Put `Spice64\bin` on your PATH
   (that dir holds `ngspice_con.exe`, the console/batch binary this harness uses).
3. Check: `ngspice_con.exe --version` → `ngspice-46 ...`.

Alternatives: `choco install ngspice` (needs an elevated shell; currently
packages v46). `winget` does not carry it as of this writing.

Optional cross-check tool: LTspice (freeware) can open the same cards for
interactive poking; not required for the deliverable.

## Run

```powershell
pwsh -File sim\run.ps1        # or: powershell -File sim\run.ps1
```

`run.ps1` regenerates `p48.cir`, finds ngspice (PATH → common install dirs),
runs `ngspice_con -b p48.cir`, parses every `name = value` it prints, and
range-checks the pass criteria. **Exit 0 = all pass, exit 1 = a failure**
(ngspice does not fail its own process on a `.meas` miss, so the script does it).

Run the deck by hand:

```powershell
ngspice_con.exe -b sim\p48.cir      # (run from the sim/ dir so .include resolves)
```

## What each analysis checks

Expected values are the hand-derived numbers from the 2026-07-06 design review
(issues #2/#3/#5/#6/#9); ±15 % is allowed where the zener dominates.

| # | Analysis | Confirms | Latest sim result |
|---|----------|----------|-------------------|
| 1 | `.op` operating point | #3, #5 | V(P2)=30.6 V, V(P3)=28.2 V, I(pin2)=2.56 mA, I(pin3)=2.91 mA, VPIP=7.30 V, I(D1)=199 µA |
| 2 | `.ac` output impedance at pin 2 | #2 | **10.03 kΩ flat** 20 Hz–100 kHz (not the old 30–50 Ω claim) |
| 3 | `.ac` gain, capsule→differential | #2, #6 | −21.8 dB @ 1 kHz (in the 13–22 dB loss band); passband flat 100 Hz–20 kHz to 0.44 dB; polarity **inverting** |
| 4 | `.tran` startup 0–15 s (cold) | #9 | max Vce(Q1)=28.2 V (< 35 V); VPIP at 90 % in **~0.7 s** |
| 5 | `.tran` polarity blip | #6 | down-gate-step → up-output ⇒ inverting (agrees with #3) |
| 6 | `.noise` at the output | — | informational only (see caveat) |

### Findings the sim surfaced (feed back to the issues)

- **Bass roll-off ≈ 4.3 dB at 20 Hz.** The audio passband has a ~40 Hz high-pass
  corner set by the **VPIP bypass** (C1‖C5 = 32 µF) working against Q1's ~170 Ω
  emitter output impedance — *not* by the C2 coupling cap (C2's corner is ~1.2 Hz).
  Bumping C1/C5 to ~220 µF flattens 20 Hz to < 0.1 dB. Candidate tweak if flat
  bass matters; otherwise a documented −3 dB near 40 Hz.
- **Startup is faster than estimated.** VPIP reaches 90 % in ~0.7 s and is settled
  by ~2 s, versus the ~5–10 s note in #9 — because the zener clamps VREF long
  before R9·C4 (2.2 s) would fully charge, shortening the ramp.
- **Polarity is inverting** (positive gate excursion → negative-going differential
  output), matching the #6 topology prediction. The *capsule-construction* half of
  #6 still needs the bench.

## Model caveats — read before trusting numbers

- **Zener (`BZX84C8V2`) is datasheet-DERIVED, not a vendor `.lib`.** Nexperia does
  not publish a downloadable SPICE model and the vendor download endpoints block
  scripted access, so the model is fitted to the Rev.7 datasheet reverse curve
  (Vz=8.2 V and rdif=15 Ω at 5 mA, rdif=80 Ω at 1 mA — the soft knee). At the
  ~190 µA operating point it predicts VREF≈7.96 V ⇒ VPIP≈7.30 V. That is ~0.1 V
  above the review's 6.5–7.2 V estimate: the datasheet's max rdif bounds how soft
  the knee can be, so the real part sags *less* at 190 µA than hand-estimated.
  If you obtain the official vendor model, drop it in `models/` (keep the name
  `BZX84C8V2`) and re-run. See the file header for the fit rationale + source URL.
- **Zener noise is not modelled.** SPICE has no avalanche-noise magnitude, so the
  absolute self-noise from analysis 6 is meaningless; it only shows the R9/C4
  filter shape. No assertion is placed on it.
- **BJTs** use the canonical 2N3904/2N3906 die models (accepted stand-ins for the
  SOT-23 MMBT390x per issue #10).
- **Capsule** is a J201 JFET proxy for the electret's internal common-source
  buffer (gate at Vgs≈0, ~Idss, as a real electret self-biases). It sets absolute
  gain and the capsule DC operating point; the real AOM-5024 transconductance and
  output polarity are bench items.

## Evaluating the proposed respin tweaks

Once green as-is, use the harness to A/B the review's suggestions before any
respin (edit `../netlist.py`, re-run):

- R9 100k → 47k (#3): roughly doubles zener bias, watch the pin-3 imbalance.
- R1 10k → 7.5k (#5): rebalances pin-2 current, changes the pin-2 source-Z leg.
- C2/C3 swap (#6): flips the driven leg to pin 3 to correct differential polarity.
- C1/C5 → ~220 µF: flat bass to 20 Hz (this harness's own finding, above).
