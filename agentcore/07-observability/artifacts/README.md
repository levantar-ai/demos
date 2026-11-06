# Deployment artifacts — captured from a real run

Captured from the deploy and invoke cycle of this demo on 2026-11-05 (region
`us-east-1`, account `134570442530`), policy engine in `ENFORCE`. Demo 06's
stack was still deployed alongside it.

## Transaction Search

Off in the account before this demo. `get-trace-segment-destination` read
`XRay`, `ACTIVE`, and the `Default` indexing rule was at 0%. Andy enabled it
with the three commands in the demo README (resource policy
`TransactionSearchAccess`, destination `CloudWatchLogs`, indexing 1%). The
destination read `PENDING` and then `ACTIVE` within the ten minutes the
docs give. It is the account's setting and stays on after this stack is
destroyed.

## What was deployed

- Image `32f56fa` (the commit the image was built from; ADOT 0.22.0 under
  `opentelemetry-instrument`). The first build failed at the first `RUN`
  with `exec format error`, the VM's arm64 emulation having gone with a
  reboot; registered again with `tonistiigi/binfmt` and since made
  permanent with `qemu-user-binfmt`.
- `terraform apply` planned 75 to add. It stopped on
  `aws_bedrockagentcore_policy.own_orders` with `ConflictException: Policy
  with the same name already exists`, although the new engine was empty.
  Demo 06's engine holds `own_orders_only` and
  `deny_other_customers_orders`; policy names are unique in the account,
  not the engine. 07's are now `demos_agentcore_07_own_orders_only` and
  `demos_agentcore_07_deny_other_customers_orders` (commit `ca5df05`).
- Runtime `demos_agentcore_07_observability-fRhQYJ4m4M`, gateway
  `demos-agentcore-07-observability-gw-towk2q2cyy`, memory
  `demos_agentcore_07_memory-yjV7Mz9ppd`.
- The runtime's log group
  `/aws/bedrock-agentcore/runtimes/demos_agentcore_07_observability-fRhQYJ4m4M-DEFAULT`
  was created by the service at 23:20:15 UTC, with the runtime and before
  any invocation, with no retention and no KMS key. The `null_resource`
  added after the first run set seven days and the demo key; the next run
  wrote to it normally.

## Live runs

Customer `c-1000`, password generated in memory for the run and never
written down. Two conversations, each the spending question then the
carrier question. Responses are in `turns/`.

| session | turn | status | tools | restated |
| --- | --- | --- | --- | --- |
| `observability-1bb95ff61c1f2d386eb7a797917bce3e` | 1 | 200 | list_orders, run_python | yes |
| | 2 | 200 | run_python | no |
| `observability-45dcf15388795d60cd333966214c5112` | 1 | 200 | list_orders, run_python | no |
| | 2 | 200 | run_python | no |

Both spending answers: January £250.00, February £310.50, June £70.00, July
£113.30, biggest February, total £743.80. Both carrier answers: DPD 6, Royal
Mail 3. A request with no token was 401 on both runs.

## What the traces showed

Each turn is one trace. In the first session the runtime's `spans` stream
held 73 spans over the two turns (45 and 28), every one with
`session.id` set to the conversation's id, and each turn's top-level spans
had a parent outside the container, the runtime's own span, which is what
`traced()` is for. `aws/spans` held the gateway's spans
(`AgentCore.Gateway.InboundAuth`, `AgentCore.Identity.Authorize`,
`AgentCore.Policy.AuthorizeAction`, `AgentCore.Gateway.InvokeTool.orders___list_orders`,
`AgentCore.Gateway.TargetInvocation`), the orders Lambda's, and the
memory's (`ListEvents`, `CreateEvent`, `RetrieveMemoryRecords`) under the
same trace ids. The exchange Lambdas' spans were in traces of their own.

