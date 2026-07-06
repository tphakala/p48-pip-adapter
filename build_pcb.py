"""
Headless PCB builder for the P48 -> 8V PIP adapter.

Runs under KiCad's bundled Python (pcbnew), no GUI required:

    "<KiCad>/bin/python.exe" build_pcb.py

Produces p48_pip_adapter.kicad_pcb from the single source of truth in
netlist.py: standard + custom footprints, real nets, a 4-layer stackup, the
11.1 x 25 mm Edge.Cuts outline and a parametric, collision-checked placement.

ASSEMBLY CONSTRAINT: every component sits on the TOP (F.Cu) side.  The SMD
parts are placed on F.Cu and never flipped; the XLR solder cups and the
capsule are through-hole (inserted from the top).  Inner/bottom copper is used
for routing only.
"""
import json
import os
import sys

import pcbnew

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import netlist as NL

HERE = os.path.dirname(os.path.abspath(__file__))
KICAD_FP_ROOT = r"C:\Users\Tomi\AppData\Local\Programs\KiCad\10.0\share\kicad\footprints"
OUT = os.path.join(HERE, "p48_pip_adapter.kicad_pcb")

MM = pcbnew.FromMM
V = pcbnew.VECTOR2I_MM


# --------------------------------------------------------------------------- #
# custom through-hole footprints (XLR solder cups, capsule)                    #
# --------------------------------------------------------------------------- #
def make_tht_footprint(board, name, pad_map, drill, size):
    fp = pcbnew.FOOTPRINT(board)
    fp.SetReference(name)
    fp.SetAttributes(pcbnew.FP_THROUGH_HOLE)
    fp.SetPosition(V(0, 0))
    for num, (dx, dy) in pad_map.items():
        pad = pcbnew.PAD(fp)
        pad.SetNumber(num)
        pad.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
        pad.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
        pad.SetSize(V(size, size))
        pad.SetDrillSize(V(drill, drill))
        pad.SetLayerSet(pad.PTHMask())
        fp.Add(pad)
        # fp anchor is at origin here, so absolute == footprint-relative;
        # fp.SetPosition() later translates the pads with the anchor.
        pad.SetPosition(V(dx, dy))
    return fp


def _smd_lset(front):
    ls = pcbnew.LSET()
    layers = ((pcbnew.F_Cu, pcbnew.F_Mask, pcbnew.F_Paste) if front
              else (pcbnew.B_Cu, pcbnew.B_Mask, pcbnew.B_Paste))
    for lid in layers:
        ls.AddLayer(lid)
    return ls


def make_xlr_footprint(board):
    """XLR sandwich mount: pins 1,2 as FRONT face pads, pin 3 as a BACK face
    pad, so the thin board edge slides between the Neutrik pins."""
    fp = pcbnew.FOOTPRINT(board)
    fp.SetReference("J1")
    fp.SetAttributes(pcbnew.FP_SMD)
    fp.SetPosition(V(0, 0))
    w, h = NL.XLR_PAD
    for num, (dx, dy, side) in NL.XLR_FACE_PADS.items():
        pad = pcbnew.PAD(fp)
        pad.SetNumber(num)
        pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        pad.SetShape(pcbnew.PAD_SHAPE_ROUNDRECT)
        pad.SetSize(V(w, h))
        pad.SetLayerSet(_smd_lset(side == "F"))
        fp.Add(pad)
        pad.SetPosition(V(dx, dy))
    return fp


def load_std_footprint(board, lib, name):
    fp = pcbnew.FootprintLoad(os.path.join(KICAD_FP_ROOT, lib + ".pretty"), name)
    if fp is None:
        raise RuntimeError("could not load footprint %s:%s" % (lib, name))
    return fp


# --------------------------------------------------------------------------- #
# placement collision check                                                    #
# --------------------------------------------------------------------------- #
def _aabb(table, ref, x, y, rot):
    w, h = table[NL.COMPONENTS[ref][2]]
    if rot % 180 != 0:
        w, h = h, w
    return (x - w / 2.0, y - h / 2.0, x + w / 2.0, y + h / 2.0)


def _overlaps(table, place, margin):
    boxes = {r: _aabb(table, r, *p) for r, p in place.items()}
    bad = []
    refs = list(boxes)
    for i in range(len(refs)):
        for j in range(i + 1, len(refs)):
            ax0, ay0, ax1, ay1 = boxes[refs[i]]
            bx0, by0, bx1, by1 = boxes[refs[j]]
            if (ax0 < bx1 - margin and bx0 < ax1 - margin and
                    ay0 < by1 - margin and by0 < ay1 - margin):
                bad.append((refs[i], refs[j]))
    return boxes, bad


