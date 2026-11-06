"""Print a conversation's turns as traces, from the spans CloudWatch stored.

Usage: python3 show_trace.py <runtime log group> <session id> [region]

Runs one Logs Insights query over the runtime's `spans` stream for the
session, then one over `aws/spans` for the same trace ids, which is where
the gateway's and the memory's spans are. Prints each turn as a short
waterfall of the spans worth reading. Spans take a minute or two to arrive,
so it waits until the session has some and their count stops changing.
Read-only; run it under the same credentials as the demo.
"""

import re
import sys
import time

import boto3

# The spans worth a line, by name. Everything else (each memory write, each
# MCP request) is counted in the turn's total but not printed.
SHOWN = {
    "Bedrock AgentCore.GetResourceOauth2Token": "token exchange",
    "invoke_agent Strands Agents": "agent",
    "chat": "  model",
    "execute_tool orders___list_orders": "  tool orders___list_orders",
    "AgentCore.Policy.AuthorizeAction": "    gateway: Cedar AuthorizeAction",
    "AgentCore.Gateway.TargetInvocation": "    gateway: orders Lambda",
    "execute_tool run_python": "  tool run_python",
    "Bedrock AgentCore.StartCodeInterpreterSession": "    Code Interpreter: start",
    "RetrieveMemoryRecords": "  memory: RetrieveMemoryRecords",
}


def query(logs, group, text, start):
    qid = logs.start_query(logGroupName=group, startTime=start, endTime=int(time.time()) + 60,
                           queryString=text)["queryId"]
    while True:
        result = logs.get_query_results(queryId=qid)
        if result["status"] in ("Complete", "Failed", "Cancelled", "Timeout"):
            return [{f["field"]: f["value"] for f in row} for row in result["results"]]
        time.sleep(1)


# The agent's own grammar for a session id (agent/main.py). The id goes into
# a query string, so anything else is refused rather than quoted.
SESSION_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{32,127}")


def main():
    group, session = sys.argv[1], sys.argv[2]
    if not SESSION_RE.fullmatch(session):
        sys.exit("not a session id")
    logs = boto3.client("logs", region_name=sys.argv[3] if len(sys.argv) > 3 else None)
    start = int(time.time()) - 3 * 3600
    fields = "fields traceId, name, startTimeUnixNano, durationNano, status.code, " \
             "`attributes.gen_ai.usage.input_tokens`"
    mine = f'filter @logStream = "spans" and `attributes.session.id` = "{session}" | {fields} | limit 10000'
    # Logs Insights can answer with part of what it holds while it indexes, so
    # keep the fullest answer and stop once another query matches it.
    rows = []
    for _ in range(40):
        found = query(logs, group, mine, start)
        if rows and len(found) == len(rows):
            break
        if len(found) > len(rows):
            rows = found
        print(f"{len(rows)} spans so far, checking again in 10 s", flush=True)
        time.sleep(10)
    traces = sorted({r["traceId"] for r in rows})
    if traces:
        ids = ", ".join(f'"{t}"' for t in traces)
        rows += query(logs, "aws/spans", f"filter traceId in [{ids}] | {fields} | limit 10000", start)
    for trace in sorted(traces, key=lambda t: min(int(r["startTimeUnixNano"]) for r in rows if r["traceId"] == t)):
        spans = sorted((r for r in rows if r["traceId"] == trace), key=lambda r: int(r["startTimeUnixNano"]))
        t0 = int(spans[0]["startTimeUnixNano"])
        print(f"\ntrace {trace}  {len(spans)} spans")
        for s in spans:
            label = SHOWN.get(s["name"])
            if not label:
                continue
            at = (int(s["startTimeUnixNano"]) - t0) / 1e9
            took = int(s["durationNano"]) / 1e9
            extra = ""
            if s["name"] == "chat" and s.get("attributes.gen_ai.usage.input_tokens"):
                extra = f"  {s['attributes.gen_ai.usage.input_tokens']} tokens in"
            if s.get("status.code") == "ERROR":
                extra += "  ERROR"
            print(f"  {at:5.1f}s  {took:5.1f}s  {label}{extra}")


if __name__ == "__main__":
    main()
