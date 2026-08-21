"""Calling Brightwell's order tools through AgentCore Gateway.

Carried forward from post 02 so this demo stands alone. The gateway takes a
bearer token, so this is the stock MCP client with an Authorization header,
and the client secret is read from Secrets Manager with the runtime role.
Post 04 adds list_orders, which is what the reconciliation joins against.
"""

import asyncio
import base64
import json
import os
import threading
import time
import urllib.parse
import urllib.request

import boto3
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

# The gateway namespaces tool names as <target>___<tool>, three underscores.
TARGET = "orders"

# Tokens are reused until shortly before they expire.
EXPIRY_MARGIN = 60
_token = {"value": None, "expires_at": 0.0}
_token_lock = threading.Lock()


def _client_credentials():
    secret = boto3.client("secretsmanager").get_secret_value(
        SecretId=os.environ["CLIENT_SECRET_ARN"]
    )
    credentials = json.loads(secret["SecretString"])
    return credentials["client_id"], credentials["client_secret"]


def access_token():
    # Double-checked under the lock: the server is threaded, so without it a
    # burst of requests around expiry would each fetch the secret and mint a
    # token rather than sharing one.
    if _token["value"] and time.time() < _token["expires_at"]:
        return _token["value"]

    with _token_lock:
        if _token["value"] and time.time() < _token["expires_at"]:
            return _token["value"]

        client_id, client_secret = _client_credentials()
        form = urllib.parse.urlencode(
            {"grant_type": "client_credentials", "scope": os.environ["TOKEN_SCOPE"]}
        ).encode()
        # Credentials go in the Authorization header, not the form body, which
        # keeps them out of anything that logs request bodies.
        basic = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
        request = urllib.request.Request(
            os.environ["TOKEN_URL"],
            data=form,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Authorization": f"Basic {basic}",
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            payload = json.loads(response.read())

        _token["value"] = payload["access_token"]
        _token["expires_at"] = time.time() + payload["expires_in"] - EXPIRY_MARGIN
        return _token["value"]


def _result_text(result):
    """Pull the text out of an MCP tool result, refusing anything unexpected.

    A tool that sets isError still arrives as a well-formed response, so
    without this check a failure reads as an answer.
    """
    if result.isError:
        raise RuntimeError(f"tool reported an error: {result.content}")
    for item in result.content or []:
        if getattr(item, "type", None) == "text":
            return item.text
    raise RuntimeError(f"tool returned no text content: {result.content}")


async def _call_tool(tool, arguments):
    headers = {"Authorization": f"Bearer {access_token()}"}
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


def lookup_order(order_id):
    return asyncio.run(_call_tool("lookup_order", {"order_id": order_id}))


def list_orders(customer_id):
    """The customer's orders as the tool returns them, JSON text."""
    return asyncio.run(_call_tool("list_orders", {"customer_id": customer_id}))
