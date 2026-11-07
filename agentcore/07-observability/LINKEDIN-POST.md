# LinkedIn post — tracing the agent (post 07)

Live: https://levantar.ai/insights/agentcore-07-observability.html
Native image: social-square.png (1200x1200). Or share the URL and the
og:image renders the 1200x630 card. The demo video uploads natively too.

---

Post seven of the AgentCore series, where one order support agent gains a capability with each post. This time we trace it.

The agent runs under the AWS Distro for OpenTelemetry, joins the trace AgentCore Runtime starts, and the gateway and the memory send their spans to the same place. One customer's turn becomes one trace, from the model calls through the gateway's Cedar check and the orders Lambda to the memory.

The trace earned its keep on the first run. It showed a token exchange failing and a retry quietly covering for it, and the model stating a figure it had worked out in its head rather than in the sandbox. Both answers the customer saw were right.

A trace of an agent is customer data. It holds the questions, the order history and every answer, so the post covers the key, the retention and the access it needs, and how to redact it in the agent. It also points to the NCSC's advice on logging agentic AI.

https://levantar.ai/insights/agentcore-07-observability.html

#AgentCore #AWS #Bedrock #AIAgents #OpenTelemetry
