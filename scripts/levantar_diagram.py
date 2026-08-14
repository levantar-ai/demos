"""House diagram style for the demo posts.

The architecture diagrams in this repo come off graphviz through the
`diagrams` package, which is the right tool when the picture is mostly AWS
service icons. It is the wrong tool when the picture is control flow, because
the palette then belongs to AWS rather than to us and the type is whatever
graphviz found.

This draws that second kind, in the site's own tokens and typeface, so a
diagram about our code looks like it came from levantar.ai. Import it and
compose, see agentcore/03-memory/routing.py for a worked example.

    d = Diagram(1480, 620)
    d.cluster(60, 90, 700, 440, "agent container")
    d.box(90, 130, 300, 64, "startswith(\"remember\")", tone="flame")
    d.arrow((390, 162), (560, 162), "stores the whole prompt")
    d.caption("How a prompt reaches an API call")
    d.save("routing.png")

Coordinates are top-left origin and in pixels. Nothing is laid out for you,
which is deliberate. These diagrams are small enough that hand-placing reads
better than fighting an auto-layout, and it keeps the module to primitives.
"""

import pathlib

from fontTools.ttLib import TTFont as FTFont
from fontTools.varLib import instancer
from PIL import Image, ImageDraw, ImageFont

ROOT = pathlib.Path(__file__).resolve().parent.parent
FONT_SRC = ROOT / "scripts/fonts/inter-tight-var.woff2"
FONT_BUILD = ROOT / ".fonts-build"

# Straight from levantar.css. Keep these in step with the site rather than
# picking something that merely looks close.
PAPER = (247, 245, 240)       # --paper       #f7f5f0
PAPER_WARM = (239, 236, 228)  # --paper-warm  #efece4
INK = (14, 18, 22)            # --ink         #0e1216
INK_2 = (74, 81, 88)          # --ink-2       #4a5158
INK_3 = (101, 108, 114)       # --ink-3       #656c72
TEAL = (13, 82, 87)           # --teal-700    #0d5257
TEAL_DEEP = (8, 58, 62)       # --teal-deep   #083a3e
ACCENT_LIFT = (127, 197, 194)  # --accent-lift #7fc5c2
FLAME = (224, 90, 43)         # --flame-500   #e05a2b
FLAME_100 = (250, 228, 218)   # --flame-100   #fae4da
RULE = (220, 213, 198)        # --rule        #dcd5c6
RULE_STRONG = (198, 189, 169)  # --rule-strong #c6bda9

# Flame is reserved for the one thing the diagram is actually about, per the
# site's colour addendum. Teal is structural and does the rest of the work.
TONES = {
    "default": {"fill": PAPER, "line": RULE_STRONG, "title": INK, "sub": INK_3},
    "accent": {"fill": PAPER_WARM, "line": TEAL, "title": TEAL_DEEP, "sub": INK_2},
    "flame": {"fill": FLAME_100, "line": FLAME, "title": INK, "sub": INK_2},
    "dark": {"fill": TEAL_DEEP, "line": TEAL_DEEP, "title": PAPER, "sub": ACCENT_LIFT},
}

SCALE = 2  # draw at 2x and downsample, since Pillow has no antialiased shapes


def _faces():
    FONT_BUILD.mkdir(exist_ok=True)
    out = {}
    for weight, name in ((400, "inter-400"), (600, "inter-600")):
        path = FONT_BUILD / f"{name}.ttf"
        if not path.exists():
            font = instancer.instantiateVariableFont(FTFont(str(FONT_SRC)), {"wght": weight})
            font.flavor = None
            font.save(str(path))
        out[weight] = path
    return out


