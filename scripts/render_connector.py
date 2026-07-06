#!/usr/bin/env python3
"""
Render images/board_with_connector.png: the routed board slotted into a bare
3-pin XLR pin insert, showing the sandwich mount -- pins 1 & 2 on the front
(component) face, pin 3 on the back.

The board is exported to GLB by kicad-cli; the pin insert + three gold pins are
modelled in Blender at the board's real XLR-pad positions (netlist.py), so no
third-party connector model is needed.  (The real Neutrik NC3MXX STEP is one
fused solid whose pins can't be cleanly isolated, so the pins are modelled.)
Blender renders on a transparent film and the result is composited over grey.

    python scripts/render_connector.py

Tools auto-detected from PATH / common install dirs; override with KICAD_CLI /
BLENDER.  Camera via AZ / EL env vars.
"""
import os
import shutil
import subprocess
import sys
import tempfile

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BOARD = os.path.join(ROOT, "p48_pip_adapter.kicad_pcb")
OUT = os.path.join(ROOT, "images", "board_with_connector.webp")
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


def main():
    if not KCLI or not BLENDER:
        sys.exit("kicad-cli and Blender are required (set KICAD_CLI / BLENDER).")
    tmp = tempfile.mkdtemp()
    try:
        glb = os.path.join(tmp, "board.glb")
        subprocess.run([KCLI, "pcb", "export", "glb", "-o", glb,
                        "--include-tracks", "--include-pads", "--include-zones",
                        "--include-silkscreen", "--include-soldermask",
                        "--subst-models", "--force", BOARD], check=True)
        raw = os.path.join(tmp, "raw.png")
        subprocess.run([BLENDER, "-b", "-P", SCENE, "--", glb, raw], check=True)
        fg = Image.open(raw).convert("RGBA")
        bg = Image.new("RGBA", fg.size, BG + (255,))
        bg.alpha_composite(fg)
        os.makedirs(os.path.dirname(OUT), exist_ok=True)
        bg.convert("RGB").save(OUT, "WEBP", quality=90, method=6)
        print("wrote", OUT)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
