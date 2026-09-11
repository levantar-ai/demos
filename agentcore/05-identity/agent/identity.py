"""Getting the agent a token to call the order service, from AgentCore Identity.

Post 05's subject. The agent does not relay the customer's raw Cognito token to
the gateway, and it holds no static credential. It asks AgentCore Identity, on
behalf of the customer, to exchange the customer's inbound JWT for a short-lived
token scoped to the order gateway. That is the on-behalf-of flow: the runtime's
workload identity plus the customer's token, exchanged at the credential
provider, which brokers RFC 8693 against the exchange service. Cognito cannot be
that exchange target, so the provider points at a self-hosted exchange service
(see exchange/). The gateway trusts that service; Cedar still checks the customer.
"""

import os

import boto3

_agentcore = None


def _client():
    global _agentcore
    if _agentcore is None:
        _agentcore = boto3.client("bedrock-agentcore")
    return _agentcore


def orders_token(inbound_jwt: str) -> str:
    """A token for the order gateway, minted on behalf of the customer.

    Two AgentCore Identity calls: first exchange the customer's inbound JWT for
    a workload access token that represents the agent acting for that customer,
    then use it to request the on-behalf-of resource token. The exchanged token
    carries the customer's username, so the gateway's Cedar policy still refuses
    anything outside that customer's orders.
    """
    client = _client()
    workload_token = client.get_workload_access_token_for_jwt(
        workloadName=os.environ["WORKLOAD_NAME"],
        userToken=inbound_jwt,
    )["workloadAccessToken"]

    result = client.get_resource_oauth2_token(
        workloadIdentityToken=workload_token,
        resourceCredentialProviderName=os.environ["OBO_PROVIDER_NAME"],
        scopes=[os.environ["ORDERS_SCOPE"]],
        oauth2Flow="ON_BEHALF_OF_TOKEN_EXCHANGE",
    )
    token = result.get("accessToken")
    if not isinstance(token, str) or not token.strip():
        # On-behalf-of is a back-channel exchange; there is no consent URL to
        # follow. Anything else is a failure we must not treat as an answer.
        raise RuntimeError(f"no on-behalf-of token returned: {result.get('sessionStatus')}")
    return token
