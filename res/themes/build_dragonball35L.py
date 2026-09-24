# Build DragonBall35H: DragonBall5inch scaled to the 3.5" display in LANDSCAPE.
# Physical panel 480x320 (driver rotates rev-A LCD). Uniform 0.6 scale
# (800x480 -> 480x288), +16px vertical centering, letterboxed bg, CJK-safe
# date/time fonts, orientation landscape.
import re
from PIL import Image

SRCTHEME = "res/themes/DragonBall5inch/theme.yaml"
SRCCanvas = (800, 480)
SCALE = 0.60
CANVAS = (480, 320)
Y_OFF = (320 - round(480 * SCALE)) // 2  # 16
OUTDIR = "res/themes/DragonBall35H"

lines = open(SRCTHEME).readlines()
out = []
in_static_images = False
for L in lines:
    s = L.rstrip("\n")
    if "static_images:" in s:
        in_static_images = True
    elif re.match(r"^\S+:", s) and "static_images" not in s:  # top-level key ends block
        in_static_images = False
    m = re.match(r"^(\s*)(X|Y|WIDTH|HEIGHT|RADIUS|FONT_SIZE|AXIS_FONT_SIZE)(\s*:\s*)(-?\d+(?:\.\d+)?)(.*)$", s)
    if m:
        indent, key, sep, val, rest = m.groups()
        v = float(val)
        if key == "WIDTH":
            nv = round(v * SCALE)
        elif key == "HEIGHT":
            nv = round(v * SCALE)
        elif key == "X" or key == "RADIUS":
            nv = round(v * SCALE)
        elif key == "Y":
            nv = round(v * SCALE) + (0 if in_static_images else Y_OFF)
        else:
            nv = max(1, round(v * SCALE))
        out.append(f"{indent}{key}{sep}{int(nv)}{rest}")
    else:
        out.append(s)
txt = "\n".join(out) + "\n"

# Letterbox background blits full canvas at origin.
txt = re.sub(
    r"(BACKGROUND:[^\n]*\n\s*PATH:[^\n]*\n\s*)X\s*:\s*\d+(\s*\n\s*)Y\s*:\s*\d+(\s*\n\s*)WIDTH\s*:\s*\d+(\s*\n\s*)HEIGHT\s*:\s*\d+",
    rf"\g<1>X: 0\g<2>Y: 0\g<3>WIDTH: {CANVAS[0]}\g<4>HEIGHT: {CANVAS[1]}",
    txt,
)
txt = txt.replace('DISPLAY_SIZE: 5"', 'DISPLAY_SIZE: 3.5"')
txt = txt.replace('DISPLAY_ORIENTATION: landscape', 'DISPLAY_ORIENTATION: landscape')

# CJK-safe date/time fonts (zh locale renders 上午/下午/年/月/日)
import pathlib, os
os.makedirs(OUTDIR, exist_ok=True)
lines2 = txt.splitlines(keepends=True)
out2 = []
date_block = 0
for L in lines2:
    out2.append(L)
    if L.startswith("  DATE:"):
        date_block = 1
    elif date_block and re.match(r"^  [A-Z]", L):
        date_block = 0
    if date_block and re.match(r"^\s*FONT:\s*jetbrains", L):
        out2[-1] = re.sub(r"jetbrains[^\n]+", "GlowSansSC-Compressed/GlowSansSC-Compressed-Bold.otf", L)
open(f"{OUTDIR}/theme.yaml", "w").write("".join(out2))

# Background: uniform 0.6 into 480x320 canvas, centered.
src = Image.open("res/themes/DragonBall5inch/background.png").convert("RGB")
img = src.resize((round(800*SCALE), round(480*SCALE)), Image.LANCZOS)
canvas = Image.new("RGB", CANVAS, (0, 0, 0))
canvas.paste(img, (0, Y_OFF))

# Erase the baked-in "VOLUME" word in the top band. Pixel probe of the scaled
# canvas locates the cream letters at x 108..159, y 26..34; the flat-orange
# strip 20px below is clean, so clone it over the word (small margin).
clean = canvas.crop((104, 46, 163, 61))
canvas.paste(clean, (104, 24))
canvas.save(f"{OUTDIR}/background.png")
print(f"{OUTDIR} built: canvas {CANVAS}, scale {SCALE}, Y_OFF {Y_OFF}")
print("date fonts:", "GlowSansSC" in open(f"{OUTDIR}/theme.yaml").read().split("  DATE:")[1].split("\n  [A-Z")[0].replace("STATS","") if "DATE" in open(f"{OUTDIR}/theme.yaml").read() else "?")
# sanity: report date/time font lines
t = open(f"{OUTDIR}/theme.yaml").read()
for i, L in enumerate(t.splitlines()):
    if "GlowSansSC" in L:
        print("font line:", L.strip())
