# LinkedIn post — the model decides (post 06)

Live: https://levantar.ai/insights/agentcore-06-model-in-the-loop.html
Native image: social-square.png (1200x1200). Or share the URL and the
og:image renders the 1200x630 card. The demo video uploads natively too.

---

Post six of the AgentCore series. The same order-support agent, and for the
first time a model decides what it does.

Five posts built the primitives, a runtime, a gateway, memory, a sandbox and
an identity chain, and every one of them routed the prompt with code. This
post hands those primitives to Claude on Bedrock as tools and asks a question
nobody wrote code for. The model fetches the orders through the gateway,
writes the pandas itself, runs it in the sandbox and answers, and the response
carries the trail of what it chose.

What makes that safe is that identity stayed in trusted code. The model is
told which customer it acts for and chooses the arguments. It never holds the
token. Ask it to be someone else and it declines, and if it were ever talked
round, the Cedar policy at the gateway refuses the call before the tool runs.

The full walkthrough and the code are here.
https://levantar.ai/insights/agentcore-06-model-in-the-loop.html

#AgentCore #AWS #AI #Agents #Bedrock
