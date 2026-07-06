"""
Authoritative netlist / footprint / placement description for the
P48 -> 8V PIP adapter.

This module is the single source of truth for connectivity.  The design is
schematic-free: the PCB builder (build_pcb.py) synthesizes the board directly
from the tables below, and the schematic figure (scripts/gen_schematic.py ->
images/schematic.webp) is drawn from the same tables, so the schematic and the
board can never drift apart.

--------------------------------------------------------------------------
Circuit derived from README.md architecture (impedance-balanced, 3 mA/pin):

  Reference / PIP supply (fed from XLR pin 3 = the "cold/quiet" pin):
    P3 --R9(100k)--> VREF ; D1(8.2V zener) clamps VREF to GND ;
    C4(22u) filters VREF (R9*C4 ~ 0.07 Hz, sub-1Hz per README).
    Q1(NPN) emitter follower: base=VREF (via R8 stopper), collector=P3,
    emitter=VPIP (~7.5V).  C1(22u)+C5(10u) bypass VPIP.

  Capsule bias:
    VPIP --R10(6.8k)--> MICOUT ; MIC1(+)=MICOUT, MIC1(-)=GND.

  Hot buffer (draws ~3 mA from XLR pin 2, carries the audio):
    Q2(PNP): base=Q2B set by divider R3/R4 off VPIP, capsule signal
    AC-coupled in through C2 ; emitter=Q2E fed from P2 through R1(10k);
    collector=GND.  Signal current modulates pin-2 current -> audio.

  Cold buffer (draws matched ~3 mA from XLR pin 3, no signal):
    Q3(PNP): identical to Q2 but base Q3B is AC-grounded by C3 (README:
    "base is AC-grounded"), divider R6/R7, emitter=Q3E fed from P3 through
    R2(10k), collector=GND.  Matches pin-2 output impedance -> looks
    balanced to the preamp.

  NOTE: values are nominal, derived from the README description and standard
  P48->PIP practice; topology is what drives layout/routing.  Bench tuning of
  bias values may be desired before a production run.
--------------------------------------------------------------------------
"""

# Standard KiCad footprint libraries (installed with KiCad 10).
FP_SOT23   = ("Package_TO_SOT_SMD", "SOT-23")
FP_SOD323  = ("Diode_SMD",          "D_SOD-323")
FP_C1206   = ("Capacitor_SMD",      "C_1206_3216Metric")
FP_C0805   = ("Capacitor_SMD",      "C_0805_2012Metric")
FP_R0603   = ("Resistor_SMD",       "R_0603_1608Metric")
FP_R1206   = ("Resistor_SMD",       "R_1206_3216Metric")   # R1/R2 thermal (issue #4)

# Custom footprints are built inline by build_pcb.py.
FP_XLR = ("custom", "XLR_SolderCup")   # 3 THT pads, Neutrik NC3MXX pin pitch
FP_MIC = ("custom", "MIC_2pad")        # 2 THT pads for the AOM-5024 capsule

