#!/usr/bin/env python3
"""
Simulate and plot the adapter's frequency response, into the ultrasonic band.

Like the assertion harness (run.ps1 / gen_deck.py) this derives everything from
../netlist.py -- the single source of truth -- so the figure can never drift
from the board.  It reuses gen_deck's component cards and phantom-power harness,
runs two AC sweeps (10 Hz .. 384 kHz -- the audio band plus the ultrasonic range
up to the 192 kHz Nyquist of a 384 kHz sample rate, relevant to e.g. bat
recording) in ngspice, and draws:

    1. differential voltage gain  (capsule output node -> P2-P3), dB
    2. output impedance |Zout| at pin 2 (adapter source impedance), ohm

Output: ../images/frequency_response.webp  (referenced from README.md).

Usage:
    python plot_response.py            # writes ../images/frequency_response.webp
Environment:
    NGSPICE   override the ngspice executable path (else PATH / known locations)
"""

import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gen_deck as G  # noqa: E402  (component_cards + HARNESS, from netlist.py)

OUT_IMG = os.path.join(HERE, "..", "images", "frequency_response.webp")
FMIN, FMAX = 10.0, 384.0e3        # deep bass .. 384 kHz (top audio sample rate)
AUDIO_LO, AUDIO_HI = 20.0, 20000.0

# ---- palette (data-viz skill reference instance, light surface) --------------
SURFACE   = "#fcfcfb"
INK       = "#0b0b0b"
INK2      = "#52514e"
MUTED     = "#898781"
GRID      = "#e1e0d9"
AXIS      = "#c3c2b7"
GAIN_C    = "#2a78d6"   # slot 1 blue
ZOUT_C    = "#4a3aa7"   # slot 5 violet (CVD-distinct from blue on light)
BAND_FILL = "#f0efec"   # neutral wash for the audio band


def ngspice_exe():
    env = os.environ.get("NGSPICE")
    if env and os.path.exists(env):
        return env
    for name in ("ngspice_con", "ngspice_con.exe", "ngspice", "ngspice.exe"):
        p = shutil.which(name)
        if p:
            return p
    for c in (
        os.path.expanduser("~/tools/ngspice-46/Spice64/bin/ngspice_con.exe"),
        os.path.join(os.environ.get("LOCALAPPDATA", ""),
                     "Programs/ngspice/Spice64/bin/ngspice_con.exe"),
    ):
        if os.path.exists(c):
            return c
    sys.exit("ngspice not found -- set NGSPICE or add it to PATH (see README).")


def build_deck():
    """Circuit + harness from netlist.py, plus a two-sweep .control block."""
    body = [
        ".include models/zener_bzx84c8v2.lib",
        ".include models/bjt_mmbt390x.lib",
        ".include models/jfet_j201.lib",
        "* ---- circuit (generated from netlist.py via gen_deck) ----",
        *G.component_cards(),
        "",
        G.HARNESS,
    ]
    ctrl = f""".control
set noaskquit
set numdgt=7
* 1. differential gain: capsule output node (MICOUT) -> differential (P2-P3)
ac dec 80 {FMIN:g} {FMAX:g}
let gmag = db((v(P2)-v(P3))/v(MICOUT))
wrdata _gain.data gmag
* 2. output impedance at pin 2: isolate the adapter's own source Z (as test 2
*    of the assertion harness) -- open the phantom feed, preamp shunt and cable
*    cap off P2, hold Q2's DC bias with a current source, inject 1 A AC into P2.
alter RF2   = 1e12
alter RINP  = 1e12
alter CCB2  = 1e-15
alter IBIAS dc = 2.59m
alter IZT   ac = 1
ac dec 80 {FMIN:g} {FMAX:g}
let zmag = vm(P2)
wrdata _zout.data zmag
.endc
.end
"""
    return "\n".join(body) + ctrl


def read_xy(path, ycol=1):
    """Read an ngspice wrdata file: columns [freq, value, ...]."""
    xs, ys = [], []
    with open(path) as f:
        for line in f:
            parts = line.split()
            if len(parts) < 2:
                continue
            xs.append(float(parts[0]))
            ys.append(float(parts[ycol]))
    return xs, ys


