#!/usr/bin/env python3
"""
Draw a properly wired schematic of the P48 -> 8V PIP adapter with schemdraw and
save it to images/schematic.png (rasterized via Inkscape).  Every part is wired
by transistor anchor (base/emitter/collector), so the topology matches
netlist.py exactly:

  GND    J1.1 MIC1.2 D1.A C1.2 C3.2 C4.2 C5.2 R4.2 R7.2 Q2.C Q3.C
  P2     J1.2 R1.1                 P3   J1.3 R9.1 Q1.C R2.1
  VPIP   Q1.E C1.1 C5.1 R10.1 R3.1 R6.1
  VREF   R9.2 D1.K C4.1 R8.1       Q1B  R8.2 Q1.B
  MICOUT MIC1.1 R10.2 C2.1
  Q2B    R3.2 R4.1 C2.2 Q2.B       Q2E  R1.2 Q2.E
  Q3B    R6.2 R7.1 C3.1 Q3.B       Q3E  R2.2 Q3.E

    python scripts/gen_schematic.py
"""
import os
import shutil
import subprocess

import schemdraw
import schemdraw.elements as elm

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "images", "schematic.png")

INK = "#16232e"
NET = "#8a1c1c"
schemdraw.config(unit=2.6, fontsize=14, lw=2.0, color=INK)
d = schemdraw.Drawing(show=False)

RAIL_Y = 0.0
BY = -3.4          # base / MICOUT row
GNDY = -7.0


def dot(p):
    d.add(elm.Dot().at(p))


def ground():                       # ground at the drawing cursor
    d.add(elm.Ground())


def ground_at(p):
    d.add(elm.Ground().at(p))


def buffer(bx, refs, sig=None):
    """A common-collector buffer: R_bias divider from VPIP + R_emitter to a
    phantom pin.  refs = (Rbias_hi, Rbias_lo, Q, Remit, phantom).  sig: a
    callable drawing the base input (C-coupled signal or C to gnd)."""
    rhi, rlo, q, remit, phantom = refs
    dot((bx, BY))
    dot((bx, RAIL_Y))
    d.add(elm.Resistor().at((bx, RAIL_Y)).down().to((bx, BY)).label(rhi, "left"))
    d.add(elm.Resistor().at((bx, BY)).down().to((bx, GNDY)).label(rlo, "left"))
    ground()
    if sig:
        sig(bx)
    d.add(elm.Line().at((bx, BY)).right().length(1.7))
    t = elm.BjtPnp(circle=True).anchor("base")
    d.add(t)
    d.add(elm.Label().at((t.collector[0], BY + 1.7)).label(q, fontsize=13))
    d.add(elm.Line().at(t.collector).down().to((t.collector[0], GNDY)))
    ground()
    d.add(elm.Line().at(t.emitter).right().length(0.5))
    d.add(elm.Resistor().right().label(remit, "top"))
    d.add(elm.Tag().right().label(phantom, color=NET))


# ===========================================================================
# XLR connector J1 (far left): pin1 GND, pin2 P2 (hot), pin3 P3 (cold)
# ===========================================================================
JX = -11.5
d += elm.Label().at((JX + 0.3, 3.4)).label("J1  ·  Neutrik XLR3", fontsize=12, color="#555")
for y, num, name in ((2.4, "2", "P2"), (0.8, "3", "P3")):
    d += elm.Dot(open=True).at((JX, y))
    d += elm.Line().right().length(1.4).label(num, "top", fontsize=11)
    d += elm.Tag().label(name, color=NET)
d += elm.Dot(open=True).at((JX, -0.9))
d += elm.Line().right().length(1.1).label("1", "bottom", fontsize=11)
d += elm.Ground()

