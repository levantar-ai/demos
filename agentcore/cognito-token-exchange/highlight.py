"""Post 05's architecture, with the part Cognito's own token exchange removes marked in red.

Run from this directory: python3 highlight.py [in.png out.png]
By default reads ../05-identity/architecture.png unchanged and writes
removed.png. Any render of post 05's diagram.py works, as the exchange
cluster is found by its fill colour.
"""

import pathlib
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = pathlib.Path(__file__).parent
EXCHANGE_FILL = (0xF3, 0xEE, 0xEE)  # the exchange cluster's bgcolor in agentcore/05-identity/diagram.py
RED = (0xC6, 0x28, 0x28)
LABEL = "REMOVED. Cognito's customer pool now does this exchange itself"
FONT = "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf"

src, out = (sys.argv[1:3] if len(sys.argv) > 2 else (HERE / "../05-identity/architecture.png", HERE / "removed.png"))
im = Image.open(src).convert("RGB")
pixels = np.array(im).astype(int)
ys, xs = np.where((pixels == EXCHANGE_FILL).all(axis=2))
assert len(xs), "the exchange cluster's fill colour is not in this image"
x0, y0, x1, y1 = xs.min(), ys.min(), xs.max(), ys.max()

# The cluster's own title is the first band of ink inside it. Cover it, tint the
# cluster red, then border and relabel it.
ink = (np.abs(pixels[y0:y1, x0:x1] - EXCHANGE_FILL).sum(axis=2) > 60).any(axis=1)
title_end = y0 + next(i for i in range(1, len(ink)) if ink[i - 1] and not ink[i])
draw = ImageDraw.Draw(im)
draw.rectangle((x0 + 4, y0 + 2, x1 - 4, title_end + 4), fill=EXCHANGE_FILL)
tint = Image.new("RGB", im.size, RED)
mask = Image.new("L", im.size, 0)
ImageDraw.Draw(mask).rectangle((x0, y0, x1, y1), fill=40)
im = Image.composite(tint, im, mask)

draw = ImageDraw.Draw(im)
pad, dash, width = 10, 24, 6
left, top, right, bottom = x0 - pad, y0 - pad, x1 + pad, y1 + pad
for x in range(left, right, dash * 2):
    draw.line((x, top, min(x + dash, right), top), fill=RED, width=width)
    draw.line((x, bottom, min(x + dash, right), bottom), fill=RED, width=width)
for y in range(top, bottom, dash * 2):
    draw.line((left, y, left, min(y + dash, bottom)), fill=RED, width=width)
    draw.line((right, y, right, min(y + dash, bottom)), fill=RED, width=width)
size = max(24, (title_end - y0) - 4)  # as tall as the title it replaces
while draw.textlength(LABEL, font=ImageFont.truetype(FONT, size)) > x1 - x0 - 14:
    size -= 1
draw.text((x0 + 14, y0 + 8), LABEL, fill=RED, font=ImageFont.truetype(FONT, size))

im.save(out, optimize=True)
