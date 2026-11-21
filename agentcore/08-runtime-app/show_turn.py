"""Print one turn of the agent readably: the trail the model took, then its answer.

Reads the runtime's JSON response on stdin. Used by demo.tape so the video
shows the tools the model called and its answer, not the code or the JSON.
"""

import json
import sys

raw = sys.stdin.read()
try:
    turn = json.loads(raw)
except ValueError:
    print(f"no JSON in the response: {raw[:300]!r}")
    sys.exit(0)
if not isinstance(turn, dict):
    print(f"unexpected response: {raw[:300]!r}")
    sys.exit(0)
if "error" in turn:
    print(f"error: {turn['error']}")
    sys.exit(0)

for i, step in enumerate(turn.get("trail", []), 1):
    # Post 07's video is about the trace, so the turn is only the tools and the answer.
    print(f"  {i}. {step['tool']}  [{step.get('status', '?')}]")
    if step.get("error"):
        print(f"      {step['error']}")
if turn.get("restated"):
    print("  the check named a figure in the first answer; the model was asked once to restate")
if turn.get("unsupported_figures"):
    print(f"  figures in the answer no tool printed: {', '.join(turn['unsupported_figures'])}")
print()
print(turn.get("result", "").replace("**", ""))
