#!/usr/bin/env python3
"""Mandatory GPT review of a post before it is merged: two passes, run together.

Usage: python3 scripts/review-post.py agentcore/07-observability ["round note"]

defects: POST.md plus every tracked .md/.py/.tf/Dockerfile in the demo, no web.
         Finds wrong facts, code that does not match the post, security, bugs.
reader:  POST.md alone, with web search, read as the audience would. Finds
         wrong or overstated claims, reproduction traps, scope gaps, drift.

Each pass writes <demo>/artifacts/review-<pass>.md. Act on defects, reader 1, 2
and 5; note reader 3 and 4. After applying fixes, run it once more.
"""

import concurrent.futures
import json
import pathlib
import subprocess  # nosec B404 - fixed git argv
import sys
import urllib.request

MODEL = "gpt-5.6-sol"
KEY = pathlib.Path.home() / ".ssh/loadr_openai_api_key"

DEFECTS = (
    "You are a senior AWS and security reviewer for a technical blog series on Amazon Bedrock AgentCore. "
    "Review the post and the code it describes. Report only real problems: factual errors about AWS, AgentCore "
    "or the libraries used; code that does not do what the post says; security issues (credentials, customer "
    "data, IAM breadth); bugs; claims the evidence in artifacts/README.md does not support. For each finding give "
    "severity (blocker/major/minor), the file and quote, why it is wrong, and the fix. Do not critique style, "
    "scope or structure. End with a one-line verdict: 'ready to publish' or 'not ready'."
)
READER = (
    "You are an experienced AWS practitioner reading a technical blog post as its audience would, with only the "
    "published text. Use web search to check its technical claims against current AWS and vendor documentation. "
    "Report, separately: (1) claims that are wrong, with the source that shows it; (2) claims stated more strongly "
    "than the evidence shown in the post supports; (3) what a reader trying to reproduce it would trip over; "
    "(4) gaps a production reader would notice, marked clearly as scope rather than defects; (5) any passage "
    "that drifts from the post's subject or explains more than the reader needs. Cite sources. Be concise. End "
    "with a one-line verdict."
)


def bundle(demo):
    files = subprocess.run(["git", "ls-files", demo], capture_output=True, text=True, check=True).stdout.split()  # nosec B603 B607
    files = [f for f in files if f.endswith((".md", ".py", ".tf", "Dockerfile"))]
    return "\n\n".join(f"===== {f} =====\n{pathlib.Path(f).read_text()}" for f in files)


def review(system, user, web):
    body = {
        "model": MODEL,
        "input": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "reasoning": {"effort": "high"},
        "max_output_tokens": 40000,  # 8000 went entirely on reasoning and returned no text
    }
    if web:
        body["tools"] = [{"type": "web_search"}]
    req = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {KEY.read_text().strip()}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=1200) as r:  # nosec B310 - fixed https endpoint
        out = json.load(r)
    text = "".join(
        c.get("text", "")
        for item in out.get("output", [])
        if item.get("type") == "message"
        for c in item.get("content", [])
    )
    if not text:
        sys.exit(f"no review text returned: {json.dumps(out)[:2000]}")
    return text


def main():
    demo = sys.argv[1].rstrip("/")
    note = sys.argv[2] if len(sys.argv) > 2 else ""
    post = pathlib.Path(demo, "POST.md").read_text()
    passes = {
        "defects": (DEFECTS, f"{note}\n\n{bundle(demo)}".strip(), False),
        "reader": (READER, post, True),
    }
    with concurrent.futures.ThreadPoolExecutor() as pool:
        futures = {name: pool.submit(review, *args) for name, args in passes.items()}
    for name, future in futures.items():
        path = pathlib.Path(demo, "artifacts", f"review-{name}.md")
        path.parent.mkdir(exist_ok=True)
        path.write_text(f"# {name} pass, {MODEL}\n\n{future.result()}\n")
        print(f"{path}: {future.result().strip().splitlines()[-1]}")


if __name__ == "__main__":
    main()
