"""
Headless fab-output export: Gerbers (X2) + Excellon drill -> a single zip ready
to upload to PCBWay / JLCPCB.  Runs with the plain system Python (it only
shells out to kicad-cli); no KiCad GUI required:

    python export_gerbers.py

Layers: F.Cu, In1.Cu (GND), In2.Cu (PWR), B.Cu, both silk, both mask, edge.
"""
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
KCLI = r"C:\Users\Tomi\AppData\Local\Programs\KiCad\10.0\bin\kicad-cli.exe"
BOARD = os.path.join(HERE, "p48_pip_adapter.kicad_pcb")
OUTDIR = os.path.join(HERE, "Gerbers_PCBWay")
ZIP = os.path.join(HERE, "P48_Adapter_PCBWay")

LAYERS = ",".join([
    "F.Cu", "In1.Cu", "In2.Cu", "B.Cu",
    "F.SilkS", "B.SilkS", "F.Mask", "B.Mask", "Edge.Cuts",
])


def run(*args):
    print("$", " ".join(os.path.basename(a) if a == KCLI else a for a in args))
    subprocess.run(args, check=True)


def main():
    if os.path.isdir(OUTDIR):
        shutil.rmtree(OUTDIR)
    os.makedirs(OUTDIR)

    # Gerbers (X2, soldermask subtracted from silk)
    run(KCLI, "pcb", "export", "gerbers",
        "--output", OUTDIR + os.sep,
        "--layers", LAYERS,
        "--subtract-soldermask",
        "--use-drill-file-origin",
        BOARD)

    # Excellon drill, PTH/NPTH separated, with a drill map
    run(KCLI, "pcb", "export", "drill",
        "--output", OUTDIR + os.sep,
        "--format", "excellon",
        "--excellon-units", "mm",
        "--excellon-separate-th",
        "--generate-map", "--map-format", "gerberx2",
        "--drill-origin", "absolute",
        BOARD)

    if os.path.exists(ZIP + ".zip"):
        os.remove(ZIP + ".zip")
    shutil.make_archive(ZIP, "zip", OUTDIR)

    files = sorted(os.listdir(OUTDIR))
    print("\nGerber/drill files (%d):" % len(files))
    for f in files:
        print("  ", f)
    print("\nZip:", ZIP + ".zip", "(%d bytes)" % os.path.getsize(ZIP + ".zip"))


if __name__ == "__main__":
    sys.exit(main())