def _at(xs, ys, f):
    """Linear-in-log interp of ys at frequency f."""
    import math
    lf = math.log10(f)
    for i in range(1, len(xs)):
        if xs[i] >= f:
            l0, l1 = math.log10(xs[i - 1]), math.log10(xs[i])
            t = (lf - l0) / (l1 - l0) if l1 != l0 else 0.0
            return ys[i - 1] + t * (ys[i] - ys[i - 1])
    return ys[-1]


def _corner(xs, ys, mid, side):
    """Frequency where gain first falls to mid-3 dB scanning out from 1 kHz.

    Returns None if the band edge is outside the swept range (e.g. the LF
    corner sits below FMIN, as it does with the CB2/CB3 bypass).
    """
    import math
    tgt = mid - 3.0
    ref = min(range(len(xs)), key=lambda i: abs(math.log10(xs[i]) - 3.0))
    seq = range(ref + 1, len(xs)) if side == "hi" else range(ref - 1, -1, -1)
    prev = ref
    for i in seq:
        if ys[i] <= tgt:
            a, b = ys[prev], ys[i]
            t = (tgt - a) / (b - a) if b != a else 0.0
            return 10 ** (math.log10(xs[prev]) + t *
                          (math.log10(xs[i]) - math.log10(xs[prev])))
        prev = i
    return None


