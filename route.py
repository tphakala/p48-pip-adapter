"""
Headless autorouting driver: KiCad board -> Specctra DSN -> Freerouting -> SES
-> routed KiCad board.  Runs under KiCad's bundled Python:

    "<KiCad>/bin/python.exe" route.py [max_passes]

Freerouting is ALWAYS run headless: the JVM is started with
-Djava.awt.headless=true (via JAVA_TOOL_OPTIONS) so no GUI window can ever be
created, plus gui.enabled=false is written to freerouting.json as a backstop.

The SES is applied to the board by a small built-in Specctra-SES parser rather
than pcbnew.ImportSpecctraSES (which fails silently on freerouting 2.x output).

A pristine, freshly-built board is regenerated first, because importing routes
onto an already-routed board can leave stale inner-layer traces.
"""
import json
import os
import re
import subprocess
import sys
import tempfile

import pcbnew

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_pcb

HERE = os.path.dirname(os.path.abspath(__file__))
BOARD = os.path.join(HERE, "p48_pip_adapter.kicad_pcb")
DSN = os.path.join(HERE, "p48_pip_adapter.dsn")
SES = os.path.join(HERE, "p48_pip_adapter.ses")
FREEROUTING = r"C:\Users\Tomi\AppData\Local\freerouting\freerouting.exe"
FR_CFG = os.path.join(tempfile.gettempdir(), "freerouting", "freerouting.json")

SES_TO_NM = 100  # (resolution um 10) -> 1 unit = 0.1 um = 100 nm


# --------------------------------------------------------------------------- #
# tiny S-expression reader                                                     #
# --------------------------------------------------------------------------- #
def _sexpr(text):
    toks, i, n = [], 0, len(text)
    while i < n:
        c = text[i]
        if c in "()":
            toks.append(c); i += 1
        elif c.isspace():
            i += 1
        elif c == '"':
            j = text.index('"', i + 1); toks.append(text[i + 1:j]); i = j + 1
        else:
            j = i
            while j < n and not text[j].isspace() and text[j] not in '()"':
                j += 1
            toks.append(text[i:j]); i = j

    def build(pos):
        lst = []; pos += 1
        while toks[pos] != ")":
            if toks[pos] == "(":
                sub, pos = build(pos); lst.append(sub)
            else:
                lst.append(toks[pos]); pos += 1
        return lst, pos + 1

    return build(0)[0]


def _find(node, tag):
    for c in node:
        if isinstance(c, list) and c and c[0] == tag:
            yield c


# --------------------------------------------------------------------------- #
# SES -> board                                                                 #
# --------------------------------------------------------------------------- #
def import_ses(board, ses_path):
    tree = _sexpr(open(ses_path).read())
    routes = next(_find(tree, "routes"))
    netout = next(_find(routes, "network_out"))

    def X(u):
        return int(round(float(u) * SES_TO_NM))

    def Y(u):
        return -int(round(float(u) * SES_TO_NM))

    nets_by_name = {board.GetNetInfo().GetNetItem(i).GetNetname():
                    board.GetNetInfo().GetNetItem(i)
                    for i in range(board.GetNetInfo().GetNetCount())}

    # pre-placed stitch vias (from build_pcb) are already on the board; skip any
    # SES via that re-lists them so they are not doubled (holes co-located).
    existing_vias = [(v.GetPosition().x, v.GetPosition().y)
                     for v in board.GetTracks() if isinstance(v, pcbnew.PCB_VIA)]

    n_tracks = n_vias = 0
    for net in _find(netout, "net"):
        name = net[1]
        netinfo = nets_by_name.get(name)
        for wire in _find(net, "wire"):
            path = next(_find(wire, "path"))
            layer = board.GetLayerID(path[1])
            width = X(path[2])
            coords = path[3:]
            pts = [(X(coords[k]), Y(coords[k + 1]))
                   for k in range(0, len(coords), 2)]
            for a, b in zip(pts, pts[1:]):
                t = pcbnew.PCB_TRACK(board)
                t.SetStart(pcbnew.VECTOR2I(*a))
                t.SetEnd(pcbnew.VECTOR2I(*b))
                t.SetWidth(width)
                t.SetLayer(layer)
                if netinfo:
                    t.SetNet(netinfo)
                board.Add(t); n_tracks += 1
        for via in _find(net, "via"):
            # via = ['via', '<padstack>', x, y]; padstack encodes DDD:ddd_um
            pad = via[1]
            dia, drl = 600000, 300000
            try:
                sz = pad.split("_")[-2] if pad.endswith("_um") else ""
                d, k = pad.split(":") if ":" in pad else ("", "")
                dia = int(pad.split("_")[1].split(":")[0]) * 1000
                drl = int(pad.split(":")[1].split("_")[0]) * 1000
            except Exception:
                pass
            vx, vy = X(via[2]), Y(via[3])
            if any(abs(vx - ex) < 1000 and abs(vy - ey) < 1000
                   for ex, ey in existing_vias):
                continue                       # already placed as a stitch via
            v = pcbnew.PCB_VIA(board)
            v.SetPosition(pcbnew.VECTOR2I(vx, vy))
            v.SetWidth(dia)
            v.SetDrill(drl)
            v.SetViaType(pcbnew.VIATYPE_THROUGH)
            v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
            if netinfo:
                v.SetNet(netinfo)
            board.Add(v); n_vias += 1
    return n_tracks, n_vias


