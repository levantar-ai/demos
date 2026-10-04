"""The order tools, as the gateway publishes them, handed to the model.

Carried forward from post 02 with one change. Earlier posts called a named
tool from code; here the gateway is connected as an MCP server and whatever
tools it lists are the ones the model may choose from, by the names the
gateway gives them, <target>___<tool>. The token presented is the one
AgentCore Identity obtained on the customer's behalf (identity.py), never
the customer's own, and the model never sees it: it travels in the HTTP
header of a client that trusted code built. Policy in AgentCore still
evaluates Cedar on every call, so a customer_id the model chooses wrongly
is refused at the gateway before the tool runs.
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

    Strands starts it when the agent loads its tools and stops it on
    agent.cleanup(), so the connection lives exactly as long as one answer.
    Only the allowlisted tools are loaded, whatever else the gateway lists.
    """
    return make_client(
        url=os.environ["GATEWAY_URL"],
        headers={"Authorization": f"Bearer {gateway_token}"},
        tool_filters={"allowed": list(ALLOWED_TOOLS)},
    )
