"""Compose the animated ENGRAM logo GIF from render-banner.mjs frames.

    node render-banner.mjs --gif && python compose-gif.py

Draws the CHARACTERS themselves (halftone shading, thin shadow lines)
rather than filled rectangles - that is what gives the standalone.html
page its pixel-grain look; block fills would read as too smooth.
Colors follow the variant's palette: violet letters, grey rounded
shadow, a bright lavender sweep for the glint.
"""
from PIL import Image, ImageDraw, ImageFont
import glob
import os

W, H = 1200, 480
BG = (14, 16, 18)
VIOLET = (124, 111, 240)     # letters  #7c6ff0
GLINT = (234, 231, 255)      # the recall sweep
SHADOW = (48, 54, 61)        # rounded drop shadow  #30363d

COLORS = {"▓": VIOLET, "█": GLINT}   # halftone letters, solid glint
SHADOW_CHARS = set("╮╯│╰─")

font = ImageFont.truetype("consola.ttf", 34)
probe = ImageDraw.Draw(Image.new("RGB", (10, 10)))
b = probe.textbbox((0, 0), "▓", font=font)
cw, ch = b[2] - b[0], b[3] - b[1]

lines = open("frames/f000.txt", encoding="utf-8").read().splitlines()
COLS = max(len(l) for l in lines)
ROWS = len(lines)
scale = min(1.0, (W - 80) / (COLS * cw))
if scale < 1.0:
    font = ImageFont.truetype("consola.ttf", max(10, int(34 * scale)))
    b = probe.textbbox((0, 0), "▓", font=font)
    cw, ch = b[2] - b[0], b[3] - b[1]

X0 = (W - COLS * cw) // 2
Y0 = (H - ROWS * ch) // 2

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
            draw.text((X0 + x * cw, Y0 + y * ch), c, font=font, fill=col)
    frames.append(img)

out = "../docs/assets/engram-logo.gif"
os.makedirs(os.path.dirname(out), exist_ok=True)
frames[0].save(out, save_all=True, append_images=frames[1:],
               duration=40, loop=0, optimize=True)
print(f"saved {out}: {os.path.getsize(out) // 1024} KB, {len(frames)} frames")
# static frame for contexts where GIFs do not play
frames[0].save("../docs/assets/engram-logo.png")
