"""Calling Brightwell's order tools through AgentCore Gateway.

Carried forward from post 02, with one change that is post 05's subject.
The gateway still takes a bearer token minted by Cognito's client_credentials
grant, but the agent no longer holds the client secret or mints the token.
AgentCore Identity keeps the credentials in its token vault and the agent
asks it for a gateway token, presenting the workload access token the
runtime handed it for this request.
"""

import asyncio
import os

import boto3
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

# The gateway namespaces tool names as <target>___<tool>, three underscores.
TARGET = "orders"

_client = None


def client():
    global _client
    if _client is None:
        _client = boto3.client("bedrock-agentcore")
    return _client


def access_token(workload_token):
    """A gateway bearer token from the vault, for this workload, M2M.

    The vault does the client_credentials exchange with Cognito. This call
    returns the resulting access token and does not return the client secret.
    """
    response = client().get_resource_oauth2_token(
        workloadIdentityToken=workload_token,
        resourceCredentialProviderName=os.environ["CREDENTIAL_PROVIDER"],
        scopes=[os.environ["TOKEN_SCOPE"]],
        oauth2Flow="M2M",
    )
    return response["accessToken"]


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


async def _call_tool(tool, arguments, workload_token):
    headers = {"Authorization": f"Bearer {access_token(workload_token)}"}
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


def list_orders(customer_id, workload_token):
    """The customer's orders as the tool returns them, JSON text."""
    return asyncio.run(
        _call_tool("list_orders", {"customer_id": customer_id}, workload_token)
    )
