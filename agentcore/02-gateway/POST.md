# Giving your agent tools with AgentCore Gateway

## TL;DR;

How to put AgentCore Gateway in front of an existing Lambda so an agent
can call it as an MCP tool, with IAM doing the authentication so there are
no credentials to manage anywhere.

SOURCE CODE - All code for this post is available at:
https://github.com/levantar-ai/demos/tree/main/agentcore/02-gateway

## Longer version

The agent from the first post could only echo. The way agents become useful
is tools, and the way tools have standardised is MCP. The problem is that
the systems agents need to reach, your internal APIs, your Lambdas, your
SaaS integrations, are not MCP servers and nobody wants to write and host a
fleet of them.

That is the job of AgentCore Gateway. You point it at things you already
have (Lambdas, OpenAPI specs, API Gateway stages) and it presents them to
agents as a single MCP server, handling the protocol, the auth and the tool
schemas. The agent sees a list of tools, the gateway routes each call to
the right backend.

This post puts a gateway in front of one Lambda, an order lookup, and has
the agent from post 01 answer order questions with it:

![Architecture](architecture.png)

## 1 - The tool

The backend is a plain Lambda, no MCP anywhere in it. It takes an order id
and returns what it knows:

```python
ORDERS = {
    "42": {"status": "shipped", "carrier": "DPD", "eta": "2026-07-28"},
    "43": {"status": "picking", "carrier": None, "eta": "2026-07-30"},
    "44": {"status": "delivered", "carrier": "Royal Mail", "eta": None},
}


def handler(event, context):
    order_id = str(event.get("order_id", ""))
    order = ORDERS.get(order_id)
    if order is None:
        return {"error": f"order {order_id} not found"}
    return order
```

The gateway invokes it with the tool arguments as the event, so a Lambda
that already takes its inputs as top-level event fields and returns JSON
needs no changes. A Lambda written for another event shape, API Gateway
style `body` and `pathParameters` for example, would need an adapter.

## 2 - Auth in front of the gateway

The gateway supports three authorizer types, `CUSTOM_JWT`, `AWS_IAM` and
`NONE`, and you want a real one in front of anything beyond a throwaway
experiment. For an agent calling a gateway in the same account this is a
service-to-service call, and AWS's [security best practices for AgentCore Runtime](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-security-best-practices.html)
are explicit about which to pick:

> Use IAM SigV4 for service-to-service calls within AWS. Use JWT bearer
> token authentication when end users authenticate directly through an
> identity provider.

So this demo uses `AWS_IAM`. The agent signs its gateway requests with
the runtime execution role's credentials, the gateway checks the caller's
IAM permission, and there is no client secret, token endpoint or key
rotation anywhere in the stack, nothing to leak because nothing exists.
`CUSTOM_JWT` is the right shape when external or end-user callers arrive
with tokens from an identity provider, and the Identity post later in
this series does that properly with AgentCore Identity holding the
credentials.

## 3 - The gateway and its target

The gateway side is two resources, the gateway itself which is the MCP
endpoint plus its authorizer, and a target which maps a backend into the
tool list:

```hcl
resource "aws_bedrockagentcore_gateway" "orders" {
  name            = "demos-agentcore-02-gateway-gw"
  role_arn        = aws_iam_role.gateway.arn
  protocol_type   = "MCP"
  authorizer_type = "AWS_IAM"
}

resource "aws_bedrockagentcore_gateway_target" "orders" {
  gateway_identifier = aws_bedrockagentcore_gateway.orders.gateway_id
  name               = "orders"

  credential_provider_configuration {
    gateway_iam_role {}
  }

  target_configuration {
    mcp {
      lambda {
        lambda_arn = aws_lambda_function.tool.arn

        tool_schema {
          inline_payload {
            name        = "lookup_order"
            description = "Look up the status of an order by its order id"

            input_schema {
              type = "object"

              property {
                name        = "order_id"
                type        = "string"
                description = "The order id to look up"
                required    = true
              }
            }
          }
        }
      }
    }
  }
}
```

The tool schema you declare here is what agents will see over MCP, so it
all matters, the name, description and input schema are what a model uses
to decide when to call the tool and how to shape the arguments.

