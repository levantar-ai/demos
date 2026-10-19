# LinkedIn post — the model decides (post 06)

Live: https://levantar.ai/insights/agentcore-06-model-in-the-loop.html
Native image: social-square.png (1200x1200). Or share the URL and the
og:image renders the 1200x630 card. The demo video uploads natively too.

---

Post six of the AgentCore series, where one order support agent gains a capability with each post. This time a model decides what the agent does.

Claude on Bedrock gets the gateway and the Code Interpreter sandbox as tools, with AgentCore Memory as context. Ask how much you have spent this year by month and it fetches your orders, writes the code and runs it in the sandbox.

Trusted code hands the order data to the sandbox, so the model never retypes rows. A check after each answer names any figure no tool printed and asks the model to restate.

Each customer who signs in can only reach their own orders. The model never holds the token, and the Cedar policy at the gateway refuses a lookup for anyone else.

The model can still get a figure wrong, so its answers should inform rather than decide anything that costs money.

https://levantar.ai/insights/agentcore-06-model-in-the-loop.html

#AgentCore #AWS #Bedrock #AIAgents
