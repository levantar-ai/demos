# reader pass, gpt-5.6-sol

Checked against current AWS, OpenTelemetry, Strands, and repository material as of **November 7, 2026**.

## 1. Claims that are wrong

- **“Use Strands’ redaction” is misleading.** Strands explicitly says its SDK does **not natively perform PII redaction**; it recommends external redaction libraries or collector-level masking. For simple attribute suppression, ADOT 0.22 documents `AWS_REDACT_SPAN_ATTRIBUTES`. The post should name the actual mechanism rather than implying a built-in Strands control. ([strandsagents.com](https://strandsagents.com/latest/documentation/docs/user-guide/safety-security/pii-redaction/))

No other central claim is clearly contradicted: the repository’s captured trace supports the runtime-parent context, joined Gateway/Memory/Lambda spans, session attributes, failed exchange, model calls, and token counts. ([raw.githubusercontent.com](https://raw.githubusercontent.com/levantar-ai/demos/main/agentcore/07-observability/artifacts/README.md))

## 2. Claims stronger than the evidence supports

- **“Every turn … with what the model was sent and said back” sounds audit-grade.** The run demonstrates capture, but OpenTelemetry export is best-effort: queues can fill, exports can time out, and failed batches can be dropped. Say “captures in this configuration” rather than implying completeness. ([opentelemetry.io](https://opentelemetry.io/docs/specs/otel/protocol/exporter/?utm_source=openai))
- **“One turn is one trace” needs the qualifier “for instrumented, context-propagating components.”** The post itself acknowledges that the exchange Lambdas and Code Interpreter service spans are absent. AWS now supports explicit tracing for Identity and built-in tools, so this is configuration-dependent rather than an intrinsic boundary. ([docs.aws.amazon.com](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/observability-configure.html))
- **Cold starts are plausible, not established as the cause of Identity’s timeout.** The timing correlation is good evidence, especially after another idle period, but does not exclude an Identity/token-endpoint timeout or another transient dependency failure. Keep “likely,” and label it an inference. ([raw.githubusercontent.com](https://raw.githubusercontent.com/levantar-ai/demos/main/agentcore/07-observability/artifacts/README.md))
- **“Tracing … takes very little” understates the operational work:** account/Region-wide Transaction Search, resource policies, execution-role permissions, deliveries, KMS/retention changes, and sensitive-data governance. ([docs.aws.amazon.com](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/Enable-TransactionSearch.html))

## 3. Reproduction traps

- **ARM64 is missing from the post’s procedure.** AgentCore Runtime requires an ARM64 image; x86 builders need buildx/emulation or an ARM builder. The captured run itself hit `exec format error`. ([docs.aws.amazon.com](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-http-protocol-contract.html?trk=article-ssr-frontend-pulse_little-text-block&utm_source=openai))
- **Transaction Search requires substantial setup permissions and is account/Region-wide.** It also may remain `PENDING` before becoming active; a reader may deploy successfully but initially see no spans. ([docs.aws.amazon.com](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/Enable-TransactionSearch.html))
- **The container is not fully reproducible.** Top-level Python packages are version-pinned, but transitive packages and hashes are not. In particular, Strands 1.57.2 permits MCP up to `<2.2` and now resolves to MCP 2.x, while ADOT 0.22 documents its MCP instrumentation support as `<2`. Pin or lock the complete resolved environment and test that MCP spans still appear. ([raw.githubusercontent.com](https://raw.githubusercontent.com/levantar-ai/demos/main/agentcore/07-observability/agent/Dockerfile))
- **Terraform invokes the local AWS CLI to modify the runtime log group.** Reproduction therefore requires `bash`, an installed/configured AWS CLI, appropriate credentials, and the service-created log group to exist; the provisioner has no retry. ([raw.githubusercontent.com](https://raw.githubusercontent.com/levantar-ai/demos/main/agentcore/07-observability/terraform/observability.tf))
- **The 1% setting is indexing, not ingestion.** Readers may wrongly expect only 1% of spans to be stored or billed; Transaction Search ingests the spans and indexes a percentage for trace summaries. ([docs.aws.amazon.com](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/Enable-TransactionSearch.html))

## 4. Production gaps — scope, not defects

- **Telemetry reliability:** no exporter-failure monitoring, delivery alarms, or completeness checks. AWS recommends alarms, while OpenTelemetry documents queue/export loss modes. ([docs.aws.amazon.com](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/observability-configure.html))
- **Cost and volume controls:** no estimate or policy for span ingestion, model-content logs, retention, sampling, or high-cardinality session IDs. ([docs.aws.amazon.com](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/Enable-TransactionSearch.html))
- **Data governance:** the post sensibly raises access and immutability, but implements no reader roles, data-protection policy, immutable export, legal retention policy, or deletion workflow. NCSC explicitly recommends protecting these logs from modification or deletion. ([ncsc.gov.uk](https://www.ncsc.gov.uk/blogs/managing-the-cyber-risk-of-agentic-ai))
- **Shared `aws/spans` governance:** Gateway, Memory, and Lambda spans use the account-level group rather than the demo’s KMS/retention boundary. The post discloses this; production ownership and retention still need defining. ([raw.githubusercontent.com](https://raw.githubusercontent.com/levantar-ai/demos/main/agentcore/07-observability/artifacts/README.md))
- **Coverage:** Identity-exchange internals and Code Interpreter service spans are intentionally omitted. That is valid demo scope, but prevents a genuinely end-to-end operational trace. ([docs.aws.amazon.com](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/observability-configure.html))

## 5. Drift or excess explanation

- Section 6’s four Cognito-trigger cold-start reconstruction is more Identity troubleshooting than tracing setup; reduce it to the hidden retry and latency lesson.
- The figure-check mechanics and exact 2,740-token restatement cost are useful evidence, but could be one paragraph rather than a second mini-case study.
- “One turn, one trace” is repeated in the TL;DR, introduction, section 4, and conclusion.
- The NCSC discussion is relevant, not drift, but could be shortened after the concrete retention/KMS/access facts.

**Verdict: Technically strong and unusually well-evidenced, but qualify completeness, fix the redaction wording, and make the build and telemetry dependencies reproducible.**