The agent's `tools/list` call shows the mapping in action:

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "tools": [
      {
        "name": "orders___lookup_order",
        "description": "Look up the status of an order by its order id",
        "inputSchema": {
          "type": "object",
          "properties": {
            "order_id": {
              "description": "The order id to look up",
              "type": "string"
            }
          },
          "required": ["order_id"]
        }
      }
    ]
  }
}
```

The runtime role gets one extra permission, `bedrock-agentcore:InvokeGateway`
scoped to this gateway's ARN, which is the entire auth setup.

NOTE: the gateway namespaces tool names as `<target>___<tool>` (triple
underscore), so `lookup_order` on the `orders` target becomes
`orders___lookup_order`. Resolve that fully qualified name exactly, two
targets can expose tools with the same short name and a fuzzy match will
happily pick the wrong one.

## 4 - Teaching the agent to call it

The agent gains one function that signs MCP requests with SigV4 using the
runtime role's own credentials (botocore is its first dependency), and
the only configuration the runtime passes in is the gateway URL:

```python
def mcp_request(method, params):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params})
    request = AWSRequest(method="POST", url=os.environ["GATEWAY_URL"], data=body,
                         headers={"Content-Type": "application/json",
                                  "Accept": "application/json, text/event-stream"})
    SigV4Auth(credentials(), "bedrock-agentcore", os.environ["AWS_REGION"]).add_auth(request)
    req = urllib.request.Request(request.url, data=body.encode(),
                                 headers=dict(request.headers), method="POST")
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())


def lookup_order(order_id):
    tool_name = "orders___lookup_order"
    tools = {t["name"] for t in mcp_request("tools/list", {})["result"]["tools"]}
    if tool_name not in tools:
        raise RuntimeError(f"required tool not found: {tool_name}")
    result = mcp_request("tools/call",
                         {"name": tool_name, "arguments": {"order_id": order_id}})
    return result["result"]["content"][0]["text"]
```

This is a minimal gateway-specific client, not a conforming MCP
implementation, it skips the MCP initialize handshake and assumes single
JSON responses rather than handling event streams. For a real agent use an
MCP SDK for the protocol and transport, your application still owns
signing or authenticating the calls, choosing the tool and interpreting
the result.

```hcl
  environment_variables = {
    GATEWAY_URL = aws_bedrockagentcore_gateway.orders.gateway_url
  }
```

The credentials the signature uses come from the runtime's own execution
role, fetched from the environment the platform provides, they never
appear in Terraform, state, or configuration.

There is still no model in this agent, it extracts an order id from the
prompt with a regex, because the thing under demonstration is the tool
path, not the reasoning. A model slots into exactly this shape later in
the series.

## 5 - Asking it questions

```bash
aws bedrock-agentcore invoke-agent-runtime \
  --cli-binary-format raw-in-base64-out \
  --agent-runtime-arn "$RUNTIME_ARN" \
  --runtime-session-id "$SESSION_ID" \
  --payload '{"prompt": "where is order 42?"}' response.json

cat response.json
{"result": "order 42: {\"status\":\"shipped\",\"carrier\":\"DPD\",\"eta\":\"2026-07-28\"}"}
```

The full round trip, agent to gateway to Lambda and back with SigV4 on
each hop, came in at 7.39 seconds in one run on a fresh session including
the microVM cold start, and the tool handles the miss case the same way:

```
"is order 99 ok?"  ->  {"result": "order 99: {\"error\":\"order 99 not found\"}"}
```

## Conclusion

One Lambda and two gateway resources turned a plain function into an MCP
tool an agent can discover and call, with IAM in front of it, no
credentials anywhere in the stack, and without writing or hosting an MCP
server. The same target mechanism scales sideways, more Lambdas, OpenAPI
specs or API Gateway stages all join the same tool list behind the same
endpoint.

The next post gives the agent somewhere to keep what it learns, short-term
session context and long-term extracted memory with AgentCore Memory.

References:

- https://github.com/levantar-ai/demos/tree/main/agentcore/02-gateway
- https://docs.aws.amazon.com/bedrock-agentcore/
- https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/bedrockagentcore_gateway
- https://modelcontextprotocol.io/
