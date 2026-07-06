#!/usr/bin/env python3
"""
Draw a properly wired schematic of the P48 -> 8V PIP adapter with schemdraw and
save it to images/schematic.webp (rasterized via Inkscape).  Wired by transistor
anchor (base/emitter/collector); topology matches netlist.py exactly (rev-E, with
the low-Z emitter-bypass output network CBx/RBx):

  GND    J1.1 MIC1.2 D1.A C1.2 C3.2 C4.2 C5.2 R4.2 R7.2 Q2.C Q3.C
  P2     J1.2 R1.1 RB2.2            P3   J1.3 R9.1 Q1.C R2.1 RB3.2
  VPIP   Q1.E C1.1 C5.1 R10.1 R3.1 R6.1
  VREF   R9.2 D1.K C4.1 R8.1        Q1B  R8.2 Q1.B
  MICOUT MIC1.1 R10.2 C2.1
  Q2B    R3.2 R4.1 C2.2 Q2.B        Q2E  R1.2 Q2.E CB2.1
  Q3B    R6.2 R7.1 C3.1 Q3.B        Q3E  R2.2 Q3.E CB3.1
  NB2    CB2.2 RB2.1                NB3  CB3.2 RB3.1

    python scripts/gen_schematic.py
"""
import os
import shutil
import subprocess

import schemdraw
import schemdraw.elements as elm

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "images", "schematic.webp")

INK = "#17242f"
NET = "#8a1c1c"
GREY = "#5b6672"
schemdraw.config(unit=2.6, fontsize=13, lw=2.0, color=INK)
d = schemdraw.Drawing(show=False)

RAILY = 0.0        # VPIP rail
BASEY = -3.6       # transistor-base / MICOUT row
GNDY = -7.4        # ground row


def dot(p):
    d.add(elm.Dot().at(p))


def gnd():
    d.add(elm.Ground())


def txt(p, s, color=INK, size=13, halign="center"):
    d.add(elm.Label().at(p).label(s, color=color, fontsize=size, halign=halign))


def emitter_out(t, remit, cb, rb, phantom, nbname):
    """rev-E low-Z output stage: the emitter node Qxe feeds the phantom pin two
    ways -- Rx sets the DC operating current, while the CBx/RBx branch AC-couples
    the low-impedance emitter to the pin (Zout 10k -> ~80 Ω, +21 dB level)."""
    d.add(elm.Line().at(t.emitter).right().length(0.5))
    ex, ey = t.emitter[0] + 0.5, t.emitter[1]
    dot((ex, ey))
    px = ex + 4.2
    # DC feed: emitter resistor to the phantom pin
    d.add(elm.Resistor().at((ex, ey)).right().length(2.6).label(remit, "top", ofst=0.15))
    d.add(elm.Line().at((ex + 2.6, ey)).right().to((px, ey)))
    dot((px, ey))
    d.add(elm.Tag().at((px, ey)).right().label(phantom, color=NET))
    # AC bypass: CBx -> NBx node -> RBx (series stopper), rejoining at the pin
    by = ey - 1.9
    d.add(elm.Line().at((ex, ey)).down().to((ex, by)))
    d.add(elm.Capacitor().at((ex, by)).right().length(2.1).label(cb, "bottom", ofst=0.2))
    dot((ex + 2.1, by))
    txt((ex + 2.1, by - 0.55), nbname, color=NET, size=10)
    d.add(elm.Resistor().at((ex + 2.1, by)).right().length(2.1).label(rb, "bottom", ofst=0.2))
    d.add(elm.Line().at((px, by)).up().to((px, ey)))


def buffer(bx, rhi, rlo, qname, remit, phantom, sig, cb, rb, nbname):
    """Common-collector PNP buffer: bias divider rhi/rlo from VPIP, emitter via
    the rev-E CBx/RBx bypass network to a phantom pin, collector to GND.
    sig(bx) draws the base input."""
    dot((bx, BASEY)); dot((bx, RAILY))
    d.add(elm.Resistor().at((bx, RAILY)).down().to((bx, BASEY)).label(rhi, "left", ofst=0.15))
    d.add(elm.Resistor().at((bx, BASEY)).down().to((bx, GNDY)).label(rlo, "left", ofst=0.15))
    gnd()
    sig(bx)
    d.add(elm.Line().at((bx, BASEY)).right().length(1.8))
    t = elm.BjtPnp(circle=True).anchor("base")
    d.add(t)
    txt((t.collector[0], BASEY + 1.9), qname, size=13)
    d.add(elm.Line().at(t.collector).down().to((t.collector[0], GNDY)))
    gnd()
    emitter_out(t, remit, cb, rb, phantom, nbname)


VX, VY = -9.0, 3.0     # VREF node (regulator)

# ===========================================================================
# XLR connector J1 (far left)  -- pin1 GND, pin2 P2 (hot), pin3 P3 (cold)
# ===========================================================================
JX = -15.5
d += elm.Line().at((JX, 3.2)).to((JX, -1.4)).linewidth(2.4)          # connector body
txt((JX - 0.3, 3.9), "J1", color=GREY, size=13, halign="right")
txt((JX - 0.3, 3.1), "Neutrik", color=GREY, size=11, halign="right")
txt((JX - 0.3, 2.5), "XLR3", color=GREY, size=11, halign="right")
# pin 2 (P2, hot) -> tag (consumed far away at the hot buffer)
d += elm.Dot().at((JX, 2.6))
d += elm.Line().right().length(1.5).label("2", "top", fontsize=11)
d += elm.Tag().label("P2", color=NET)
# pin 3 (P3, cold) -> wired straight to R9, and up to Q1 collector via tags
d += elm.Dot().at((JX, 0.9))
d += elm.Line().right().length(1.5).label("3", "top", fontsize=11)
d += elm.Line().at((JX + 1.5, 0.9)).right().to((VX - 3.2, 0.9))
d += elm.Line().up().to((VX - 3.2, VY))
dot((VX - 3.2, VY))
d += elm.Dot().at((JX, -0.8))
d += elm.Line().right().length(1.2).label("1", "bottom", fontsize=11)
gnd()

