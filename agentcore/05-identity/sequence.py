"""Sequence diagram for post 05, the on-behalf-of exchange and the two checks.

Run from this directory: python3 sequence.py
Produces sequence.png referenced by POST.md.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "scripts"))

from levantar_diagram import FLAME, INK_3, RULE_STRONG, TEAL, Diagram

d = Diagram(1900, 900)

# Participants and their lifeline x-centres. The runtime authorizer, which
# validates the customer's token, is kept separate from the agent. AgentCore
# Identity and the token exchange (a front door in front of a second Cognito
# pool, the AWS sample's shape) are the new pair in the middle.
people = [
    (110, "customer", None),
    (370, "AgentCore Runtime", "the JWT authorizer"),
    (620, "agent", "the container"),
    (880, "AgentCore Identity", "workload identity, OBO"),
    (1150, "token exchange", "front door + exchange pool"),
    (1440, "AgentCore Gateway", "trusts the exchange pool, Cedar"),
    (1730, "orders", "the tool"),
]
top, bottom = 40, 840
for cx, title, sub in people:
    w = 230 if sub else 140
    d.box(cx - w / 2, top, w, 54, title, subtitle=sub, tone="accent")
    d._dashed_line(cx, top + 54, cx, bottom, RULE_STRONG)

C, RT, A, ID, EX, G, O = 110, 370, 620, 880, 1150, 1440, 1730


def msg(x1, x2, y, label, colour=INK_3, dashed=False):
    d.arrow((x1, y), (x2, y), label, dashed=dashed, colour=colour)


def note(cx, y, w, text, sub=None):
    d.box(cx - w / 2, y, w, 44 if sub else 38, text, subtitle=sub)


# Inbound, unchanged: the customer's token validated at the runtime.
msg(C, RT, 120, "invoke, Bearer JWT")
note(RT, 150, 230, "runtime validates the token")
msg(RT, A, 214, "forward request and token")

# On behalf of the customer: the agent gets a token for the order service from
# AgentCore Identity, which brokers the exchange with the customer's token as
# the subject. The customer's own token never goes to the gateway.
msg(A, ID, 268, "GetWorkloadAccessTokenForJWT,\nthen GetResourceOauth2Token (on behalf of)")
msg(ID, EX, 336, "RFC 8693 exchange,\nsubject_token = the customer's JWT")
note(EX, 362, 330, "front door verifies the JWT", "the pool's triggers verify again, Cognito mints, 5 min")
msg(EX, ID, 430, "the minted token, aud = orders client", dashed=True)
msg(ID, A, 476, "the minted token", dashed=True)

# The minted token goes to the gateway, which trusts the exchange pool.
msg(A, G, 530, "list_orders(customer_id),\nthe minted token")
note(G, 560, 300, "gateway validates the token, then Cedar")
d.text(G, 610, "token customer_id == customer_id argument ?", 12, 600, TEAL, anchor="ma")

# The two outcomes are mutually exclusive, so they sit in one alt frame and
# only the permit branch reaches the tool.
d.cluster(1010, 640, 830, 150, "one of two outcomes")
msg(G, O, 690, "id matches the token: permit", colour=TEAL)
msg(G, A, 754, "another id: forbid wins,\nno permit applies", colour=FLAME, dashed=True)

d.caption(
    110, 868,
    "The customer's token is validated at the runtime, exchanged on their behalf through "
    "AgentCore Identity for a five-minute token the exchange pool mints for the gateway, and Cedar decides on that.",
)
d.save("sequence.png")
print("wrote sequence.png")