# ref -> (value, symbol lib_id, footprint)
COMPONENTS = {
    "J1":   ("XLR3",     "Connector:XLR3",               FP_XLR),
    "MIC1": ("AOM5024",  "Connector:Conn_01x02_Male",    FP_MIC),
    "Q1":   ("MMBT3904", "Transistor_BJT:MMBT3904",      FP_SOT23),
    "Q2":   ("MMBT3906", "Transistor_BJT:MMBT3906",      FP_SOT23),
    "Q3":   ("MMBT3906", "Transistor_BJT:MMBT3906",      FP_SOT23),
    "D1":   ("8.2V",     "Device:D_Zener",               FP_SOD323),
    "C1":   ("22uF",     "Device:C",                     FP_C1206),
    # C2 couples the capsule into Q2's base (signal path, only ~1 V DC across it):
    # use X7R -- microphonics are the only concern (derating is negligible at 1 V);
    # a film/polymer A/B before production is a nicety (issue #9).
    # POLARITY (issue #6): sim is inverting; IF the bench capsule-polarity test
    # confirms it, the zero-BOM-cost fix is to swap the base coupling here --
    # move C2 to Q3B and C3 (the AC ground) to Q2B.  Do NOT apply blind.
    "C2":   ("22uF",     "Device:C",                     FP_C1206),
    "C3":   ("22uF",     "Device:C",                     FP_C1206),
    "C4":   ("47uF",     "Device:C",                     FP_C1206),
    "C5":   ("10uF",     "Device:C",                     FP_C0805),
    # R1/R2 in 1206, not 0603: each dissipates continuously inside the sealed
    # XLR shell -- R1 = 67 mW (pin-2's full ~3 mA x 22.5 V), R2 = 50 mW.  1206's
    # 250 mW rating leaves ~30% derated margin at 80 C ambient; a 0603 would run
    # near its limit.  Matched package hot/cold for symmetry (issue #4).
    "R1":   ("7.5k",     "Device:R",                     FP_R1206),
    "R2":   ("10k",      "Device:R",                     FP_R1206),
    "R3":   ("100k",     "Device:R",                     FP_R0603),
    "R4":   ("100k",     "Device:R",                     FP_R0603),
    "R6":   ("100k",     "Device:R",                     FP_R0603),
    "R7":   ("100k",     "Device:R",                     FP_R0603),
    "R8":   ("1k",       "Device:R",                     FP_R0603),
    "R9":   ("47k",      "Device:R",                     FP_R0603),
    "R10":  ("6.8k",     "Device:R",                     FP_R0603),
    # --- rev-E low-noise / low-Zout output buffer (issues #2, #11 + noise opt) --
    # CB2/CB3 AC-bypass R1/R2 so the output is taken at Q2/Q3's low-Z emitters:
    # Zout 10k->~80 ohm (in-band), level +21 dB, input-referred noise -34 dB.
    # RB2/RB3 are the series stop resistors (capacitive-cable stability).
    # NOTE: CB2/CB3 sit across ~23 V DC -> they MUST be 50 V rated; spec X7R.
    # DC-bias derating (a 50 V X7R holds only ~12-17 uF at 23 V) raises the bass
    # corner, but that is ACCEPTABLE here: some sub-50 Hz rolloff is desirable
    # for this use case, so no oversizing/polymer is needed (issue #9).  Class-2
    # MLCC are mildly microphonic -- a film/polymer A/B is a pre-production
    # nicety only, not a blocker.
    "CB2":  ("22uF",     "Device:C",                     FP_C1206),
    "CB3":  ("22uF",     "Device:C",                     FP_C1206),
    "RB2":  ("47",       "Device:R",                     FP_R0603),
    "RB3":  ("47",       "Device:R",                     FP_R0603),
}

# Pad roles for reference (not consumed programmatically):
#   SOT-23  : pad "1"=B, "2"=E, "3"=C   (matches KiCad MMBT390x symbol)
#   D_Zener : pad "1"=K (cathode), "2"=A (anode)
#   R / C   : pads "1","2"

# net name -> list of (ref, pad_number)
NETS = {
    "GND":    [("J1","1"), ("MIC1","2"), ("D1","2"), ("C4","2"), ("C5","2"),
               ("C1","2"), ("R4","2"), ("R7","2"), ("C3","2"),
               ("Q2","3"), ("Q3","3")],
    "P2":     [("J1","2"), ("R1","1"), ("RB2","2")],
    "P3":     [("J1","3"), ("R9","1"), ("Q1","3"), ("R2","1"), ("RB3","2")],
    "VPIP":   [("Q1","2"), ("C5","1"), ("C1","1"), ("R10","1"),
               ("R3","1"), ("R6","1")],
    "VREF":   [("R9","2"), ("D1","1"), ("C4","1"), ("R8","1")],
    "Q1B":    [("R8","2"), ("Q1","1")],
    "MICOUT": [("MIC1","1"), ("R10","2"), ("C2","1")],
    "Q2B":    [("R3","2"), ("R4","1"), ("C2","2"), ("Q2","1")],
    "Q2E":    [("R1","2"), ("Q2","2"), ("CB2","1")],
    "Q3B":    [("R6","2"), ("R7","1"), ("C3","1"), ("Q3","1")],
    "Q3E":    [("R2","2"), ("Q3","2"), ("CB3","1")],
    # emitter-bypass RC networks: Q2E -CB2- NB2 -RB2- P2  (and cold-side mirror)
    "NB2":    [("CB2","2"), ("RB2","1")],
    "NB3":    [("CB3","2"), ("RB3","1")],
}

