# LinkedIn post, the SDK's server (post 08)

Live: https://levantar.ai/insights/agentcore-08-runtime-app.html
Native image: social-square.png (1200x1200). Or share the URL and the
og:image renders the 1200x630 card. The demo video uploads natively too.

---

Post eight of the AgentCore series, where one order support agent gains a capability with each post. This time it loses something, the HTTP server the series wrote by hand in post 01.

The agent now runs on BedrockAgentCoreApp, the server in AWS's bedrock-agentcore Python SDK. The agent becomes one function, and the SDK serves the runtime's /invocations and /ping contract around it.

The tracing code from post 07 goes as well. The SDK's app is a Starlette application, which the AWS Distro for OpenTelemetry instruments, and AgentCore Runtime sends the session id in the request's baggage. Each turn is still one trace in CloudWatch with the session id on every span, with no code of the agent's doing it.

The SDK does not do everything for you. It puts no limit on a request body or on the turns in flight, and an exception that escapes your function goes back to the client with its message. The post shows the small piece of middleware and the catch that keep both in the agent's hands.

https://levantar.ai/insights/agentcore-08-runtime-app.html

#AgentCore #AWS #Bedrock #AIAgents #OpenTelemetry