# --------------------------------------------------------------------------- #
# ground planes: confine routing to the outer layers, flood-fill after routing #
# --------------------------------------------------------------------------- #
def confine_routing_to_outer(dsn_path):
    """Relabel the inner copper as Specctra 'power' layers so Freerouting keeps
    signal routing on F.Cu + B.Cu and treats In1/In2 purely as the GND planes
    exported as (plane GND ...).  This is what makes the inner layers stay solid
    reference planes instead of getting chopped up by signal traces."""
    txt = open(dsn_path).read()
    for inner in ("In1.Cu", "In2.Cu"):
        txt = re.sub(r"(\(layer %s\s*\(type )signal" % re.escape(inner),
                     r"\1power", txt)
    open(dsn_path, "w").write(txt)


def _net(board, name):
    ni = board.GetNetInfo()
    for i in range(ni.GetNetCount()):
        n = ni.GetNetItem(i)
        if n.GetNetname() == name:
            return n
    return None


def add_outer_pours(board):
    """Flood F.Cu + B.Cu with GND after routing and refill the inner planes so
    all four layers clear the freshly imported copper.  Completes the on-board
    Faraday cage; the pre-placed stitch vias tie every layer together."""
    gnd = _net(board, "GND")
    build_pcb.add_ground_zone(board, gnd, pcbnew.F_Cu)
    build_pcb.add_ground_zone(board, gnd, pcbnew.B_Cu)
    build_pcb.fill_all_zones(board)


# --------------------------------------------------------------------------- #
# freerouting                                                                  #
# --------------------------------------------------------------------------- #
def force_headless_config():
    try:
        cfg = json.load(open(FR_CFG))
    except (OSError, ValueError):
        cfg = {}
    cfg.setdefault("gui", {})
    cfg["gui"]["enabled"] = False
    cfg["gui"]["dialog_confirmation_timeout"] = 0
    os.makedirs(os.path.dirname(FR_CFG), exist_ok=True)
    json.dump(cfg, open(FR_CFG, "w"), indent=2)


def run_freerouting(max_passes):
    force_headless_config()
    if os.path.exists(SES):
        os.remove(SES)
    env = dict(os.environ)
    # hard guarantee: a headless JVM cannot open any window
    env["JAVA_TOOL_OPTIONS"] = "-Djava.awt.headless=true"
    cmd = [FREEROUTING, "-de", DSN, "-do", SES, "-mp", str(max_passes)]
    print("RUN (headless):", " ".join(cmd))
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=900, env=env)
    for line in proc.stdout.splitlines()[-14:]:
        print(line)
    if not os.path.exists(SES):
        raise SystemExit("Freerouting produced no SES file\n" + proc.stdout[-2000:])


# --------------------------------------------------------------------------- #
def main(max_passes=100):
    build_pcb.main()                       # pristine board: parts + GND planes
    b = pcbnew.LoadBoard(BOARD)
    if not pcbnew.ExportSpecctraDSN(b, DSN):
        raise SystemExit("DSN export failed")
    confine_routing_to_outer(DSN)          # In1/In2 stay solid GND planes

    run_freerouting(max_passes)

    b2 = pcbnew.LoadBoard(BOARD)
    nt, nv = import_ses(b2, SES)
    add_outer_pours(b2)                     # flood F.Cu/B.Cu GND, refill planes
    b2.BuildConnectivity()
    b2.Save(BOARD)

    unrouted = b2.GetConnectivity().GetUnconnectedCount(True)
    print("Routed board saved:", BOARD)
    print("Tracks added: %d | Vias added: %d | Unrouted ratsnest: %d"
          % (nt, nv, unrouted))
    return unrouted


if __name__ == "__main__":
    mp = int(sys.argv[1]) if len(sys.argv) > 1 else 100
    sys.exit(1 if main(mp) else 0)