class Diagram:
    def __init__(self, width, height, background=PAPER):
        self.w, self.h = width, height
        self._faces = _faces()
        self.image = Image.new("RGB", (width * SCALE, height * SCALE), background)
        self.draw = ImageDraw.Draw(self.image)

    def font(self, size, weight=400):
        return ImageFont.truetype(str(self._faces[weight]), size * SCALE)

    def _s(self, *values):
        return [v * SCALE for v in values]

    def text(self, x, y, value, size=14, weight=400, colour=INK, anchor="la"):
        self.draw.text(self._s(x, y), value, font=self.font(size, weight),
                       fill=colour, anchor=anchor)

    def width_of(self, value, size=14, weight=400):
        return self.draw.textlength(value, font=self.font(size, weight)) / SCALE

    def box(self, x, y, w, h, title, subtitle=None, tone="default", mono=False):
        """A rounded panel with a title and an optional second line."""
        t = TONES[tone]
        self.draw.rounded_rectangle(self._s(x, y, x + w, y + h), radius=8 * SCALE,
                                    fill=t["fill"], outline=t["line"], width=SCALE)
        size = 13 if mono else 14.5
        if subtitle:
            self.text(x + w / 2, y + h / 2 - 11, title, size, 600, t["title"], anchor="ma")
            self.text(x + w / 2, y + h / 2 + 5, subtitle, 12.5, 400, t["sub"], anchor="ma")
        else:
            self.text(x + w / 2, y + h / 2, title, size, 600, t["title"], anchor="mm")

    def cluster(self, x, y, w, h, label):
        """A dashed hairline group, the way the site draws a boundary."""
        self._dashed_rect(x, y, w, h, RULE_STRONG)
        self.text(x + 14, y + 11, label.upper(), 11, 600, TEAL, anchor="la")

    def _dashed_rect(self, x, y, w, h, colour, dash=6, gap=5):
        for x0 in range(int(x), int(x + w), dash + gap):
            for yy in (y, y + h):
                self.draw.line(self._s(x0, yy, min(x0 + dash, x + w), yy), fill=colour, width=SCALE)
        for y0 in range(int(y), int(y + h), dash + gap):
            for xx in (x, x + w):
                self.draw.line(self._s(xx, y0, xx, min(y0 + dash, y + h)), fill=colour, width=SCALE)

    def arrow(self, start, end, label=None, dashed=False, colour=INK_3, label_above=True):
        """A hairline connector with a solid head, horizontal or vertical."""
        (x1, y1), (x2, y2) = start, end
        if dashed:
            self._dashed_line(x1, y1, x2, y2, colour)
        else:
            self.draw.line(self._s(x1, y1, x2, y2), fill=colour, width=SCALE)

        head = 5
        if y1 == y2:
            tip = (x2, y2)
            back = x2 - head if x2 > x1 else x2 + head
            points = [tip, (back, y2 - head / 1.6), (back, y2 + head / 1.6)]
        else:
            tip = (x2, y2)
            back = y2 - head if y2 > y1 else y2 + head
            points = [tip, (x2 - head / 1.6, back), (x2 + head / 1.6, back)]
        self.draw.polygon([tuple(self._s(*p)) for p in points], fill=colour)

        if label:
            mx, my = (x1 + x2) / 2, (y1 + y2) / 2
            self.text(mx, my - 15 if label_above else my + 5, label, 11.5, 400, INK_3, anchor="ma")

    def _dashed_line(self, x1, y1, x2, y2, colour, dash=6, gap=5):
        if y1 == y2:
            for x0 in range(int(min(x1, x2)), int(max(x1, x2)), dash + gap):
                self.draw.line(self._s(x0, y1, min(x0 + dash, max(x1, x2)), y1),
                               fill=colour, width=SCALE)
        else:
            for y0 in range(int(min(y1, y2)), int(max(y1, y2)), dash + gap):
                self.draw.line(self._s(x1, y0, x1, min(y0 + dash, max(y1, y2))),
                               fill=colour, width=SCALE)

    def rule(self, x, y, w, colour=RULE):
        self.draw.line(self._s(x, y, x + w, y), fill=colour, width=SCALE)

    def ticks(self, x, y, count=5, gap=4, height=9):
        """The site's tick-mark eyebrow motif."""
        for i in range(count):
            self.draw.line(self._s(x + i * gap, y, x + i * gap, y + height),
                           fill=TEAL, width=SCALE)

    def eyebrow(self, x, y, label):
        self.ticks(x, y)
        self.text(x + 34, y - 3, label.upper(), 11.5, 600, TEAL, anchor="la")

    def caption(self, x, y, value):
        self.text(x, y, value, 13, 400, INK_2, anchor="la")

    def save(self, path):
        self.image.resize((self.w, self.h), Image.LANCZOS).save(path, optimize=True)
        return path
