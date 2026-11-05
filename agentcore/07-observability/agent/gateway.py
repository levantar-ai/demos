"""The order tools, as the gateway publishes them, handed to the model.

Carried forward from post 02 with one change. Earlier posts called a named
tool from code; here the gateway is connected as an MCP server, Strands
discovers the tools it lists, and the model is handed only the ones named
in ALLOWED_TOOLS, by the names the gateway gives them, <target>___<tool>.
The token presented is the one AgentCore Identity obtained on the
customer's behalf (identity.py), never the customer's own, and trusted code
puts it only in the HTTP header of the client built here, never in the
model's prompt, messages or tool arguments. In the supplied Terraform
deployment, Policy in AgentCore evaluates Cedar on every call (gateway.tf,
ENFORCE mode, policy.tf), so a customer_id the model chooses wrongly is
refused at the gateway before the tool runs; this module does not
establish that on its own.
"""

import os

from strands.tools.mcp import MCPClient

# Seam for the tests, which substitute a recorder for the real client.
make_client = MCPClient

# The tools this agent is written for. A target added to the gateway later
# is not handed to the model by accident; it has to be named here first.
ALLOWED_TOOLS = ["orders___list_orders"]


def orders_tools(gateway_token):
    """An MCP client for the order gateway, authenticated with the minted token.

    Strands starts it when the agent loads its tools, and stopping it is
    attempted on agent.cleanup(), with a closer of its own in model.py for
    the case where the agent's build fails part way: made for one answer.
    Only the allowlisted tools are loaded, whatever else the gateway lists.
    """
    return make_client(
        url=os.environ["GATEWAY_URL"],
        headers={"Authorization": f"Bearer {gateway_token}"},
        tool_filters={"allowed": list(ALLOWED_TOOLS)},
    )
