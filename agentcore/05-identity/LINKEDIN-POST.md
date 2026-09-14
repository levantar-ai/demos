# LinkedIn post — AgentCore Identity (post 05)

Live: https://levantar.ai/insights/agentcore-05-identity.html
Native image: social-square.png (1200x1200). Or share the URL and the
og:image renders the 1200x630 card. The demo video uploads natively too.

---

Post five of the AgentCore series. The same order-support agent, now given
an identity at both ends.

Inbound, AgentCore Identity validates the customer's sign-in token, so the
agent knows who is asking.

Outbound is the harder half. The agent never relays the customer's token to
the order service. It asks AgentCore Identity for a token minted for that
customer on their behalf, and a Cedar policy at the gateway refuses any call
for anyone else. The customer's own token gets a 403 there.

Cognito's token endpoint does not offer the exchange grant this needs, so the
exchange is built the way AWS's own sample builds it, a second Cognito pool
that mints, with an audience, a confidential client and a five-minute token
added on top.

This one is a real step up in moving parts, and the post is honest about what
each still does not guarantee. In production the exchange belongs to a managed
IdP, not a pool you run.

The full walkthrough and the code are here.
https://levantar.ai/insights/agentcore-05-identity.html

#AgentCore #AWS #AI #Identity
