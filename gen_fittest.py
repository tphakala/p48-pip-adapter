"""
Generate a 3D-printable mechanical FIT-TEST model of the routed PCB.

Extracts the real geometry from p48_pip_adapter.kicad_pcb and emits a
parametric OpenSCAD model + STL:
  * exact 11.1 x 25 mm outline and board thickness,
  * through-holes for the 3 XLR solder-cup pins and 2 capsule pads,
  * every SMD component embossed as a raised block at its true body size and
    height (so you can check clearance inside the Neutrik chuck),
  * every pad raised as a "solder point",
  * top-copper (F.Cu) traces + vias embossed shallowly for realism.

Run with KiCad's bundled Python (needs pcbnew), then it renders the STL with
OpenSCAD automatically:
    "<KiCad>/bin/python.exe" gen_fittest.py
"""
import os
import subprocess
import sys

import pcbnew

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import netlist as NL

HERE = os.path.dirname(os.path.abspath(__file__))
BOARD = os.path.join(HERE, "p48_pip_adapter.kicad_pcb")
OUTDIR = os.path.join(HERE, "fit_test")
SCAD = os.path.join(OUTDIR, "p48_fittest.scad")
STL = os.path.join(OUTDIR, "p48_fittest.stl")
OPENSCAD = r"C:\Program Files\OpenSCAD\openscad.com"

# footprint -> (body_len, body_wid, height) mm  (real component envelopes)
BODY = {
    ("Resistor_SMD", "R_0603_1608Metric"): (1.60, 0.80, 0.45),
    ("Capacitor_SMD", "C_1206_3216Metric"): (3.20, 1.60, 1.50),
    ("Capacitor_SMD", "C_0805_2012Metric"): (2.00, 1.25, 0.85),
    ("Package_TO_SOT_SMD", "SOT-23"): (2.90, 1.30, 1.10),
    ("Diode_SMD", "D_SOD-323"): (1.80, 1.25, 0.95),
}


def mm(v):
    return round(pcbnew.ToMM(v), 4)


def extract():
    b = pcbnew.LoadBoard(BOARD)
    W, L, T = NL.BOARD_W, NL.BOARD_L, NL.BOARD_T   # y flipped (KiCad down->up)
    fcu = b.GetLayerID("F.Cu")
    refkey = {r: NL.COMPONENTS[r][2] for r in NL.COMPONENTS}

    front, back, xlr, tht, bodies, tracks, vias = [], [], [], [], [], [], []
    for fp in b.GetFootprints():
        ref = fp.GetReference()
        fx, fy = mm(fp.GetPosition().x), mm(fp.GetPosition().y)
        key = refkey.get(ref)
        if key in BODY:
            bl, bw, bh = BODY[key]
            bodies.append((fx, L - fy, bl, bw, bh, -fp.GetOrientationDegrees()))
        for p in fp.Pads():
            px, py = mm(p.GetPosition().x), mm(p.GetPosition().y)
            if p.GetAttribute() == pcbnew.PAD_ATTRIB_PTH:
                tht.append((px, L - py, mm(p.GetDrillSize().x), mm(p.GetSize().x)))
            else:                                   # SMD pad -> front or back face
                on_front = p.IsOnLayer(pcbnew.F_Cu)
                if ref == "J1":                     # XLR pad -> long in-plane solder joint
                    xlr.append((px, L - py, mm(p.GetSize().x), mm(p.GetSize().y),
                                1 if on_front else 0))
                else:
                    row = (px, L - py, mm(p.GetSize().x), mm(p.GetSize().y),
                           -p.GetOrientationDegrees())
                    (front if on_front else back).append(row)
    for t in b.GetTracks():
        if t.Type() == pcbnew.PCB_VIA_T:
            try:
                dia = mm(t.GetWidth(pcbnew.F_Cu))   # KiCad 10 vias need a layer
            except Exception:
                dia = 0.6
            vias.append((mm(t.GetPosition().x), L - mm(t.GetPosition().y), dia))
        elif t.Type() == pcbnew.PCB_TRACE_T and t.GetLayer() == fcu:
            s, e = t.GetStart(), t.GetEnd()
            tracks.append((mm(s.x), L - mm(s.y), mm(e.x), L - mm(e.y), mm(t.GetWidth())))
    return W, L, T, front, back, xlr, tht, bodies, tracks, vias


def vec(rows):
    return "[\n" + ",\n".join("  " + str(list(r)) for r in rows) + "\n]"


