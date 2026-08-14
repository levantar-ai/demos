#!/usr/bin/env python3
"""Render a 1200x630 social card (LinkedIn link format) for a post.

Usage: python3 scripts/render-social.py agentcore/01-first-agent [square]

Reads the post title from POST.md, composes the demo's architecture
diagram onto a branded canvas, and writes social.png into the demo
directory. Run from the repo root; render-post.py copies the card to
docs/ and references it as og:image.

The card is the same object as the ones levantar.ai renders in
tools/build-social-cards.py, so the two read as one family in a feed. Same
dark band, same light-teal eyebrow over a hairline rule, same Inter Tight,
same mark-and-domain footer. What differs is the middle: the site's cards
are text only, these carry the demo's architecture diagram, because the
diagram is the reason to click.
"""

import os
import pathlib
import re
import subprocess
import sys

from fontTools.ttLib import TTFont as FTFont
from fontTools.varLib import instancer
from PIL import Image, ImageChops, ImageDraw, ImageFont

ROOT = pathlib.Path(__file__).resolve().parent.parent
FONT_SRC = ROOT / "scripts/fonts/inter-tight-var.woff2"
FONT_BUILD = ROOT / ".fonts-build"

W, H = 1200, 630  # overridden to 1200x1200 when "square" is passed
MARGIN = 80       # the side margin levantar.ai's own cards use
# Vertical rhythm is tighter than the site's 80. These cards carry artwork as
# well as a title, and on a 630-high canvas an 80px band top and bottom is
# height the diagram cannot spare.
MARGIN_Y = 40

# Tokens lifted from levantar.css, via the site's card renderer.
BG = (11, 19, 21)            # --dark    #0b1315
TITLE_INK = (233, 231, 224)  # --dark-ink   #e9e7e0
MUTED_INK = (167, 176, 177)  # --dark-ink-2 #a7b0b1
ACCENT_LIFT = (127, 197, 194)  # --accent-lift #7fc5c2, the teal the site uses on dark
PAPER = (247, 245, 240)      # --paper   #f7f5f0

EYEBROW = "AgentCore series"
# Smaller than the site's 72-42 ramp: these cards give most of their height to
# the diagram, so the title takes two lines at most and gets out of the way.
TITLE_SIZES = [40, 35, 31, 28]
MAX_TITLE_LINES = 2


def load_fonts():
    """Instance the variable webfont to static TTFs Pillow can open.

    Same trick as the site's tools/build-social-cards.py — we ship woff2,
    which Pillow does not read.
    """
    FONT_BUILD.mkdir(exist_ok=True)
    faces = {}
    for weight, name in ((400, "inter-400"), (600, "inter-600")):
        path = FONT_BUILD / f"{name}.ttf"
        if not path.exists():
            font = instancer.instantiateVariableFont(FTFont(str(FONT_SRC)), {"wght": weight})
            font.flavor = None
            font.save(str(path))
        faces[weight] = path
    return faces


def wrap(draw, text, fnt, max_width):
    lines, line = [], ""
    for word in text.split():
        candidate = f"{line} {word}".strip()
        if draw.textlength(candidate, font=fnt) <= max_width or not line:
            line = candidate
        else:
            lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines


def main():
    global W, H
    square = len(sys.argv) > 2 and sys.argv[2] == "square"
    if square:
        W, H = 1200, 1200
    demo = pathlib.Path(sys.argv[1].rstrip("/"))
    title = re.match(r"# (.+)\n", (demo / "POST.md").read_text()).group(1)

    faces = load_fonts()

    def font(weight, size):
        return ImageFont.truetype(str(faces[weight]), size)

    # Re-render the diagram with boosted fonts for feed legibility
    env = dict(os.environ, DIAGRAM_FONT_BOOST="8", DIAGRAM_OUT="architecture-social")
    subprocess.run([sys.executable, "diagram.py"], cwd=demo, env=env, check=True)

    canvas = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(canvas)
    text_width = W - 2 * MARGIN

    # Eyebrow and its hairline, laid out as the site's cards lay them out.
    draw.text((MARGIN, MARGIN_Y), " ".join(EYEBROW.upper()), font=font(600, 22), fill=ACCENT_LIFT)
    rule_y = MARGIN_Y + 42
    draw.line([(MARGIN, rule_y), (MARGIN + 96, rule_y)], fill=ACCENT_LIFT, width=2)

    # Shrink the title until it fits rather than truncating it — a card that
    # ends mid-word reads as broken, a slightly smaller one does not.
    for size in TITLE_SIZES:
        title_font = font(600, size)
        lines = wrap(draw, title, title_font, text_width)
        if len(lines) <= MAX_TITLE_LINES:
            break
    lines = lines[:MAX_TITLE_LINES]

    leading = round(size * 1.15)
    y = rule_y + 30
    for line in lines:
        draw.text((MARGIN, y), line, font=title_font, fill=TITLE_INK)
        y += leading

    mark_h = 38
    footer_y = H - MARGIN_Y - mark_h

    # Diagram on a paper card sized to the artwork, not to the canvas. Filling
    # the lower area leaves a tall empty panel on the square card, because the
    # diagrams are much wider than they are high.
    top = y + 22
    pad_x, pad_y = 22, 18
    area_w, area_h = W - 2 * MARGIN, footer_y - 22 - top

    art = Image.open(demo / "architecture-social.png").convert("RGB")
    (demo / "architecture-social.png").unlink()
    scale = min((area_w - 2 * pad_x) / art.width, (area_h - 2 * pad_y) / art.height)
    art = art.resize((int(art.width * scale), int(art.height * scale)), Image.LANCZOS)

    # The diagram comes off graphviz on white. Multiplying it over a paper tile
    # turns that white into the site's paper and leaves the strokes and the AWS
    # icon colours where they were, so the card carries no pure white anywhere.
    art = ImageChops.multiply(art, Image.new("RGB", art.size, PAPER))

    # A 2.7:1 diagram on a square canvas leaves slack whatever we do. Splitting
    # it evenly floats the artwork away from its own title, so bias it upward
    # and let the surplus fall above the footer instead.
    card_w, card_h = art.width + 2 * pad_x, art.height + 2 * pad_y
    card_x = (W - card_w) // 2
    card_y = top + round((area_h - card_h) * (0.40 if square else 0.5))
    draw.rounded_rectangle(
        [card_x, card_y, card_x + card_w, card_y + card_h], radius=16, fill=PAPER
    )
    canvas.paste(art, (card_x + pad_x, card_y + pad_y))

    # Footer: the mark and wordmark left, the domain right.
    mark = Image.open(ROOT / "docs/levantar-logo-white.png").convert("RGBA")
    mark = mark.resize((round(mark.width * mark_h / mark.height), mark_h), Image.LANCZOS)
    canvas.paste(mark, (MARGIN, footer_y), mark)
    draw.text((MARGIN + mark.width + 15, footer_y + 4), "Levantar",
              font=font(600, 28), fill=TITLE_INK)

    domain_font = font(400, 22)
    draw.text((W - MARGIN - draw.textlength("levantar.ai", font=domain_font), footer_y + 9),
              "levantar.ai", font=domain_font, fill=MUTED_INK)

    out = demo / ("social-square.png" if square else "social.png")
    canvas.save(out, optimize=True)
    print(f"rendered {out}")


if __name__ == "__main__":
    main()
