"""Getting the agent a token to call the order service, from AgentCore Identity.

Post 05's subject. The agent does not relay the customer's raw Cognito token to
the gateway, and the gateway accepts no static agent credential. It asks
AgentCore Identity, on behalf of the customer, to exchange the customer's
inbound JWT for a short-lived token audience-restricted to the order gateway.
That is the on-behalf-of flow: the agent's explicitly declared workload
identity plus the customer's token, exchanged at the credential provider,
which brokers RFC 8693 against the exchange service. Cognito's token endpoint
does not offer that grant, so the provider points at a self-hosted exchange
service (see exchange/). The gateway trusts that service; Cedar still checks
the customer.
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
    carries the customer's username, which the gateway's Cedar policy compares
    with the customer_id every list_orders call asks for.
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
        # This provider performs a back-channel exchange and returns no consent
        # URL; any delegation it needs is established at the provider already.
        # Anything but a token is a failure we must not treat as an answer.
        raise RuntimeError(f"no on-behalf-of token returned: {result.get('sessionStatus')}")
    return token