`trace-turn-1.json` is the first turn's trace, the runtime's spans and the
`aws/spans` records with that trace id, plus the exchange Lambdas' spans
from the turn's first ten seconds. Attributes are cut down to the ones the
post and `trace.py` use; the AWS credential attributes ADOT records on
botocore spans are left out.

The two things the post reports, from that trace:

- `Bedrock AgentCore.GetResourceOauth2Token` failed after 6,123 ms,
  status `ValidationException ... HTTP request failed against Token
  endpoint`, http 400. The exchange Lambda's invocation that served it took
  5,148 ms, during which `define`, `create`, `verify` and `pretoken`
  each started cold (Init 678 to 738 ms). The agent's retry, after its
  pause, took 641 ms. The second session's first exchange took 691 ms with
  no error.
- The first answer ended "In total, you've spent £743.80 with us this
  year across 7 orders." The `run_python` code printed the months, the
  biggest month and the year's total, and no count. The figure check
  named `7`, the restate request went back as a fourth model call (2,740
  input tokens, 86 output) and the restated answer dropped the count. The
  second session's spending turn needed no restatement.

Logs Insights over the runtime's group, model calls and tokens per turn of
the first session, `chat` spans only:

```
traceId=6aed10634132265a7f45d13b4678d66b  model_calls=4  input_tokens=8960  output_tokens=644
traceId=6aed108000cd74fb1039183c788fa4db  model_calls=2  input_tokens=5966  output_tokens=284
```

Summing token usage over every span gave 33,100 for the first turn, because
the agent and event-loop spans carry usage too. The query in the post and
the README filters on `chat`.

Every failed span in the group:

```
@timestamp=2026-11-05 23:25:30.206  name=Bedrock AgentCore.GetResourceOauth2Token  ms=6123
  status.message=ValidationException: An error occurred (ValidationException) when calling the GetResourceOauth2Token operation: HTTP request failed against Token endpoint
```

Where the second session's first turn spent its time, summed by span name
(model calls 11.6 s of a 14.6 s MCP session):

```
mcp.session 14588 ms, invoke_agent 13939, execute_event_loop_cycle x3 13487,
chat x3 11586, CreateEvent x11 1089, execute_tool run_python 980,
StartCodeInterpreterSession 741, GetResourceOauth2Token 691,
RetrieveMemoryRecords 250, InvokeCodeInterpreter x2 233, tools/list 229,
execute_tool orders___list_orders 219
```

## Content in the logs

`otel-rt-logs` held the system prompt, the customer's question, the full
`list_orders` result, the model's code, its first and restated answers and
the restate request, each record carrying the trace and span id of the
`chat` span it belongs to. That is why the runtime's group gets the demo
key and a retention.

The Strands MCP client's `server/discover` probe is answered 400 by the
gateway on every session, before `initialize` succeeds. It is in the
runtime log, not marked as an error span.

## Review, gpt-5.6-sol

Round 1 (post, README, artifacts, Dockerfile, main.py and its tests, the
Terraform that changed, show_trace.py, trace.py, diagram.py). Three
majors, verdict "not ready".

- "Every span carries the session id" was not supported for `aws/spans`.
  Checked against the stored spans: the memory's `CreateEvent`,
  `ListEvents` and `RetrieveMemoryRecords` carry `session.id` (the memory's
  own session, the same id); the gateway's, the Cedar span and the orders
  Lambda's carry none and join by trace id. Accepted; the post and README
  now say "every span the agent starts" and name the rest.
