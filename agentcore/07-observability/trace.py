"""The trace of one turn, drawn from the spans the live run recorded.

Run from this directory: python3 trace.py
Reads artifacts/trace-turn-1.json and writes trace.png, referenced by POST.md.
Each row is a span, or for memory every span of that kind, placed on the
turn's own clock. Nothing here is made up; a row with no span is not drawn.
"""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "scripts"))

from levantar_diagram import (
    ACCENT_LIFT,
    FLAME,
    INK_3,
    RULE,
    TEAL,
    Diagram,
)

with open("artifacts/trace-turn-1.json") as f:
    trace = json.load(f)
spans = trace["spans"]
t0 = min(s["start"] for s in spans)
t1 = max(s["end"] for s in spans)


def named(name, source=None):
    return [s for s in spans if s["name"] == name and (source is None or s["source"] == source)]


def failed(span):
    return (span.get("status") or {}).get("code") == "ERROR"


exchange = trace["exchange_spans"]
cold = [s for s in exchange if s["name"].endswith("/LambdaService")]
chats = named("chat")
agents = named("invoke_agent Strands Agents")

# (label, detail, spans, colour). One row each, top to bottom in time order.
rows = [
    ("token exchange", "AgentCore Identity", named("Bedrock AgentCore.GetResourceOauth2Token"), TEAL),
    ("  exchange Lambda", "its own trace", [c for c in cold if c["service"].endswith("-exchange")], INK_3),
    ("  Cognito triggers", "define, create, verify, pre-token", [c for c in cold if not c["service"].endswith("-exchange")], INK_3),
    ("memory reads", "ListEvents, RetrieveMemoryRecords",
     named("ListEvents", "aws/spans") + named("RetrieveMemoryRecords", "aws/spans"), TEAL),
    ("memory writes", "CreateEvent", named("CreateEvent", "aws/spans"), TEAL),
    ("gateway session", "MCP initialise, tools/list", named("mcp.session"), TEAL),
    ("agent", "invoke_agent", agents[:1], ACCENT_LIFT),
    ("  model", "chat", chats[:3], ACCENT_LIFT),
    ("  orders___list_orders", "execute_tool", named("execute_tool orders___list_orders"), TEAL),
    ("    Cedar", "AuthorizeAction at the gateway", named("AgentCore.Policy.AuthorizeAction"), TEAL),
    ("    orders Lambda", "the gateway's target", named("demos-agentcore-07-observability-orders/LambdaService"), TEAL),
    ("  run_python", "execute_tool", named("execute_tool run_python"), TEAL),
    ("    Code Interpreter", "start, invoke", named("Bedrock AgentCore.StartCodeInterpreterSession")
     + named("Bedrock AgentCore.InvokeCodeInterpreter"), TEAL),
    ("agent, restating", "invoke_agent", agents[1:], ACCENT_LIFT),
    ("  model", "chat", chats[3:], ACCENT_LIFT),
]

LEFT, RIGHT, TOP, ROW = 360, 1860, 110, 46
d = Diagram(1900, TOP + ROW * len(rows) + 110)
d.eyebrow(40, 34, "one turn, one trace")
d.text(40, 56, f"session {trace['session']}, trace {trace['traceId']}", 13, 400, INK_3)

scale = (RIGHT - LEFT) / (t1 - t0)
for second in range(0, int((t1 - t0) / 1e9) + 1, 5):
    x = LEFT + second * 1e9 * scale
    d._dashed_line(x, TOP - 14, x, TOP + ROW * len(rows), RULE)
    d.text(x, TOP - 30, f"{second} s", 12, 400, INK_3, anchor="ma")

for i, (label, detail, row, colour) in enumerate(rows):
    y = TOP + i * ROW
    d.text(40, y + 6, label.replace(" ", " "), 14.5, 600)
    d.text(40 + d.width_of(label, 14.5, 600) + 10, y + 8, detail, 12, 400, INK_3)
    for s in row:
        x0 = LEFT + (s["start"] - t0) * scale
        x1 = max(x0 + 3, LEFT + (s["end"] - t0) * scale)
        d.draw.rounded_rectangle(d._s(x0, y + 4, x1, y + 26), radius=4 * 2, fill=FLAME if failed(s) else colour)
    # A span of 0.6 s or more is labelled with its duration after its bar,
    # when the label fits before the row's next bar starts.
    placed = 0
    for s in sorted(row, key=lambda s: s["start"]):
        ms = (s["end"] - s["start"]) / 1e6
        note = f"{ms / 1000:.1f} s" + (", failed" if failed(s) else "")
        x = LEFT + (s["end"] - t0) * scale + 6
        room = min([LEFT + (o["start"] - t0) * scale for o in row if o["start"] > s["end"]] + [d.w])
        if ms >= 600 and x > placed and x + d.width_of(note, 12, 600) + 4 < room:
            placed = x + d.width_of(note, 12, 600)
            d.text(x, y + 8, note, 12, 600 if failed(s) else 400, FLAME if failed(s) else INK_3)

d.caption(
    40, TOP + ROW * len(rows) + 30,
    "The first token exchange failed after 6.1 s while the exchange's Lambdas started cold, and the retry took 0.6 s. "
    "The model's first answer named a figure no code printed, so trusted code asked it once to restate.",
)
d.save("trace.png")
print("wrote trace.png")