def check_placement(place):
    """Hard-fail on any PAD-copper overlap (a real short); report courtyard
    overlaps (assembly keep-outs) as informational only."""
    boxes, pad_bad = _overlaps(NL.PAD_EXTENT, place, margin=0.125)
    oob = [r for r, (x0, y0, x1, y1) in boxes.items()
           if x0 < 0 or y0 < 0 or x1 > NL.BOARD_W or y1 > NL.BOARD_L]
    if pad_bad or oob:
        raise SystemExit("PAD OVERLAP %s / OUT-OF-BOARD %s" % (pad_bad, oob))
    _, court_bad = _overlaps(NL.COURTYARD, place, margin=0.0)
    return court_bad


# --------------------------------------------------------------------------- #
# build                                                                        #
# --------------------------------------------------------------------------- #
EDGE_KEEPOUT = 0.3      # copper stays >= 0.3 mm from the board edge
EDGE_RULE = 0.25        # DRC copper-to-edge minimum (fab-safe)


def add_edge_keepout(board):
    """Ring of rule areas that forbid tracks/vias within EDGE_KEEPOUT of the
    edge, so Freerouting keeps a fab-safe copper-to-edge margin."""
    W, L, k = NL.BOARD_W, NL.BOARD_L, EDGE_KEEPOUT
    strips = [(0, 0, W, k), (0, L - k, W, L), (0, 0, k, L), (W - k, 0, W, L)]
    ls = pcbnew.LSET()
    for lid in (pcbnew.F_Cu, pcbnew.In1_Cu, pcbnew.In2_Cu, pcbnew.B_Cu):
        ls.AddLayer(lid)
    for (x0, y0, x1, y1) in strips:
        z = pcbnew.ZONE(board)
        z.SetIsRuleArea(True)
        z.SetDoNotAllowTracks(True)
        z.SetDoNotAllowVias(True)
        z.SetDoNotAllowZoneFills(True)
        z.SetLayerSet(ls)
        op = z.Outline()
        op.NewOutline()
        for (x, y) in [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]:
            op.Append(V(x, y))
        board.Add(z)


# KiCad 10 default DRC severities, with courtyards_overlap downgraded: on this
# 11.1 mm board the four 1206 caps' courtyards (assembly keep-out margins, not
# copper) unavoidably overlap.  Copper rules (shorting_items, clearance,
# track_width, copper_edge_clearance, unconnected_items ...) stay as errors.
# A COMPLETE map is written so kicad-cli never repopulates it with defaults.
_SEVERITIES = {
    "annular_width": "error", "clearance": "error", "connection_width": "warning",
    "copper_edge_clearance": "error", "copper_sliver": "warning",
    "courtyards_overlap": "warning", "creepage": "error",
    "diff_pair_gap_out_of_range": "error",
    "diff_pair_uncoupled_length_too_long": "error", "drill_out_of_range": "error",
    "duplicate_footprints": "warning", "extra_footprint": "warning",
    "footprint": "error", "footprint_filters_mismatch": "ignore",
    "footprint_symbol_field_mismatch": "warning",
    "footprint_symbol_mismatch": "warning", "footprint_type_mismatch": "ignore",
    "hole_clearance": "error", "hole_to_hole": "warning",
    "holes_co_located": "warning", "invalid_outline": "error",
    "isolated_copper": "warning", "item_on_disabled_layer": "error",
    "items_not_allowed": "error", "length_out_of_range": "error",
    "lib_footprint_issues": "warning", "lib_footprint_mismatch": "warning",
    "malformed_courtyard": "error", "microvia_drill_out_of_range": "error",
    "mirrored_text_on_front_layer": "warning", "missing_courtyard": "ignore",
    "missing_footprint": "warning", "missing_tuning_profile": "warning",
    "net_conflict": "warning", "nonmirrored_text_on_back_layer": "warning",
    "npth_inside_courtyard": "error", "padstack": "warning",
    "pth_inside_courtyard": "error", "shorting_items": "error",
    "silk_edge_clearance": "warning", "silk_over_copper": "warning",
    "silk_overlap": "warning", "skew_out_of_range": "error",
    "solder_mask_bridge": "error", "starved_thermal": "error",
    "text_height": "warning", "text_on_edge_cuts": "error",
    "text_thickness": "warning", "through_hole_pad_without_hole": "error",
    "too_many_vias": "error", "track_angle": "error",
    "track_dangling": "warning", "track_not_centered_on_via": "ignore",
    "track_on_post_machined_layer": "error", "track_segment_length": "error",
    "track_width": "error", "tracks_crossing": "error",
    "tuning_profile_track_geometries": "ignore", "unconnected_items": "error",
    "unresolved_variable": "error", "via_dangling": "warning",
    "zones_intersect": "error",
}


