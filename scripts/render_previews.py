#!/usr/bin/env python3
"""
Render the preview images in images/ from the routed KiCad board and the
3D-printable fit-test STL.

The board beauty shots (hero / top / bottom) are rendered photorealistically by
kicad-cli's raytracer with a transparent background + floor shadow, then
composited over a light-grey studio backdrop.  The fit-test coupon is rendered
from its STL with Blender (Cycles); that step is skipped if Blender is absent.

Run from the repository root with a normal Python (it only shells out):

    python scripts/render_previews.py

Tools are auto-detected from PATH / common install dirs; override with the
KICAD_CLI and BLENDER environment variables if needed.
"""
import os
import shutil
import subprocess
import sys

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BOARD = os.path.join(ROOT, "p48_pip_adapter.kicad_pcb")
STL = os.path.join(ROOT, "fit_test", "p48_fittest.stl")
IMG = os.path.join(ROOT, "images")
TMP = os.path.join(IMG, "_raw")
BG = (235, 235, 237)  # light-grey studio backdrop (~0.92)

# name -> extra kicad-cli render args
VIEWS = {
    "board_hero": ["--perspective", "--rotate", "-30,0,-22"],
    "board_top": ["--side", "top"],
    "board_bottom": ["--side", "bottom"],
}


def find_tool(env, name, *fallbacks):
    p = os.environ.get(env)
    if p and os.path.exists(p):
        return p
    p = shutil.which(name)
    if p:
        return p
    for f in fallbacks:
        if f and os.path.exists(f):
            return f
    return None


USER = os.environ.get("USERNAME", "")
KCLI = find_tool(
    "KICAD_CLI", "kicad-cli",
    r"C:\Users\%s\AppData\Local\Programs\KiCad\10.0\bin\kicad-cli.exe" % USER,
    r"C:\Program Files\KiCad\10.0\bin\kicad-cli.exe",
)
BLENDER = find_tool(
    "BLENDER", "blender",
    r"C:\Program Files\Blender Foundation\Blender 5.1\blender.exe",
)


def composite(raw, out):
    fg = Image.open(raw).convert("RGBA")
    bg = Image.new("RGBA", fg.size, BG + (255,))
    bg.alpha_composite(fg)
    bg.convert("RGB").save(out)


def render_board():
    if not KCLI:
        sys.exit("kicad-cli not found (set the KICAD_CLI environment variable)")
    os.makedirs(TMP, exist_ok=True)
    for name, extra in VIEWS.items():
        raw = os.path.join(TMP, name + ".png")
        subprocess.run(
            [KCLI, "pcb", "render", "-o", raw,
             "--quality", "high", "--floor",
             "--width", "1600", "--height", "1000",
             "--background", "transparent", *extra, BOARD],
            check=True,
        )
        composite(raw, os.path.join(IMG, name + ".png"))
        print("wrote", os.path.join(IMG, name + ".png"))


def render_fittest():
    if not BLENDER:
        print("Blender not found - skipping fit_test.png (set BLENDER to enable)")
        return
    script = os.path.join(ROOT, "scripts", "render_fittest.py")
    out = os.path.join(IMG, "fit_test.png")
    subprocess.run([BLENDER, "-b", "-P", script, "--", STL, out], check=True)
    print("wrote", out)


def main():
    os.makedirs(IMG, exist_ok=True)
    render_board()
    render_fittest()
    if os.path.isdir(TMP):
        shutil.rmtree(TMP)


if __name__ == "__main__":
    main()
