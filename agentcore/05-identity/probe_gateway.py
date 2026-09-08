"""Call the orders gateway directly as the signed-in customer, to show Policy
in AgentCore enforcing. Pass a customer_id: your own is allowed, anyone
else's is denied at the gateway before the tool runs.

Usage: GATEWAY_URL=... TOKEN=... python3 probe_gateway.py <customer_id>
"""

import asyncio
import json
import os
import sys

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client


async def main():
    customer_id = sys.argv[1]
    headers = {"Authorization": f"Bearer {os.environ['TOKEN']}"}
    try:
        async with (
            streamablehttp_client(os.environ["GATEWAY_URL"], headers=headers) as (r, w, _),
            ClientSession(r, w) as session,
        ):
            await session.initialize()
            result = await session.call_tool("orders___list_orders", {"customer_id": customer_id})
            text = "".join(
                i.text for i in (result.content or []) if getattr(i, "type", None) == "text"
            )
            orders = json.loads(text).get("orders", [])
            print(f"allowed: {len(orders)} orders for {customer_id}")
    except BaseException as err:  # noqa: BLE001 - surface the gateway's denial
        # The MCP client wraps the denial in nested task groups; walk to the
        # leaf without naming BaseExceptionGroup, which ruff flags on 3.10.
        leaf = err
        while getattr(leaf, "exceptions", None):
            leaf = leaf.exceptions[0]
        print(f"denied by the gateway: {leaf}")


asyncio.run(main())
