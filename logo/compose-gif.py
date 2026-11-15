"""Compose the animated ENGRAM logo GIF from render-banner.mjs frames.

    node render-banner.mjs --gif && python compose-gif.py

Colors follow the variant's palette: violet letters, grey rounded
shadow, a bright lavender sweep for the glint.
"""
from PIL import Image, ImageDraw
import glob
import os

W, H = 1200, 480
BG = (14, 16, 18)
VIOLET = (124, 111, 240)     # letters  #7c6ff0
GLINT = (234, 231, 255)      # the recall sweep
SHADOW = (48, 54, 61)        # rounded drop shadow  #30363d
CW, CH = 18, 50             # one character cell
COLS, ROWS = 63, 6
X0 = (W - COLS * CW) // 2
Y0 = (H - ROWS * CH) // 2

COLORS = {"▓": VIOLET, "█": GLINT}
SHADOW_CHARS = set("╮╯│╰─")

files = sorted(glob.glob("frames/f*.txt"))
frames = []
for path in files:
    lines = open(path, encoding="utf-8").read().splitlines()
    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)
    for y, line in enumerate(lines):
        for x, c in enumerate(line):
            col = COLORS.get(c) or (SHADOW if c in SHADOW_CHARS else None)
            if col is None:
                continue
            draw.rectangle(
                [X0 + x * CW, Y0 + y * CH, X0 + (x + 1) * CW - 1, Y0 + (y + 1) * CH - 1],
                fill=col,
            )
    frames.append(img)

out = "../docs/assets/engram-logo.gif"
os.makedirs(os.path.dirname(out), exist_ok=True)
frames[0].save(
    out, save_all=True, append_images=frames[1:],
    duration=40, loop=0, optimize=True,
)
print(f"saved {out}: {os.path.getsize(out) // 1024} KB, {len(frames)} frames")
