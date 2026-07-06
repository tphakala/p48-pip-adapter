#!/usr/bin/env python3
"""
Generate sim/p48.cir from ../netlist.py -- the single source of truth.

The schematic, the PCB (build_pcb.py) and now this SPICE deck all derive from
netlist.py, so they cannot drift apart.  This script imports the COMPONENTS and
NETS tables, maps them to ngspice element cards (net names become node names,
GND becomes node 0), then appends the phantom-power test harness and the
analysis .control block described in issue #10.

Pure stdlib -- it must NOT import pcbnew (issue #10 prerequisite 1).

Usage:
    python gen_deck.py            # writes sim/p48.cir next to this file
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
import netlist as N  # noqa: E402  (path set above)

# Model names the generated cards reference (defined in models/*.lib).
ZENER_MODEL = "BZX84C8V2"          # D1 (netlist value "8.2V" -> this model)

# Skip the connectors: they are the interface the harness drives, not devices.
SKIP_REFS = {"J1", "MIC1"}


def node(net):
    """net name -> SPICE node ('GND' is the global ground, node 0)."""
    return "0" if net == "GND" else net


def pin_to_net():
    """(ref, pad) -> net name, inverted from netlist.NETS."""
    m = {}
    for net, conns in N.NETS.items():
        for ref, pad in conns:
            m[(ref, pad)] = net
    return m


def spice_value(v):
    """KiCad value string -> SPICE numeric suffix ('22uF'->'22u', '10k'->'10k')."""
    return v[:-1] if v.endswith("F") else v


def component_cards():
    """Emit one SPICE element card per board component (connectors excluded).

    Pad-role conventions come straight from netlist.py:
        SOT-23  : pad 1 = B, pad 2 = E, pad 3 = C
        D_Zener : pad 1 = K (cathode), pad 2 = A (anode)
        R / C   : pads 1, 2
    """
    p = pin_to_net()
    lines = []

    def net(ref, pad):
        return node(p[(ref, pad)])

    for ref, (value, _sym, _fp) in N.COMPONENTS.items():
        if ref in SKIP_REFS:
            continue
        kind = ref[0]
        if kind in ("R", "C"):
            lines.append(f"{ref} {net(ref,'1')} {net(ref,'2')} {spice_value(value)}")
        elif kind == "D":
            # SPICE diode:  Dxxx  n+ (anode)  n- (cathode)  model
            lines.append(f"{ref} {net(ref,'2')} {net(ref,'1')} {ZENER_MODEL}")
        elif kind == "Q":
            # SPICE BJT:  Qxxx  C  B  E  model   (value string is the model name)
            lines.append(f"{ref} {net(ref,'3')} {net(ref,'1')} {net(ref,'2')} {value}")
        else:
            raise ValueError(f"no SPICE mapping for {ref} ({value})")
    return lines


# ---------------------------------------------------------------------------
# Phantom-power test harness (issue #10 "deck skeleton").
#   vph  = +48 V phantom rail        P2/P3 = XLR pins 2 (hot) / 3 (cold)
# Real balanced preamp inputs are DC-blocked, so the 2 k differential load is
# AC-coupled here (CINP is a short in-band, corner ~0.08 Hz).  A bare 2 k across
# P2-P3 would sink ~1.5 mA of DC and corrupt the operating point; the hand
# analysis in issues #3/#5 assumes no DC through the preamp.
# IZT/IBIAS are dormant (0) here and only enabled by the output-impedance test.
# ---------------------------------------------------------------------------
HARNESS = """\
* ==== phantom-power test harness ====
V48   vph 0   DC 48
RF2   vph P2  6.81k
RF3   vph P3  6.81k
* preamp differential input, AC-coupled (see header note)
RINP  P2  npa 2k
CINP  npa P3  1000u
* ~30 m mic cable, pin-to-shield
CCB2  P2  0   3n
CCB3  P3  0   3n
* output-impedance test injector + DC-bias substitute (enabled only in test 2)
IZT   0   P2  DC 0 AC 0
IBIAS 0   P2  DC 0
* capsule stand-in: internal common-source JFET.  VSIG carries three roles:
*   DC 0        -> quiescent gate (electret self-biases near Vgs=0, ~Idss)
*   AC 1        -> unit drive for the gain / Zout / noise analyses
*   PWL step    -> -10 mV gate step at t=1 s for the polarity transient.
* The step is NEGATIVE on purpose: at Vgs=0 a positive step would forward-bias
* the JFET gate junction (leaves the valid region); a small downward step stays
* linear.  The authoritative polarity is the small-signal AC result (test 3).
JCAP  MICOUT vsig 0 J201
VSIG  vsig 0  DC 0 AC 1 PWL(0 0 0.9999 0 1 -10m 5 -10m)
"""


def analysis_block():
    """The ngspice .control block: the six analyses of issue #10.

    Every asserted quantity is printed as a scalar on its own line so run.ps1
    can parse "name = value" and range-check it.
    """
    r8 = spice_value(N.COMPONENTS["R8"][0])   # KCL uses the live netlist values
    r9 = spice_value(N.COMPONENTS["R9"][0])
    return (r""".control
set noaskquit
set numdgt=7

