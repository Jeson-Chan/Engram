"""Compose the animated ENGRAM logo GIF (v2: gradient + transparent bg).

    node render-banner.mjs --gif && python compose-gif.py

Changes vs v1 (2026-11-21, user feedback):
- Letter color: violet->teal per-row gradient (#7c6ff0 -> #45c4b8,
  the 'memory' variant's primary palette) instead of flat violet.
- Background: fully transparent (was #0e1012 solid).
- Letterform / frame structure / glint sweep: unchanged.
"""
from PIL import Image, ImageDraw, ImageFont
import glob
import os

W, H = 1200, 480
VIOLET = (124, 111, 240)      # top row    #7c6ff0
TEAL = (69, 196, 184)         # bottom row #45c4b8
GLINT = (234, 231, 255)       # the recall sweep
SHADOW = (48, 54, 61)         # drop shadow  #30363d

SHADOW_CHARS = set("╮╯│╰─")  # round-corner box drawing

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


def row_color(y):
    """Per-row violet->teal interpolation (memory variant gradient)."""
    t = y / max(1, ROWS - 1)
    return tuple(int(VIOLET[i] + (TEAL[i] - VIOLET[i]) * t) for i in range(3))


files = sorted(glob.glob("frames/f*.txt"))
frames = []
for path in files:
    lines = open(path, encoding="utf-8").read().splitlines()
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    for y, line in enumerate(lines):
        col = row_color(y)
        for x, c in enumerate(line):
            cp = ord(c)
            if cp == 0x2593:  # halftone letter cell
                draw.text((X0 + x * cw, Y0 + y * ch), c, font=font, fill=col)
            elif cp == 0x2588:  # glint sweep
                draw.text((X0 + x * cw, Y0 + y * ch), c, font=font, fill=GLINT)
            elif c in SHADOW_CHARS:
                draw.text((X0 + x * cw, Y0 + y * ch), c, font=font, fill=SHADOW)
    frames.append(img)

out = "../docs/assets/engram-logo.gif"
os.makedirs(os.path.dirname(out), exist_ok=True)

gif_frames = [f.convert("P", palette=Image.ADAPTIVE, colors=255) for f in frames]
gif_frames[0].save(
    out, save_all=True, append_images=gif_frames[1:],
    duration=40, loop=0, optimize=True, transparency=0,
    disposal=2,
)
print(f"saved {out}: {os.path.getsize(out) // 1024} KB, {len(frames)} frames (gradient + transparent)")

frames[0].save("../docs/assets/engram-logo.png")
print("saved ../docs/assets/engram-logo.png (transparent, gradient)")
