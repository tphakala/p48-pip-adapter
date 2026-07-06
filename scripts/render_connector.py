#!/usr/bin/env python3
"""
Render images/board_with_connector.png: the routed board plugged into a real
3-pin XLR connector.

The board is exported to GLB by kicad-cli; the connector is a third-party model
you supply locally in reference/ (NOT redistributed with this repo -- see
reference/SOURCES.txt).  Accepts either a converted reference/xlr_conn.stl or a
reference/*.3mf (auto-converted with tmf2stl.py).  Blender renders the pair on a
transparent film and the result is composited over a light-grey backdrop.

    python scripts/render_connector.py

Tools auto-detected from PATH / common install dirs; override with the
KICAD_CLI and BLENDER environment variables.
"""
import glob
import os
import shutil
import subprocess
import sys
import tempfile

from PIL import Image

import tmf2stl

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BOARD = os.path.join(ROOT, "p48_pip_adapter.kicad_pcb")
REFDIR = os.path.join(ROOT, "reference")
CONN_STL = os.path.join(REFDIR, "xlr_conn.stl")
OUT = os.path.join(ROOT, "images", "board_with_connector.png")
SCENE = os.path.join(ROOT, "scripts", "render_connector_blender.py")
BG = (235, 235, 237)


def find_tool(env, name, *fallbacks):
    p = os.environ.get(env)
    if p and os.path.exists(p):
        return p
    p = shutil.which(name)
    if p:
        return p
    return next((f for f in fallbacks if f and os.path.exists(f)), None)


USER = os.environ.get("USERNAME", "")
KCLI = find_tool("KICAD_CLI", "kicad-cli",
                 r"C:\Users\%s\AppData\Local\Programs\KiCad\10.0\bin\kicad-cli.exe" % USER,
                 r"C:\Program Files\KiCad\10.0\bin\kicad-cli.exe")
BLENDER = find_tool("BLENDER", "blender",
                    r"C:\Program Files\Blender Foundation\Blender 5.1\blender.exe")


def resolve_connector():
    if os.path.exists(CONN_STL):
        return CONN_STL
    tmfs = glob.glob(os.path.join(REFDIR, "*.3mf"))
    if tmfs:
        print("converting", os.path.basename(tmfs[0]), "-> xlr_conn.stl")
        tmf2stl.convert(tmfs[0], CONN_STL)
        return CONN_STL
    sys.exit("No connector model found. Place a 3-pin XLR .3mf (or xlr_conn.stl) "
             "in reference/ -- see reference/SOURCES.txt.")


def main():
    if not KCLI or not BLENDER:
        sys.exit("kicad-cli and Blender are required (set KICAD_CLI / BLENDER).")
    conn = resolve_connector()
    tmp = tempfile.mkdtemp()
    try:
        glb = os.path.join(tmp, "board.glb")
        subprocess.run([KCLI, "pcb", "export", "glb", "-o", glb,
                        "--include-tracks", "--include-pads", "--include-zones",
                        "--include-silkscreen", "--include-soldermask",
                        "--subst-models", "--force", BOARD], check=True)
        raw = os.path.join(tmp, "raw.png")
        subprocess.run([BLENDER, "-b", "-P", SCENE, "--", glb, conn, raw], check=True)
        fg = Image.open(raw).convert("RGBA")
        bg = Image.new("RGBA", fg.size, BG + (255,))
        bg.alpha_composite(fg)
        os.makedirs(os.path.dirname(OUT), exist_ok=True)
        bg.convert("RGB").save(OUT)
        print("wrote", OUT)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
