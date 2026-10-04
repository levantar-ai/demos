"""Sequence diagram for post 06, one turn with the model choosing.

Run from this directory: python3 sequence.py
Produces sequence.png referenced by POST.md.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "scripts"))

from levantar_diagram import FLAME, INK_3, RULE_STRONG, TEAL, Diagram

d = Diagram(1900, 960)

# Participants and their lifeline x-centres. Trusted code (the agent) sits
# between the runtime and the model; everything the model reaches is to its
# right, and the token it never sees is obtained to its left.
people = [
    (110, "customer", None),
    (340, "AgentCore Runtime", "validates the JWT"),
    (590, "agent", "trusted code"),
    (840, "AgentCore Identity", "on-behalf-of (post 05)"),
    (1090, "model", "Claude Sonnet 4.5"),
    (1360, "AgentCore Gateway", "MCP, Cedar per call"),
    (1620, "Code Interpreter", "SANDBOX"),
    (1810, "Memory", None),
]
top, bottom = 40, 900
for cx, title, sub in people:
    w = 230 if sub else 140
    d.box(cx - w / 2, top, w, 54, title, subtitle=sub, tone="accent")
    d._dashed_line(cx, top + 54, cx, bottom, RULE_STRONG)

C, RT, A, ID, M, G, S, MEM = 110, 340, 590, 840, 1090, 1360, 1620, 1810


def msg(x1, x2, y, label, colour=INK_3, dashed=False):
    d.arrow((x1, y), (x2, y), label, dashed=dashed, colour=colour)


def note(cx, y, w, text, sub=None):
    d.box(cx - w / 2, y, w, 44 if sub else 38, text, subtitle=sub)


# Trusted code first: who is asking, and a token for the order service.
msg(C, RT, 120, "prompt, Bearer JWT")
msg(RT, A, 170, "forward, token validated")
msg(A, ID, 220, "a token for the order service,\non the customer's behalf")
msg(ID, A, 284, "the minted token, 5 min", dashed=True)
note(A, 310, 300, "builds the tools with the minted token", "the model is told the customer id, not the token")

# Then the model decides.
msg(A, M, 380, "system prompt: you act for c-1000\n+ the prompt + the tools")
msg(M, MEM, 440, "recall preferences for c-1000", dashed=True)
msg(M, G, 492, "orders___list_orders(customer_id)")
note(G, 518, 250, "Cedar: argument == token's customer_id ?")
d.cluster(1230, 560, 300, 120, "one of two outcomes")
msg(G, M, 606, "permit: the orders", colour=TEAL, dashed=True)
msg(G, M, 650, "another id: refused, no tool runs", colour=FLAME, dashed=True)
msg(M, S, 712, "run_python(the pandas it wrote)")
msg(S, M, 758, "what it printed", dashed=True)
msg(M, A, 806, "the answer", dashed=True)
msg(A, C, 854, "answer + trail of tool calls", dashed=True)

d.caption(
    110, 928,
    "Trusted code establishes the customer and the token; the model chooses the tools and the arguments; "
    "Cedar at the gateway decides whether a chosen customer_id is allowed.",
)
d.save("sequence.png")
print("wrote sequence.png")
