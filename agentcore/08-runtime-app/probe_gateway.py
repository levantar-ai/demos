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
            if result.isError:
                print(f"tool error for {customer_id}: {result.content}")
                return
            text = "".join(
                i.text for i in (result.content or []) if getattr(i, "type", None) == "text"
            )
            orders = json.loads(text).get("orders", [])
            print(f"allowed: {len(orders)} orders for {customer_id}")
    except BaseException as err:  # noqa: BLE001 - classify the failure honestly
        # The MCP client wraps the failure in nested task groups; walk to the
        # leaf without naming BaseExceptionGroup, which ruff flags on 3.10.
        leaf = err
        while getattr(leaf, "exceptions", None):
            leaf = leaf.exceptions[0]
        # Only call it a policy denial when the gateway actually says so; a
        # network or protocol failure is not a proof of enforcement.
        if "policy enforcement" in str(leaf).lower() or "denied by default" in str(leaf).lower():
            print(f"denied by the gateway: {leaf}")
        else:
            print(f"error (not a policy decision) for {customer_id}: {type(leaf).__name__}: {leaf}")


asyncio.run(main())