def main():
    # --- run ngspice from sim/ so the relative .include paths resolve ----------
    deck = os.path.join(HERE, "_resp.cir")
    with open(deck, "w", newline="\n") as f:
        f.write(build_deck())
    ng = ngspice_exe()
    print(f"== ngspice: {ng} ==")
    subprocess.run([ng, "-b", "_resp.cir"], cwd=HERE, check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    fg, gain = read_xy(os.path.join(HERE, "_gain.data"))
    fz, zout = read_xy(os.path.join(HERE, "_zout.data"))

    mid_gain = _at(fg, gain, 1000.0)
    mid_zout = _at(fz, zout, 1000.0)
    f_lo = _corner(fg, gain, mid_gain, "lo")
    f_hi = _corner(fg, gain, mid_gain, "hi")

    # --- plot -----------------------------------------------------------------
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import LogLocator, FuncFormatter

    plt.rcParams.update({
        "font.family": "DejaVu Sans", "font.size": 11,
        "axes.edgecolor": AXIS, "axes.labelcolor": INK2,
        "xtick.color": MUTED, "ytick.color": MUTED,
        "figure.facecolor": SURFACE, "axes.facecolor": SURFACE,
    })
    fig, (ax1, ax2) = plt.subplots(
        2, 1, figsize=(8.4, 6.6), sharex=True, dpi=200,
        gridspec_kw={"height_ratios": [1, 1], "hspace": 0.12})

    def fmt_hz(x, _):
        if x >= 1e6:
            return f"{x/1e6:g} MHz"
        if x >= 1e3:
            return f"{x/1e3:g} kHz"
        return f"{x:g} Hz"

    for ax in (ax1, ax2):
        ax.set_xscale("log")
        ax.set_xlim(FMIN, FMAX)
        ax.grid(True, which="major", color=GRID, lw=0.8)
        ax.grid(True, which="minor", color=GRID, lw=0.4, alpha=0.6)
        ax.set_axisbelow(True)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
        # audio band + ultrasonic orientation
        ax.axvspan(AUDIO_LO, AUDIO_HI, color=BAND_FILL, zorder=0)
        ax.axvline(AUDIO_HI, color=AXIS, lw=1.0, ls=(0, (4, 3)))

    # panel 1: differential gain
    ax1.plot(fg, gain, color=GAIN_C, lw=2.2, solid_capstyle="round")
    ax1.axhline(mid_gain, color=MUTED, lw=0.8, ls=(0, (2, 3)))
    ax1.set_ylabel("differential gain  (dB)", color=INK2)
    ax1.set_ylim(min(gain) - 1.5, max(2.0, max(gain) + 1.5))
    ax1.set_title("Simulated frequency response: P48 → 8 V PIP adapter",
                  color=INK, fontsize=13, fontweight="bold", loc="left", pad=10)
    ax1.annotate(f"{mid_gain:+.2f} dB midband  (near-unity buffer)",
                 xy=(1000, mid_gain), xytext=(2600, mid_gain + 1.15),
                 color=GAIN_C, fontsize=10, fontweight="bold", ha="left")
    top_droop = mid_gain - gain[-1]
    ax1.annotate(f"circuit flat into the ultrasonic\n(−{top_droop:.1f} dB at "
                 f"{FMAX/1e3:.0f} kHz, usable for bat calls)",
                 xy=(fg[-1], gain[-1]), xytext=(6.0e3, gain[-1] - 2.0),
                 color=INK2, fontsize=9, va="center", ha="left",
                 arrowprops=dict(arrowstyle="-", color=MUTED, lw=0.8))
    # the LF −3 dB corner is intentionally below the swept range (CB2/CB3 bypass)
    ax1.annotate("gentle sub-50 Hz roll-off\n(CB2/CB3 emitter bypass)",
                 xy=(22, _at(fg, gain, 22)), xytext=(10.5, min(gain) + 0.3),
                 color=INK2, fontsize=9, va="bottom", ha="left",
                 arrowprops=dict(arrowstyle="->", color=MUTED, lw=0.9))

    # panel 2: output impedance
    ax2.plot(fz, zout, color=ZOUT_C, lw=2.2, solid_capstyle="round")
    ax2.set_yscale("log")
    ax2.set_ylabel("output impedance  |Z|  (Ω)", color=INK2)
    ax2.set_ylim(40, 2000)
    ax2.yaxis.set_major_formatter(FuncFormatter(lambda y, _: f"{y:g}"))
    ax2.annotate(f"{mid_zout:.0f} Ω in-band",
                 xy=(1000, mid_zout), xytext=(1400, mid_zout * 1.7),
                 color=ZOUT_C, fontsize=10, fontweight="bold")
    ax2.set_xlabel("frequency", color=INK2)
    ax2.xaxis.set_major_locator(LogLocator(base=10))
    ax2.xaxis.set_major_formatter(FuncFormatter(fmt_hz))

    # shared "audio band" / "ultrasonic" labels on the top axis
    band_c = (AUDIO_LO * AUDIO_HI) ** 0.5
    ax1.annotate("audio band  (20 Hz – 20 kHz)",
                 xy=(band_c, 1.004), xycoords=("data", "axes fraction"),
                 ha="center", va="bottom", color=MUTED, fontsize=9)
    ax1.text(1.05e5, ax1.get_ylim()[1] - 0.55, "ultrasonic", color=MUTED,
             fontsize=9, style="italic", ha="center", va="top")

    fig.text(0.10, 0.036,
             "ngspice AC sweep of the rev-E netlist (single source of truth).  "
             "Gain: differential output (pins 2–3) referred to the capsule "
             "output node.",
             color=MUTED, fontsize=8, ha="left", va="bottom")
    fig.text(0.10, 0.013,
             "|Z|: adapter source impedance at pin 2.  The sub-50 Hz roll-off is "
             "the CB2/CB3 emitter bypass (intended for this use case).",
             color=MUTED, fontsize=8, ha="left", va="bottom")

    fig.subplots_adjust(left=0.1, right=0.975, top=0.9, bottom=0.145)

    tmp_png = os.path.join(HERE, "_response.png")
    fig.savefig(tmp_png)
    plt.close(fig)

    # --- PNG -> WebP (repo convention) ----------------------------------------
    from PIL import Image
    os.makedirs(os.path.dirname(OUT_IMG), exist_ok=True)
    Image.open(tmp_png).convert("RGB").save(
        OUT_IMG, "WEBP", quality=90, method=6)

    for f in ("_resp.cir", "_gain.data", "_zout.data", "_response.png"):
        p = os.path.join(HERE, f)
        if os.path.exists(p):
            os.remove(p)

    print(f"midband gain = {mid_gain:+.2f} dB | in-band Zout = {mid_zout:.0f} ohm")
    lo_txt = f"{f_lo:.1f} Hz" if f_lo else "< 10 Hz (below sweep, by design)"
    print(f"LF -3 dB corner = {lo_txt}")
    print(f"droop at {FMAX/1e3:.0f} kHz = -{mid_gain - gain[-1]:.2f} dB "
          f"(HF -3 dB corner is beyond the plotted range)")
    print(f"wrote {os.path.relpath(OUT_IMG, HERE)}")


if __name__ == "__main__":
    main()
