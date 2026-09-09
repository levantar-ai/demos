"""Sequence diagram for post 05, the token's path and the two checks.

Run from this directory: python3 sequence.py
Produces sequence.png referenced by POST.md.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "scripts"))

from levantar_diagram import FLAME, INK_3, RULE_STRONG, TEAL, Diagram

d = Diagram(1460, 660)

# Participants and their lifeline x-centres. The runtime authorizer, which
# validates the token, is kept separate from the agent, which only relays it.
people = [
    (150, "customer", None),
    (450, "AgentCore Runtime", "the JWT authorizer"),
    (710, "agent", "the container"),
    (1000, "AgentCore Gateway", "Policy in AgentCore, Cedar"),
    (1320, "orders", "the tool"),
]
top, bottom = 40, 600
for cx, title, sub in people:
    w = 220 if sub else 150
    d.box(cx - w / 2, top, w, 54, title, subtitle=sub, tone="accent")
    d._dashed_line(cx, top + 54, cx, bottom, RULE_STRONG)

C, RT, A, G, O = 150, 450, 710, 1000, 1320


def msg(x1, x2, y, label, colour=INK_3, dashed=False):
    d.arrow((x1, y), (x2, y), label, dashed=dashed, colour=colour)


def note(cx, y, w, text):
    d.box(cx - w / 2, y, w, 38, text)


# One token, validated at the runtime before the agent sees it, then again at
# the gateway.
msg(C, RT, 120, "invoke, Bearer JWT")
note(RT, 150, 230, "runtime validates the token")
msg(RT, A, 214, "forward request and token")
msg(A, G, 262, "list_orders(customer_id),\nrelaying the same token")
note(G, 298, 300, "gateway validates the token, then Cedar")
d.text(G, 348, "caller's username == customer_id ?", 12, 600, TEAL, anchor="ma")

# The two outcomes are mutually exclusive, so they sit in one alt frame and
# only the permit branch reaches the tool.
d.cluster(600, 378, 800, 150, "one of two outcomes")
msg(G, O, 428, "the caller's own id: permit", colour=TEAL)
msg(G, A, 492, "another id: forbid wins,\nno permit applies", colour=FLAME, dashed=True)

d.caption(
    150, 628,
    "One token, minted once, validated at the runtime before the agent sees it, "
    "then again at the gateway where Cedar decides.",
)
d.save("sequence.png")
print("wrote sequence.png")
