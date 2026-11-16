# LinkedIn post, the Cognito token exchange insight

Live: https://levantar.ai/insights/cognito-token-exchange.html
Native image: social-square.png (1200x1200), post 05's architecture with the
part Cognito removes in red. Or share the URL and the og:image renders the
1200x630 card. To re-render the square, run `scripts/render-social.py` on a
folder holding a one-line POST.md title and a diagram.py that renders post
05's diagram and runs highlight.py on it.

---

Last week AWS added OAuth 2.0 token exchange to Amazon Cognito. We had it running behind AgentCore Identity the next day.

It matters to us because post 05 of our AgentCore series had to build that exchange by hand, a front door on API Gateway and Lambda, a second user pool and four Lambda triggers, so an agent could act for one customer with a token minted for that customer. Cognito can now do that itself, and in delegation mode the token names the agent as well as the customer.

It is also stricter than ours was. Our trigger added a scope the customer's own token never carried. Nothing checked it, but Cognito will only pass on scopes the customer already holds, and that is the right rule for an agent acting on someone's behalf.

Four things caught us out on the way, from the login domain the token endpoint wanted to a Terraform provider that does not know the new client settings yet. They are all in the post, with post 05's architecture showing what goes and the script that ran the test.

https://levantar.ai/insights/cognito-token-exchange.html

#AgentCore #AWS #AmazonCognito #OAuth #AIAgents