# Supply nets that route as tracks get the wider "Power" netclass (issue #7,
# consumed by build_pcb.patch_project_netclass).  GND is deliberately NOT here:
# it is distributed as the solid In1.Cu/In2.Cu ground planes, not a track, so a
# track-width class would not apply to it.
POWER_NETS = ["P2", "P3", "VPIP", "VREF"]

# ---------------------------------------------------------------------------
# Board geometry + parametric placement.  Origin at top-left; +Y downward.
# No absolute-coordinate patching: positions are computed by a 2-column
# auto-placer from the real footprint pad sizes below.
#
# Why 2 columns: KiCad's 1206 courtyard is 4.69 mm wide, so on an 11.1 mm
# board only two wide parts fit across.  The placer spaces rows by ACTUAL
# pad-copper extents (+ clearance) so no pad ever shorts to a neighbour.
# Courtyards (assembly keep-outs, which include generous silk margins) still
# overlap on this ultra-dense board -- that is an accepted trade-off of the
# form factor, not a copper problem (see README / build_pcb courtyard report).
# ---------------------------------------------------------------------------
BOARD_W = 11.1
BOARD_T = 0.8           # THIN 4-layer: the edge must slip between the XLR pins

# real KiCad courtyard (X, Y mm) -- for the informational overlap report
COURTYARD = {
    FP_R0603: (3.05, 1.55), FP_R1206: (4.65, 2.35),
    FP_C1206: (4.69, 2.39), FP_C0805: (3.49, 2.05),
    FP_SOT23: (3.95, 3.49), FP_SOD323: (3.29, 1.99),
    FP_XLR: (9.8, 8.4), FP_MIC: (5.4, 2.0),
}
# real pad-copper extent (X, Y mm) -- the placer keeps these from overlapping
PAD_EXTENT = {
    FP_R0603: (2.45, 0.95), FP_R1206: (4.05, 1.75),
    FP_C1206: (4.10, 1.80), FP_C0805: (2.90, 1.45),
    FP_SOT23: (3.35, 2.50), FP_SOD323: (2.70, 0.45),
    FP_XLR: (9.6, 8.0), FP_MIC: (5.0, 1.4),
}

_COLX = (3.0, 8.1)      # two column centres
_Y0 = 4.3               # first SMD row centre (clears the capsule pads)
_PAD_GAP = 0.38         # copper-to-copper gap between stacked pads (assembly)

# XLR solder-joint zone.  The pin runs ~5 mm along the board from the connector
# edge; the solder pad is 3 mm LONGER than the pin so it sticks out past the
# pin tip -> easier to hand-solder.  The board is lengthened to hold the longer
# pads while keeping the pin tip clear of components.
XLR_PIN_LEN = 5.0       # internal Neutrik pin length along the board (mm)
XLR_SOLDER_EXTRA = 3.0  # pad extends this far past the pin tip (solder access)
XLR_PAD_LEN = XLR_PIN_LEN + XLR_SOLDER_EXTRA          # 8 mm solder pad
XLR_CLEARANCE = 3.5     # pin tip -> nearest component pad edge (mm); trimmed from
                        # 5.0 (turnkey PCBA, not hand-solder) to reclaim ~1.5 mm
                        # and offset the rev-E bypass parts (issue: keep length ~same)
