# P48 → 8 V PIP adapter: ngspice simulation harness

Headless SPICE verification of the adapter circuit. The deck is **generated from
`../netlist.py`**, the same single source of truth the schematic figure and the
PCB derive from, so the simulation cannot drift away from the board.

The tables below are the **rev-E** results (the CB2/CB3+RB2/RB3 emitter-bypass
low-Z output stage); `run.ps1` range-checks 17 assertions and all pass.

```
sim/
├── gen_deck.py            # imports ../netlist.py, writes p48.cir (stdlib only)
├── run.ps1               # regenerate → run ngspice → parse → assert (exit code)
├── plot_response.py      # wide-band AC sweep → ../images/frequency_response.webp
├── models/
│   ├── zener_bzx84c8v2.lib   # D1, datasheet-derived (Nexperia BZX84-C8V2)
│   ├── bjt_mmbt390x.lib      # Q1 (NPN 3904), Q2/Q3 (PNP 3906)
│   └── jfet_j201.lib         # capsule stand-in (NOT a board part)
├── p48.cir               # GENERATED, do not edit (git-ignored)
└── out.log              # ngspice listing (git-ignored)
```

## Install ngspice (Windows)

KiCad 10 ships only `ngspice.dll` (its Eeschema engine); there is **no CLI**
under `%LOCALAPPDATA%\Programs\KiCad\10.0\bin`, so install the standalone CLI:

1. Download the official Windows build (64-bit) from the ngspice project on
   SourceForge, current release **v46**, file `ngspice-46_64.7z`
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

## Frequency-response plot

```
python sim/plot_response.py          # needs: pip install matplotlib pillow
```

`plot_response.py` reuses `gen_deck`'s component cards + harness, runs two AC
sweeps (10 Hz – 384 kHz: the audio band plus the ultrasonic range up to the
192 kHz Nyquist of a 384 kHz sample rate) and writes
`../images/frequency_response.webp`: differential gain and output impedance vs
frequency. The gain trace is referred to the capsule output node, so it shows
the adapter electronics in isolation (the circuit is flat well into the
ultrasonic; the capsule sets the real HF limit).

## What each analysis checks

Expected values are the hand-derived numbers from the 2026-07-06 design review
(issues #2/#3/#5/#6/#9); ±15 % is allowed where the zener dominates.

| # | Analysis | Confirms | rev-E sim result |
|---|----------|----------|-------------------|
| 1 | `.op` operating point | #3, #5 | V(P2)=27.6 V, V(P3)=27.3 V, I(pin2)=3.00 mA, I(pin3)=3.03 mA, VPIP=7.37 V, I(D1)=408 µA, pin imbalance 37 µA |
| 2 | `.ac` output impedance at pin 2 | #2, #11 | **~78 Ω, flat** 1 k–20 kHz (0.004 flatness), the emitter bypass, down from ~10 kΩ |
| 3 | `.ac` gain, capsule→differential | #2, #6 | **−0.56 dB @ 1 kHz** (near-unity buffer); passband flat 100 Hz–20 kHz to 0.009 dB; LF droop 0.69 dB @ 20 Hz; polarity **inverting** |
| 4 | `.tran` startup 0–15 s (cold) | #9 | max Vce(Q1)=23.1 V (< 35 V); VPIP at 90 % in **~0.8 s**, settled 7.38 V |
| 5 | `.tran` polarity blip | #6 | down-gate-step → up-output ⇒ inverting (agrees with #3) |
| 6 | `.noise` at the output | n/a | informational only (see caveat) |

### Findings the sim surfaced (fed into rev-E)

- **Output impedance is now ~78 Ω**, flat across the audio band, set by the rev-E
  CB2/CB3+RB2/RB3 emitter bypass that takes the output at Q2/Q3's low-Z emitters,
  down from the baseline ~10 kΩ, and low enough to drive long cable without HF loss.
- **The bass roll-off is now a gentle, deliberate 0.69 dB at 20 Hz.** The baseline's
  ~4 dB VPIP-bypass droop is gone; the remaining sub-50 Hz taper is set by the
  emitter-bypass caps against their DC-bias derating, which is desirable here and
  keeps CB2/CB3 small (no oversizing / polymer needed).
- **Startup** reaches 90 % of VPIP in ~0.8 s and is settled by ~2 s (well under the
  ~5–10 s #9 estimate): the zener clamps VREF long before R9·C4 fully charges.
- **Polarity is inverting** (positive gate excursion → negative-going differential
  output), matching the #6 topology prediction. The *capsule-construction* half of
  #6 still needs the bench.

## Model caveats (read before trusting the numbers)

- **Zener (`BZX84C8V2`) is datasheet-DERIVED, not a vendor `.lib`.** Nexperia does
  not publish a downloadable SPICE model and the vendor download endpoints block
  scripted access, so the model is fitted to the Rev.7 datasheet reverse curve
  (Vz=8.2 V and rdif=15 Ω at 5 mA, rdif=80 Ω at 1 mA, the soft knee). At the
  rev-E ~410 µA operating point (R9 47k) it predicts VREF≈8.0 V ⇒ VPIP≈7.37 V.
  That is ~0.2 V above the review's 6.5–7.2 V estimate: the datasheet's max rdif
  bounds how soft the knee can be, so the real part sags *less* than hand-estimated.
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

## Using the harness for further tweaks

rev-E already folds in the review's key changes: R9 100k → 47k (#3, ~doubles the
zener bias) and R1 10k → 7.5k (#5, rebalances the pin-2 current), plus the
CB2/CB3+RB2/RB3 emitter bypass, which made the earlier "C1/C5 → 220 µF for flat
bass" idea unnecessary (the sub-50 Hz taper is now deliberate). Use the harness to
A/B any further change (edit `../netlist.py`, re-run):

- **C2 ↔ C3 swap (#6):** the ready polarity fix *if* the bench confirms the capsule
  is inverted; it moves the driven leg to pin 3. Documented in `netlist.py`; do not
  apply blind.
- Bias re-tuning, or dropping in an official vendor zener model, then re-running
  the 17 assertions.