# ===========================================================================
# REFERENCE + REGULATOR -> VPIP
# ===========================================================================
VX, VY = -5.8, 3.0
d += elm.Tag().at((VX - 3.2, VY)).left().label("P3", color=NET)
d += elm.Resistor().at((VX - 3.2, VY)).right().to((VX, VY)).label("R9\n100k")
dot((VX, VY))
d += elm.Label().at((VX - 0.15, VY + 1.5)).label("VREF", color=NET, fontsize=12)
# D1 zener on a short stub to the left
d += elm.Line().at((VX, VY)).left().length(1.2)
d += elm.Zener().down().label("D1\n8.2V", "left").reverse()
ground()
# C4 straight down from VREF
d += elm.Capacitor().at((VX, VY)).down().label("C4\n22µF", "right")
ground()
# R8 : VREF -> Q1 base
d += elm.Resistor().at((VX, VY)).right().label("R8\n10k")
d += (q1 := elm.BjtNpn(circle=True).anchor("base").label("Q1\nMMBT3904", "right"))
d += elm.Line().at(q1.collector).up().length(1.8)
d += elm.Tag().up().label("P3", color=NET)
d += elm.Line().at(q1.emitter).down().to((q1.emitter[0], RAIL_Y))
RX0 = q1.emitter[0]
dot((RX0, RAIL_Y))

# column positions (left -> right)
MX = RX0 + 5.2          # MICOUT / capsule bias
HBX = MX + 3.8          # hot buffer divider
CBX = HBX + 8.6         # cold buffer divider
RX1 = CBX + 1.4         # rail end

# ===========================================================================
# VPIP rail (real drawn bus) + bypass caps
# ===========================================================================
d += elm.Line().at((RX0, RAIL_Y)).to((RX1, RAIL_Y)).linewidth(3.2)
d += elm.Vdd().at((RX0, RAIL_Y)).label("VPIP", color=NET)
for dx, name in ((1.5, "C1\n22µF"), (3.0, "C5\n10µF")):
    dot((RX0 + dx, RAIL_Y))
    d += elm.Capacitor().at((RX0 + dx, RAIL_Y)).down().label(name, "left")
    ground()

# ===========================================================================
# CAPSULE BIAS + HOT BUFFER
# ===========================================================================
dot((MX, RAIL_Y))
d += elm.Resistor().at((MX, RAIL_Y)).down().to((MX, BY)).label("R10\n6.8k", "right")
dot((MX, BY))
d += elm.Label().at((MX - 0.15, BY + 0.75)).label("MICOUT", color=NET, fontsize=12)
d += elm.Mic().at((MX, BY)).down()
ground()
d += elm.Label().at((MX - 1.15, BY - 1.7)).label("MIC1\nAOM-5024", fontsize=12)
# C2 : MICOUT -> Q2 base
d += elm.Capacitor().at((MX, BY)).right().to((HBX, BY)).label("C2\n22µF", "top")

buffer(HBX, ("R3\n100k", "R4\n100k", "Q2\nMMBT3906", "R1\n10k", "P2"))

# ===========================================================================
# COLD BUFFER (impedance match); C3 AC-grounds the base
# ===========================================================================
def c3_to_gnd(bx):
    d.add(elm.Line().at((bx, BY)).left().length(1.7))
    d.add(elm.Capacitor().down().to((bx - 1.7, GNDY)).label("C3\n22µF", "left"))
    d.add(elm.Ground())

buffer(CBX, ("R6\n100k", "R7\n100k", "Q3\nMMBT3906", "R2\n10k", "P3"), sig=c3_to_gnd)

d += elm.Label().at(((RX0 + RX1) / 2, GNDY - 1.4)).label(
    "P48 → 8 V PIP adapter   ·   impedance-balanced two-transistor buffer   ·   "
    "nets per netlist.py", fontsize=12, color="#666")

# ---- save + rasterize ----
SVG = os.path.splitext(OUT)[0] + ".svg"
d.save(SVG)
print("wrote", SVG)
ink = shutil.which("inkscape") or r"C:\Program Files\Inkscape\bin\inkscape.exe"
if os.path.exists(ink):
    subprocess.run([ink, SVG, "--export-type=png", "--export-filename=" + OUT,
                    "--export-width=2600", "--export-background=#ffffff"], check=True)
    print("wrote", OUT)
else:
    print("Inkscape not found; wrote SVG only:", SVG)