XLR_EDGE_GAP = 0.4      # pad connector-side edge -> board edge (copper clearance)

# 22 SMD parts, ordered by signal flow, snaked into the two columns
# (row r: col0 = ORDER[2r], col1 = ORDER[2r+1]).  Grouped so connected parts
# stay close: mic/Q2 hot input + its emitter-bypass, then reference/regulator,
# then the Q3 cold buffer + its emitter-bypass.  Each output stage's bypass
# network (CBx/RBx) is placed IMMEDIATELY after its Qx/Rx so the Q2E/NB2 and
# Q3E/NB3 loops stay short -- both a routing win (the P2/Q2E congestion that
# otherwise splits the board) and a low-noise win (tight bypass loops).
_ORDER = ["R10", "C2", "R3", "R4", "Q2", "R1",
          "CB2", "RB2",                 # hot emitter-bypass, beside Q2/R1
          "R9", "D1", "C4", "R8", "Q1", "C1",
          "C5", "R6", "R7", "C3", "Q3", "R2",
          "CB3", "RB3"]                 # cold emitter-bypass, beside Q3/R2


def _pad_h(ref):
    return PAD_EXTENT[COMPONENTS[ref][2]][1]


def _rows_and_ys():
    rows = [(_ORDER[i], _ORDER[i + 1]) for i in range(0, len(_ORDER), 2)]
    ys = [_Y0]
    for r in range(1, len(rows)):
        # pitch must clear the taller of the two columns' stacked pads
        need = max((_pad_h(rows[r - 1][c]) + _pad_h(rows[r][c])) / 2.0
                   for c in (0, 1)) + _PAD_GAP
        ys.append(ys[-1] + need)
    return rows, ys


# XLR pad row and total board length are DERIVED so the pin tip keeps its 5 mm
# clearance and the 8 mm pad has board under it.
_rows, _ys = _rows_and_ys()
_last_comp_edge = _ys[-1] + max(_pad_h(r) / 2.0 for r in _rows[-1])
_pin_tip = _last_comp_edge + XLR_CLEARANCE          # closest pin approach
_pad_top = _pin_tip - XLR_SOLDER_EXTRA              # component-side pad edge
XLR_Y = round(_pad_top + XLR_PAD_LEN / 2.0, 3)      # pad centre
BOARD_L = round(_pad_top + XLR_PAD_LEN + XLR_EDGE_GAP, 3)


def placement():
    """ref -> (x_mm, y_mm, rotation_deg), computed from real pad sizes."""
    rows, ys = _rows_and_ys()
    place = {
        "MIC1": (BOARD_W / 2.0, 2.0, 0),
        "J1":   (BOARD_W / 2.0, XLR_Y, 0),
    }
    for r, (a, b) in enumerate(rows):
        place[a] = (_COLX[0], ys[r], 0)
        place[b] = (_COLX[1], ys[r], 0)
    return place


# XLR sandwich mount: the thin board edge slides BETWEEN the Neutrik pins.
# Pins 1,2 solder to the FRONT face, pin 3 to the BACK face, at the 7.62 mm
# cup spacing -- so board thickness (BOARD_T) must be < the pin-1/2 to pin-3 gap.
XLR_FACE_PADS = {  # pad -> (dx, dy, side)  relative to footprint origin
    "1": (1.90 - BOARD_W / 2.0, 0.0, "F"),   # GND, front-left
    "2": (9.52 - BOARD_W / 2.0, 0.0, "F"),   # Hot, front-right
    "3": (5.71 - BOARD_W / 2.0, 0.0, "B"),   # Cold, back-centre
}
XLR_PAD = (2.0, XLR_PAD_LEN)   # XLR face pad size (mm) -- 8 mm long for solder

# Capsule (AOM-5024): 2 through-hole solder points at the top edge.
MIC_PADS = {  # pad -> (dx, dy)
    "1": (-2.0, 0.0),
    "2": ( 2.0, 0.0),
}
MIC_DRILL = 0.8
MIC_SIZE  = 1.4
