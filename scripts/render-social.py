#!/usr/bin/env python3
"""Render a 1200x627 social card (LinkedIn link format) for a post.

Usage: python3 scripts/render-social.py agentcore/01-first-agent [square]

Reads the post title from POST.md, composes the demo's architecture
diagram onto a dark branded canvas, and writes social.png into the demo
directory. Run from the repo root; render-post.py copies the card to
docs/ and references it as og:image.
"""

import os
import pathlib
import re
import subprocess
import sys

from PIL import Image, ImageDraw, ImageFont

W, H = 1200, 627  # overridden to 1200x1200 when "square" is passed
BG = (11, 17, 32)        # site background #0b1120
ACCENT = (34, 211, 238)  # site accent #22d3ee
MUTED = (147, 164, 195)  # site muted #93a4c3
FG = (231, 237, 247)     # site foreground #e7edf7

FONT_DIR = "/usr/share/fonts/truetype/dejavu"


def font(name, size):
    return ImageFont.truetype(f"{FONT_DIR}/{name}.ttf", size)


def wrap(draw, text, fnt, max_width):
    words, lines, line = text.split(), [], ""
    for w in words:
        trial = f"{line} {w}".strip()
        if draw.textlength(trial, font=fnt) <= max_width:
            line = trial
        else:
            lines.append(line)
            line = w
    lines.append(line)
    return lines


def main():
    global W, H
    square = len(sys.argv) > 2 and sys.argv[2] == "square"
    if square:
        W, H = 1200, 1200
    demo = pathlib.Path(sys.argv[1].rstrip("/"))
    title = re.match(r"# (.+)\n", (demo / "POST.md").read_text()).group(1)

    # Re-render the diagram with boosted fonts for feed legibility
    env = dict(os.environ, DIAGRAM_FONT_BOOST="8", DIAGRAM_OUT="architecture-social")
    subprocess.run([sys.executable, "diagram.py"], cwd=demo, env=env, check=True)

    canvas = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(canvas)

    # header: series label, title, accent rule
    draw.text((60, 38), "LEVANTAR — AGENTCORE SERIES", font=font("DejaVuSans-Bold", 17), fill=ACCENT)
    title_font = font("DejaVuSans-Bold", 34)
    y = 74
    for line in wrap(draw, title, title_font, W - 120)[:2]:
        draw.text((60, y), line, font=title_font, fill=FG)
        y += 44
    draw.rectangle([60, y + 8, 180, y + 12], fill=ACCENT)

    # diagram on a white rounded card filling the lower area
    top = y + 34
    card = [40, top, W - 40, H - 40]
    draw.rounded_rectangle(card, radius=18, fill=(255, 255, 255))
    art = Image.open(demo / "architecture-social.png").convert("RGB")
    (demo / "architecture-social.png").unlink()
    max_w, max_h = card[2] - card[0] - 40, card[3] - card[1] - 30
    scale = min(max_w / art.width, max_h / art.height)
    art = art.resize((int(art.width * scale), int(art.height * scale)), Image.LANCZOS)
    canvas.paste(art, (card[0] + (card[2] - card[0] - art.width) // 2,
                       card[1] + (card[3] - card[1] - art.height) // 2))

    draw.text((W - 60 - draw.textlength("levantar.ai", font=font("DejaVuSans-Bold", 16)), 44),
              "levantar.ai", font=font("DejaVuSans-Bold", 16), fill=MUTED)

    out = demo / ("social-square.png" if square else "social.png")
    canvas.save(out)
    print(f"rendered {out}")


if __name__ == "__main__":
    main()