- The seven days and the demo key do not cover `aws/spans`, which holds the
  gateway's, the memory's and the Lambda's spans. Accepted; checked the
  group (30 days, no customer key, the account's) and section 7 says so.
  Those spans hold attributes (tool name, Cedar decision and determining
  policy, memory actor and session ids), not request or response bodies.
- `logs:DescribeLogGroups` "does not support resource-level authorization",
  so `log-group:*` would not grant it. Not changed. The AgentCore runtime
  permissions page lists the action with exactly that resource, and the
  runtime log group has no AccessDenied in it across both runs. The post's
  sentence now says the resource is how that page lists it rather than
  claiming more.

Also from round 1's check of the data, the runtime's own span is not in
either store; the agent's top-level spans have the runtime's span id as
their parent. The post no longer says the runtime emits spans of its own.

Round 2. Two majors, verdict "not ready".

- `DescribeLogGroups` on `log-group:*` again. Settled with the IAM policy
  simulator on the deployed role: `implicitDeny` for that action on both
  `*` and `log-group:*`. The runtime permissions page's resource does not
  grant it. Accepted; the statement is now `Resource = "*"`, with a
  comment, and the post says why.
- The runtime log group's records from the first run predate the KMS
  association, which applies only to data ingested after it. Accepted as a
  disclosure. The records from the first session
  (`observability-1bb95ff61c1f2d386eb7a797917bce3e`, before 23:28 UTC)
  were encrypted with CloudWatch Logs' default key, not the demo key, and
  expire with the group's seven-day retention. In the Terraform as it now
  stands the `null_resource` runs as soon as the runtime exists, before
  anything can invoke it, so a fresh deploy has no such records.

## Third run, image `6def722`

After the IAM change (`DescribeLogGroups` on `*`, simulator now `allowed`)
and a runtime update to image `6def722`, the same two prompts in session
`observability-625079a24a6929c4aee0d2b3693326b0` at 23:49 UTC, about 25
minutes after the previous run. Both 200, the same figures, no token 401.

- The first token exchange failed again, 5.1 s, `ERROR`, and the retry took
  0.7 s. The exchange had gone cold while the stack sat idle, so the
  failure follows a cold start, not only a deploy.
- The spending turn was restated again for the count, and this time the
  model called `run_python` a second time to print the count of 7 before
  stating it, which is what the system prompt asks for.

`show_trace.py` for that session:

```

trace 6aed160e27f6f9ab4554569b04bcdc86  103 spans
    0.1s    5.1s  token exchange  ERROR
    7.2s    0.7s  token exchange
    9.2s   16.1s  agent
    9.4s    0.2s    memory: RetrieveMemoryRecords
    9.7s    2.2s    model  1595 tokens in
   12.0s    0.5s    tool orders___list_orders
   12.1s    0.1s      gateway: Cedar AuthorizeAction
   12.2s    0.3s      gateway: orders Lambda
   14.2s    6.6s    model  2079 tokens in
   20.9s    1.1s    tool run_python
   20.9s    0.9s      Code Interpreter: start
   22.2s    3.1s    model  2625 tokens in
   25.3s    8.1s  agent
   25.5s    0.2s    memory: RetrieveMemoryRecords
   25.7s    5.1s    model  2821 tokens in
   30.9s    0.1s    tool run_python
   31.2s    2.1s    model  3417 tokens in

trace 6aed16380b6b4fb772207e5b4c91961d  55 spans
    0.0s    0.1s  token exchange
    1.2s    8.4s  agent
    1.4s    0.2s    memory: RetrieveMemoryRecords
    1.6s    4.2s    model  3524 tokens in
    5.9s    1.0s    tool run_python
    5.9s    0.8s      Code Interpreter: start
    7.1s    2.4s    model  3875 tokens in
```

## Review round 3, gpt-5.6-sol

On the post after the third run and the NCSC paragraph in section 7. Two
majors and a minor, all on the new paragraph, verdict "not ready". It
confirmed that the runtime role cannot read or delete its logs or change
their retention.

- "grants read access as narrowly as access to the orders" was not
  something the demo does; it creates no reader access at all. Accepted;
  the post now says that grant is the account owner's to make.
- CloudWatch Logs data protection masks on read and query, not on
  ingestion, and `logs:Unmask` reveals the original. Accepted and said.
- Object Lock protects an exported copy, not the log group. Accepted and
  said.
