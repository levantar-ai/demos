"""Generate the prompt routing diagram for post 03.

Run from this directory: python3 routing.py
Produces routing.png referenced by POST.md.

Shows what happens between a prompt arriving and an AWS API call leaving,
which the post's architecture diagram deliberately does not: the routing is
four string tests in our own code, not a model deciding anything.
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent / "scripts"))

from levantar_diagram import INK, INK_3, Diagram

W, H = 1480, 680
d = Diagram(W, H)

d.eyebrow(40, 34, "post 03")
d.text(40, 54, "How a prompt reaches an AWS API call", 21, 600, INK)
d.text(40, 84, "Two prefix checks, one regex and a fallback, all in main.py. "
       "There is no model in this agent.", 13.5, 400, INK_3)

# The request, on the left.
d.box(40, 210, 210, 74, "POST /invocations", "actor, session, prompt", tone="accent")
d.arrow((250, 247), (322, 247))

# The agent container holds the router and the four handlers.
d.cluster(322, 130, 700, 470, "agent container on AgentCore Runtime")

d.box(348, 216, 176, 62, "do_POST", "reads the prompt", tone="default")

# Flame is reserved for one thing per the site's colour rules, and here it is
# the fall-through, because that is the branch nobody expects to be the one
# doing the long-term lookup.
ROWS = [
    # (test, test_detail, function, api, tone, dashed_to_api)
    ('startswith("remember")', "prefix match", "remember()", "CreateEvent", "accent", False),
    ('startswith("recap")', "prefix match", "recap()", "ListEvents", "accent", False),
    ("an order number", "ORDER_RE, from post 02", "lookup_order()",
     "Gateway, then Lambda", "accent", True),
    ("anything else", "no test at all", "recall()", "RetrieveMemoryRecords", "flame", False),
]

top, row_h, gap = 176, 84, 22
test_x, test_w = 556, 220
fn_x, fn_w = 812, 186
api_x, api_w = 1102, 268

for i, (test, detail, fn, api, tone, dashed) in enumerate(ROWS):
    y = top + i * (row_h + gap)
    mid = y + row_h / 2

    d.box(test_x, y, test_w, row_h, test, detail, tone=tone, mono=True)
    d.arrow((test_x + test_w, mid), (fn_x, mid))
    d.box(fn_x, y, fn_w, row_h, fn, tone="default", mono=True)
    d.arrow((fn_x + fn_w, mid), (api_x, mid), dashed=dashed)
    d.box(api_x, y, api_w, row_h, api, tone="accent" if dashed else "dark")

    # The router falls through the tests in order, so link them vertically.
    if i:
        d.arrow((test_x + test_w / 2, y - gap), (test_x + test_w / 2, y), dashed=True)

# From do_POST into the first test.
d.arrow((524, 247), (test_x, 247))

d.caption(40, 606,
          "Dark boxes are the three bedrock-agentcore data-plane calls this post is about. "
          "The dashed route is the gateway tool carried forward from post 02.")
d.caption(40, 628,
          'The prefix is not stripped, so "remember: I prefer DPD" stores that whole string, '
          '"remember:" and all.')

out = pathlib.Path(__file__).parent / "routing.png"
d.save(out)
print(f"rendered {out}")
