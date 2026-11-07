# reader pass, gpt-5.6-sol

I checked the post against current AWS, ADOT, Strands, NCSC, and repository documentation.

## 1. Claims that are wrong

- **No material error in the core tracing implementation.** The ADOT startup, manual context extraction, baggage-to-span copying, Gateway/Memory trace deliveries, and Logs Insights fields are consistent with current documentation.
- **Minor terminology:** the NCSC source is not yet formal “guidance”; NCSC describes it as **interim practical advice** that future formal guidance will supersede. ([ncsc.gov.uk](https://www.ncsc.gov.uk/blogs/managing-the-cyber-risk-of-agentic-ai))

## 2. Claims stronger than the evidence supports

- **“The model stated [the count] without computing it” / “counting in its head.”** The trace proves only that no traced `run_python` result printed the count. It cannot establish whether the model internally counted rows or merely guessed. Say **“without a recorded tool-backed computation.”** ([raw.githubusercontent.com](https://raw.githubusercontent.com/levantar-ai/demos/main/agentcore/07-observability/artifacts/README.md))
- **Cold starts as the cause of the token failure.** Cold starts and the timeout occurred together twice, making them a plausible cause, but there is no control run or service-side diagnosis establishing causality. “Likely associated with the cold-start path” would be safer. ([raw.githubusercontent.com](https://raw.githubusercontent.com/levantar-ai/demos/main/agentcore/07-observability/artifacts/README.md))
- **“One turn, one trace across … the sandbox and memory.”** This is true only for the instrumented synchronous path. The post itself excludes the exchange Lambdas and Code Interpreter service spans; asynchronous Memory extraction/consolidation is also outside the request trace. ([docs.aws.amazon.com](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/observability-memory-metrics.html?utm_source=openai))
- **“There is no collector … on the runtime.”** AWS documents that customers **do not manage** a collector in AgentCore Runtime, not that no managed collector or equivalent ingestion component exists. ([docs.aws.amazon.com](https://docs.aws.amazon.com/de_de/AmazonCloudWatch/latest/monitoring/omni-data-protection.html))

## 3. What a reproducing reader may trip over

- **Tracing enablement is separate from installing ADOT.** Transaction Search and tracing must be enabled for the relevant Runtime, Gateway, Memory, Identity, and built-in-tool resources. Code Interpreter service spans require their own tracing toggle. ([docs.aws.amazon.com](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/observability-configure.html))
- **Expect a delay:** Transaction Search can take up to ten minutes to become searchable. Also, its indexing percentage is distinct from span ingestion; the example indexes 1%, not necessarily the percentage of spans stored as structured logs. ([docs.aws.amazon.com](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/Enable-TransactionSearch.html))
- **The Logs Insights query assumes unified runtime trace storage.** Only newly created agents in supported Regions default to the runtime log group; older agents may still put spans in `aws/spans`. `UNIFIED_TRACES_DESTINATION_ENABLED` controls this. ([docs.aws.amazon.com](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/observability-configure.html))
- **Session IDs must be at least 33 characters**, or invocation fails before this tracing code matters. Reuse the same ID for related turns. ([docs.aws.amazon.com](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-sessions.html?utm_source=openai))
- **The image must be ARM64.** Building on x86 without buildx/QEMU produces the documented `exec format error`; this happened during the published run but is absent from the post. ([docs.aws.amazon.com](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-troubleshooting.html?utm_source=openai))
- **The runtime log-group update is somewhat brittle.** Terraform uses a `null_resource`/local-exec to set retention and KMS after the service creates the group, with no retry if creation is delayed. The repository acknowledges this race, although it did not occur in four applies. ([raw.githubusercontent.com](https://raw.githubusercontent.com/levantar-ai/demos/main/agentcore/07-observability/terraform/observability.tf))

## 4. Production gaps — scope, not defects

- **Scope:** no cost model for full span ingestion, model-content logs, sampling, indexing, or retention. Strands explicitly recommends sampling and storage-cost monitoring. ([strandsagents.com](https://strandsagents.com/latest/documentation/docs/user-guide/observability-evaluation/traces/))
- **Scope:** no alarms, SLOs, missing-telemetry detection, exporter-failure monitoring, or schema/version tests protecting queries such as `name = "chat"`.
- **Scope:** access governance is advised but not implemented: reader roles, break-glass access, immutable export, deletion/privacy processes, and controls for the shared `aws/spans` group.
- **Scope:** no automated trace-completeness tests across Gateway, Lambda, Identity, tools, asynchronous Memory work, retries, and unsampled upstream callers.
- **Scope:** no supply-chain lock beyond top-level Python version pins; a production build would normally lock and verify transitive artifacts.

## 5. Drift or excess explanation

- **Section 6’s Cognito-trigger and 25-minute-idle reconstruction** is useful evidence but belongs partly to the earlier Identity post. It could be reduced to: “the trace correlated the delay with cold starts, but does not prove causality.”
- **The NCSC paragraph is relevant**, but long for an implementation post. A short data-classification warning plus a production-security sidebar would preserve the point.
- Otherwise the post stays focused; the trace queries and data-handling section earn their space.

**Verdict: Technically sound and reproducible, but tighten the two causal claims and add a short prerequisites/troubleshooting box before publishing.**