echo
echo "########## 1. OPERATING POINT ##########"
op
* pin currents = current the phantom feed delivers into each XLR pin
let irf2 = (v(vph)-v(P2))/6810
let irf3 = (v(vph)-v(P3))/6810
* zener current by KCL at VREF: in via R9, out via R8 (Q1 base); C4 open at DC
let ir9 = (v(P3)-v(VREF))/__R9__
let ir8 = (v(VREF)-v(Q1B))/__R8__
let izener = ir9 - ir8
* Q1 collector-emitter voltage at rest
let vceq1_op = v(P3)-v(VPIP)
print v(P2) v(P3) v(VPIP) v(VREF) v(MICOUT) v(Q2B) v(Q3B)
print irf2 irf3 izener vceq1_op

echo
echo "########## 2. AC OUTPUT IMPEDANCE at pin 2 ##########"
* Isolate the adapter's own source impedance: open the phantom feed, the preamp
* shunt and the cable cap (all AC paths off P2), hold Q2's DC bias with a
* current source (AC-open), inject 1 A AC into P2 -> Zout = |V(P2)|.  Issue #2.
alter RF2   = 1e12
alter RINP  = 1e12
alter CCB2  = 1e-15
alter IBIAS dc = 2.59m
alter IZT   ac = 1
ac dec 10 10 100k
meas ac zout_20   FIND vm(P2) AT=20
meas ac zout_1k   FIND vm(P2) AT=1000
meas ac zout_20k  FIND vm(P2) AT=20000
* restore the harness for the following analyses
alter RF2   = 6.81k
alter RINP  = 2k
alter CCB2  = 3n
alter IBIAS dc = 0
alter IZT   ac = 0

echo
echo "########## 3. AC GAIN capsule(MICOUT) -> differential (P2-P3) ##########"
ac dec 20 10 100k
let vdiff = v(P2)-v(P3)
let gdb   = db(vdiff/v(MICOUT))
let vdre  = real(vdiff)
* midband loss (issue #2: 13-22 dB) and passband flatness
meas ac g_20     FIND gdb  AT=20
meas ac g_100    FIND gdb  AT=100
meas ac g_1k     FIND gdb  AT=1000
meas ac g_20k    FIND gdb  AT=20000
meas ac g_mid_hi MAX  gdb  FROM=100 TO=20000
meas ac g_mid_lo MIN  gdb  FROM=100 TO=20000
* absolute polarity: real part of vdiff for a +1 V gate drive (issue #6).
* negative => positive gate -> negative-going output (inverting topology).
meas ac vdre_1k  FIND vdre AT=1000

echo
echo "########## 4. TRANSIENT startup (0..15 s, cold power-on) ##########"
tran 5m 15 uic
let vceq1 = v(P3)-v(VPIP)
meas tran vpip_0p1  FIND v(VPIP) AT=0.1
meas tran vpip_0p5  FIND v(VPIP) AT=0.5
meas tran vpip_1s   FIND v(VPIP) AT=1
meas tran vpip_2s   FIND v(VPIP) AT=2
meas tran vpip_5s   FIND v(VPIP) AT=5
meas tran vpip_10s  FIND v(VPIP) AT=10
meas tran vpip_15s  FIND v(VPIP) AT=15
* time to reach 90 % of the settled value (settling estimate)
meas tran t_90pct   WHEN v(VPIP)=6.57 RISE=1
meas tran vce_max   MAX  vceq1   FROM=0 TO=15

echo
echo "########## 5. TRANSIENT polarity cross-check (gate steps -10 mV) ##########"
* Start from the settled bias; step the capsule gate DOWN 10 mV (stays in the
* JFET's valid region).  The output is AC-coupled (~40 Hz high-pass, tau~4 ms),
* so a step gives a short BLIP that decays -- read it right after the step, not
* seconds later.  An inverting topology gives an UPWARD blip for a downward gate
* step (vd_hi - vd_base > 0), which must agree with vdre_1k < 0 from test 3.
tran 100u 1.2
let vd = v(P2)-v(P3)
meas tran vd_base FIND vd AT=0.98
meas tran vd_hi   MAX  vd FROM=1.0 TO=1.05
meas tran vd_lo   MIN  vd FROM=1.0 TO=1.05
let vd_blip = vd_hi - vd_base
print vd_base vd_hi vd_lo vd_blip

echo
echo "########## 6. NOISE (informational, no assertion) ##########"
* SPICE does not model zener avalanche-noise magnitude, so absolute self-noise
* here is meaningless -- this only shows the R9/C4 filter shape.
noise v(P2) VSIG dec 10 10 100k 1
print onoise_total inoise_total

echo
echo "########## DONE ##########"
.endc
.end
""".replace("__R9__", r9).replace("__R8__", r8))


def build_deck():
    inc = lambda name: f".include models/{name}"  # noqa: E731 (relative to sim/)
    parts = [
        "* p48_pip_adapter -- SPICE deck GENERATED by sim/gen_deck.py",
        "* Source of truth: ../netlist.py.  Do not hand-edit; regenerate instead.",
        "* Nodes are net names from netlist.NETS; GND -> 0.",
        "*",
        inc("zener_bzx84c8v2.lib"),
        inc("bjt_mmbt390x.lib"),
        inc("jfet_j201.lib"),
        "",
        "* ==== circuit (generated from netlist.py) ====",
        *component_cards(),
        "",
        HARNESS,
        analysis_block(),
    ]
    return "\n".join(parts) + "\n"


def main():
    out = os.path.join(HERE, "p48.cir")
    with open(out, "w", newline="\n") as f:
        f.write(build_deck())
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