def main():
    if not os.path.isdir(OUTDIR):
        os.makedirs(OUTDIR)
    W, L, T, front, back, xlr, tht, bodies, tracks, vias = extract()

    scad = f"""// P48 PIP adapter -- mechanical fit-test model (auto-generated from PCB).
// Board FRONT face (components) is +Z; print flat with components UP.
// The bottom edge (high Y) is the XLR end: pins 1,2 contact the FRONT face
// pads, pin 3 the BACK face pad -- the 0.8 mm board slips between the pins.
// All dims mm.
$fn = 24;

board_w = {W};
board_l = {L};
board_t = {T};        // thin 4-layer PCB thickness (fits between XLR pins)
pad_h   = 0.18;       // solder-point / pad emboss height
trace_h = 0.12;       // top-copper trace emboss height
via_h   = 0.20;       // via emboss height
ring_h  = 0.25;       // through-hole pad ring height
emboss_scale = 1.0;   // scale ALL component heights (e.g. 1.3 for margin)
include_traces = true;

// XLR solder joints are LONG flat pads (not tall posts): they run ALONG the
// board covering the full internal pin length + 3 mm past the pin tip for
// easier soldering.  Pins 1,2 on the FRONT face, pin 3 on the BACK.

// [x, y, w, h, ang] FRONT-face component solder pads
front_pads = {vec(front)};
// [x, y, w, h, ang] BACK-face component solder pads
back_pads = {vec(back)};
// [x, y, pad_w, pad_len, front?] XLR solder pads (1 = front face, 0 = back face)
xlr_joints = {vec(xlr)};
// [x, y, drill, pad_dia] plated through-holes (capsule leads)
tht_pads = {vec(tht)};
// [x, y, body_len, body_wid, height, ang] component bodies
bodies = {vec(bodies)};
// [x1, y1, x2, y2, w] top-copper traces
tracks = {vec(tracks)};
// [x, y, dia] vias
vias = {vec(vias)};

module rrect(w, h, r, t) {{
    linear_extrude(t) offset(r) square([max(w-2*r,0.01), max(h-2*r,0.01)], center=true);
}}
module seg(x1, y1, x2, y2, w, t) {{
    linear_extrude(t) hull() {{
        translate([x1, y1]) circle(d=w);
        translate([x2, y2]) circle(d=w);
    }}
}}

difference() {{
    union() {{
        cube([board_w, board_l, board_t]);              // bare board
        // features embed 0.01 mm into the board (epsilon overlap) so the union
        // fuses into a single manifold solid instead of coincident-face shells
        translate([0, 0, board_t - 0.01]) {{
            if (include_traces)
                for (t = tracks) seg(t[0], t[1], t[2], t[3], t[4], trace_h);
            for (v = vias)
                translate([v[0], v[1], 0]) cylinder(d=v[2], h=via_h);
            for (p = front_pads)                         // front solder points
                translate([p[0], p[1], 0]) rotate([0,0,p[4]])
                    rrect(p[2], p[3], min(p[2],p[3])*0.2, pad_h);
            for (b = bodies)                             // component bodies
                translate([b[0], b[1], 0]) rotate([0,0,b[5]])
                    rrect(b[2], b[3], 0.15, b[4]*emboss_scale);
            for (h = tht_pads)                           // through-hole pad rings
                translate([h[0], h[1], 0]) cylinder(d=h[3], h=ring_h);
        }}
        for (p = back_pads)                              // BACK-face pads (pin 3)
            translate([p[0], p[1], -pad_h + 0.01]) rotate([0,0,p[4]])
                rrect(p[2], p[3], min(p[2],p[3])*0.2, pad_h);
        for (j = xlr_joints)                             // long XLR solder pads (along board)
            if (j[4] == 1)
                translate([j[0], j[1], board_t - 0.01])
                    rrect(j[2], j[3], min(j[2], j[3]) * 0.15, pad_h);
            else
                translate([j[0], j[1], -pad_h + 0.01])
                    rrect(j[2], j[3], min(j[2], j[3]) * 0.15, pad_h);
    }}
    // drill the capsule through-holes
    for (h = tht_pads)
        translate([h[0], h[1], -1]) cylinder(d=h[2], h=board_t + 6);
}}
"""
    open(SCAD, "w").write(scad)
    print("Wrote", SCAD)
    print("  front pads %d, back pads %d, XLR 5mm joints %d, through-holes %d, "
          "bodies %d, traces %d, vias %d"
          % (len(front), len(back), len(xlr), len(tht), len(bodies), len(tracks), len(vias)))

    print("Rendering STL with OpenSCAD ...")
    subprocess.run([OPENSCAD, "-o", STL, SCAD], check=True)
    print("Wrote", STL, "(%.1f KB)" % (os.path.getsize(STL) / 1024.0))


if __name__ == "__main__":
    main()