def patch_project_severities():
    pro = os.path.join(HERE, "p48_pip_adapter.kicad_pro")
    try:
        cfg = json.load(open(pro))
    except (OSError, ValueError):
        return
    ds = cfg.setdefault("board", {}).setdefault("design_settings", {})
    ds["rule_severities"] = dict(_SEVERITIES)
    json.dump(cfg, open(pro, "w"), indent=2)


def main():
    place = NL.placement()
    court_overlaps = check_placement(place)

    board = pcbnew.NewBoard(OUT)
    board.SetCopperLayerCount(4)

    # design rules (used by the Specctra DSN export -> Freerouting)
    bds = board.GetDesignSettings()
    bds.m_TrackMinWidth = MM(0.13)
    bds.m_CopperEdgeClearance = MM(EDGE_RULE)
    for setter in ("SetBoardThickness",):          # thin board (0.8 mm)
        if hasattr(bds, setter):
            getattr(bds, setter)(MM(NL.BOARD_T))
    ns = bds.m_NetSettings
    dnc = ns.GetDefaultNetclass()
    dnc.SetTrackWidth(MM(0.15))     # 0.15 mm handles >0.3 A; ample for ~3 mA
    dnc.SetClearance(MM(0.125))     # >= JLCPCB/PCBWay standard 4-layer min
    dnc.SetViaDiameter(MM(0.6))
    dnc.SetViaDrill(MM(0.3))

    # nets
    nets = {}
    for name in NL.NETS:
        n = pcbnew.NETINFO_ITEM(board, name)
        board.Add(n)
        nets[name] = n

    # footprints
    fps = {}
    for ref, (value, _sym, (lib, fpname)) in NL.COMPONENTS.items():
        if lib == "custom" and fpname == "XLR_SolderCup":
            fp = make_xlr_footprint(board)
        elif lib == "custom" and fpname == "MIC_2pad":
            fp = make_tht_footprint(board, ref, NL.MIC_PADS, NL.MIC_DRILL, NL.MIC_SIZE)
        else:
            fp = load_std_footprint(board, lib, fpname)
            board.Add(fp)
        fp.SetReference(ref)
        fp.SetValue(value)
        # Silkscreen refdes/value are illegible and overlapping on an 11 mm
        # board -> hide them for a clean silk layer (assembly uses the
        # pick-and-place + BOM files instead).
        fp.Reference().SetVisible(False)
        fp.Value().SetVisible(False)
        x, y, rot = place[ref]
        fp.SetPosition(V(x, y))
        fp.SetOrientationDegrees(rot)
        # keep everything on the top side (single-sided assembly)
        if fp.IsFlipped():
            fp.Flip(fp.GetPosition(), False)
        fps[ref] = fp
        if lib == "custom":
            board.Add(fp)

    # assign pads to nets
    for netname, conns in NL.NETS.items():
        for ref, pad_num in conns:
            pad = fps[ref].FindPadByNumber(pad_num)
            if pad is None:
                raise SystemExit("no pad %s on %s" % (pad_num, ref))
            pad.SetNet(nets[netname])

    # board outline (Edge.Cuts)
    edge = board.GetLayerID("Edge.Cuts")
    W, L = NL.BOARD_W, NL.BOARD_L
    for (x1, y1, x2, y2) in [(0, 0, W, 0), (W, 0, W, L), (W, L, 0, L), (0, L, 0, 0)]:
        seg = pcbnew.PCB_SHAPE(board)
        seg.SetShape(pcbnew.SHAPE_T_SEGMENT)
        seg.SetStart(V(x1, y1))
        seg.SetEnd(V(x2, y2))
        seg.SetLayer(edge)
        seg.SetWidth(MM(0.1))
        board.Add(seg)

    add_edge_keepout(board)

    board.BuildListOfNets()
    board.Save(OUT)
    patch_project_severities()

    # report
    print("Saved:", OUT)
    print("Copper layers:", board.GetCopperLayerCount())
    print("Footprints:", len(fps), "| all on top:",
          not any(fp.IsFlipped() for fp in fps.values()))
    print("Nets:", len(NL.NETS), "->", sorted(NL.NETS))
    print("Pad-overlap check: PASS (no shorts) | courtyard overlaps:",
          len(court_overlaps), "(accepted, silk keep-out margins)")


if __name__ == "__main__":
    main()
