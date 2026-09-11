"""Calling Brightwell's order tools through AgentCore Gateway.

Carried forward from post 02. The token presented here is the one AgentCore
Identity obtained on the customer's behalf (see identity.py), minted by the
exchange pool for the audience this gateway is configured to accept. It is never the customer's own
Cognito token, which the gateway no longer accepts. The gateway validates the
token against the exchange issuer, and Policy in AgentCore then evaluates a
Cedar policy on every call and refuses a list_orders whose customer_id
differs from the token's customer_id claim, which is why this module does no
authorization of its own. The orders Lambda still returns only that
customer's rows; Cedar sees the call, not the result.
"""

import asyncio
import os

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

# The gateway namespaces tool names as <target>___<tool>, three underscores.
TARGET = "orders"


def _result_text(result):
    """Pull the text out of an MCP tool result, refusing anything unexpected.

    A tool that sets isError still arrives as a well-formed response, so
    without this check a failure, including a policy denial, reads as an
    answer.
    """
    if result.isError:
        raise RuntimeError(f"tool reported an error: {result.content}")
    for item in result.content or []:
        if getattr(item, "type", None) == "text":
            return item.text
    raise RuntimeError(f"tool returned no text content: {result.content}")


async def _call_tool(tool, arguments, gateway_token):
    headers = {"Authorization": f"Bearer {gateway_token}"}
    async with (
        streamablehttp_client(os.environ["GATEWAY_URL"], headers=headers) as (
            read,
            write,
            _,
        ),
        ClientSession(read, write) as session,
    ):
        await session.initialize()
        result = await session.call_tool(f"{TARGET}___{tool}", arguments)
        return _result_text(result)


def list_orders(customer_id, gateway_token):
    """The customer's orders as the tool returns them, JSON text.

    The gateway is called with the token minted for this customer, and the
    policy engine permits list_orders only when customer_id matches the
    customer_id claim in that token, so a mismatched id is denied at the
    gateway before the tool runs.
    """
    return asyncio.run(
        _call_tool("list_orders", {"customer_id": customer_id}, gateway_token)
    )