# ===========================================================================
# REFERENCE + REGULATOR -> VPIP   (well clear of J1)
# ===========================================================================
d += elm.Resistor().at((VX - 3.2, VY)).right().to((VX, VY)).label("R9\n47k")
dot((VX, VY))
txt((VX - 0.15, VY + 1.5), "VREF", color=NET, size=12)
# D1 zener on a stub to the left; C4 straight down -- separated so labels clear
d += elm.Line().at((VX, VY)).left().length(1.3)
d += elm.Zener().down().label("D1\n8.2V", "left", ofst=0.15).reverse()
gnd()
d += elm.Capacitor().at((VX, VY)).down().label("C4\n47µF", "right", ofst=0.2)
gnd()
d += elm.Resistor().at((VX, VY)).right().label("R8\n1k")
q1 = elm.BjtNpn(circle=True).anchor("base")
d += q1
txt((q1.collector[0] + 1.5, VY + 0.2), "Q1  MMBT3904", size=13, halign="left")
d += elm.Line().at(q1.collector).up().length(1.9)
d += elm.Tag().up().label("P3", color=NET)
d += elm.Line().at(q1.emitter).down().to((q1.emitter[0], RAILY))
RX0 = q1.emitter[0]
dot((RX0, RAILY))

# column x-positions
CAPX1, CAPX2 = RX0 + 2.6, RX0 + 4.0     # C1, C5
MX = RX0 + 7.0                           # capsule / MICOUT
HBX = MX + 5.2                           # hot buffer divider
CBX = HBX + 10.0                         # cold buffer divider (clears hot Qxe net)
RX1 = CBX + 1.6

# ===========================================================================
# VPIP rail (drawn bus) + bypass caps
# ===========================================================================
d += elm.Line().at((RX0, RAILY)).to((RX1, RAILY)).linewidth(3.2)
d += elm.Vdd().at((RX0, RAILY)).label("VPIP", color=NET)
for x, name in ((CAPX1, "C1\n22µF"), (CAPX2, "C5\n10µF")):
    dot((x, RAILY))
    d += elm.Capacitor().at((x, RAILY)).down().label(name, "left", ofst=0.2)
    gnd()

# ===========================================================================
# CAPSULE BIAS + HOT BUFFER  (MICOUT gets its own clear lane)
# ===========================================================================
dot((MX, RAILY))
d += elm.Resistor().at((MX, RAILY)).down().to((MX, BASEY)).label("R10\n6.8k", "right", ofst=0.2)
dot((MX, BASEY))
txt((MX - 1.4, BASEY + 0.05), "MICOUT", color=NET, size=12, halign="right")
d += elm.Mic().at((MX, BASEY)).down()
gnd()
txt((MX - 1.35, BASEY - 2.0), "MIC1", size=12, halign="right")
txt((MX - 1.35, BASEY - 2.65), "AOM-5024", size=11, halign="right")

def hot_sig(bx):
    d.add(elm.Capacitor().at((MX, BASEY)).right().to((bx, BASEY)).label("C2\n22µF", "top", ofst=0.2))

buffer(HBX, "R3\n100k", "R4\n100k", "Q2  MMBT3906", "R1\n7.5k", "P2", hot_sig,
       "CB2\n22µF", "RB2\n47Ω", "NB2")

# ===========================================================================
# COLD BUFFER (impedance match); C3 AC-grounds the base
# ===========================================================================
def cold_sig(bx):
    d.add(elm.Line().at((bx, BASEY)).left().length(1.9))
    d.add(elm.Capacitor().down().to((bx - 1.9, GNDY)).label("C3\n22µF", "left", ofst=0.2))
    d.add(elm.Ground())

buffer(CBX, "R6\n100k", "R7\n100k", "Q3  MMBT3906", "R2\n10k", "P3", cold_sig,
       "CB3\n22µF", "RB3\n47Ω", "NB3")

txt(((RX0 + RX1) / 2, GNDY - 1.5),
    "P48 → 8 V PIP adapter   ·   impedance-balanced two-transistor buffer   ·   nets per netlist.py",
    color=GREY, size=12)

# ---- save + rasterize ----
SVG = os.path.splitext(OUT)[0] + ".svg"
d.save(SVG)
print("wrote", SVG)
ink = shutil.which("inkscape") or r"C:\Program Files\Inkscape\bin\inkscape.exe"
if os.path.exists(ink):
    from PIL import Image
    tmp_png = os.path.splitext(OUT)[0] + ".__tmp.png"
    subprocess.run([ink, SVG, "--export-type=png", "--export-filename=" + tmp_png,
                    "--export-width=2800", "--export-background=#ffffff"], check=True)
    Image.open(tmp_png).save(OUT, "WEBP", lossless=True, method=6)  # crisp lines/text
    os.remove(tmp_png)
    print("wrote", OUT)
else:
    print("Inkscape not found; wrote SVG only:", SVG)
