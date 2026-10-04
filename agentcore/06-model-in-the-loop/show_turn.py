"""Print one turn of the agent readably: the trail the model took, then its answer.

Reads the runtime's JSON response on stdin. Used by demo.tape so the video
shows the model's choices as a short list rather than a wall of JSON.
"""

import json
import sys

turn = json.load(sys.stdin)
if "error" in turn:
    print(f"error: {turn['error']}")
    sys.exit(0)

for i, step in enumerate(turn.get("trail", []), 1):
    args = step.get("input", {})
    if step["tool"] == "run_python":
        code = args.get("code", "")
        lines = code.strip().splitlines()
        shown = "\n".join(f"      {line}" for line in lines[:8])
        if len(lines) > 8:
            shown += f"\n      ... ({len(lines) - 8} more lines)"
        print(f"  {i}. run_python  [{step.get('status', '?')}]\n{shown}")
    else:
        print(f"  {i}. {step['tool']}({json.dumps(args)})  [{step.get('status', '?')}]")
    if step.get("error"):
        print(f"      {step['error']}")
print()
print(turn.get("result", ""))
