"""Getting the agent a token to call the order service, from AgentCore Identity.

Post 05's subject. The agent does not relay the customer's raw Cognito token to
the gateway, and the gateway accepts no static agent credential. It asks
AgentCore Identity, on behalf of the customer, to exchange the customer's
inbound JWT for a short-lived token whose audience is the exchange pool's orders
app client, the audience the order gateway is configured to accept.
That is the on-behalf-of flow: the agent's explicitly declared workload
identity plus the customer's token, exchanged at the credential provider,
which brokers RFC 8693 against the exchange service. Cognito's token endpoint
does not offer that grant, so the provider points at a small front door (see
exchange/) in front of a second Cognito pool that mints the token through its
custom authentication flow. The gateway trusts that pool; Cedar still checks
the customer, from the token's customer_id claim.
"""

import os
import time

import boto3
from botocore.exceptions import ClientError
from trail import describe

_agentcore = None

# An occasional first request after an idle period came back from
# GetResourceOauth2Token as a ValidationException whose message named the
# token endpoint, "HTTP request failed against Token endpoint". That one
# failure is retried once after a pause; anything else is raised as it is.
RETRY_AFTER_SECONDS = 2
_TRANSIENT_CODE = "ValidationException"
_TRANSIENT_TEXT = "Token endpoint"


def _transient(exc):
    error = (getattr(exc, "response", None) or {}).get("Error", {})
    return error.get("Code") == _TRANSIENT_CODE and _TRANSIENT_TEXT in error.get("Message", "")


def _client():
    global _agentcore
    if _agentcore is None:
        _agentcore = boto3.client("bedrock-agentcore")
    return _agentcore


def orders_token(inbound_jwt: str) -> str:
    """A token for the order gateway, minted on behalf of the customer.

    Two AgentCore Identity calls: first exchange the customer's inbound JWT for
    a workload access token that represents the agent acting for that customer,
    then use it to request the on-behalf-of resource token. The exchange pool's
    pre-token trigger copies the customer token's verified username into the
    minted token's customer_id claim, which the gateway's Cedar policy compares
    with the customer_id every list_orders call asks for.
    """
    client = _client()
    workload_token = client.get_workload_access_token_for_jwt(
        workloadName=os.environ["WORKLOAD_NAME"],
        userToken=inbound_jwt,
    )["workloadAccessToken"]

    request = {
        "workloadIdentityToken": workload_token,
        "resourceCredentialProviderName": os.environ["OBO_PROVIDER_NAME"],
        "scopes": [os.environ["ORDERS_SCOPE"]],
        "oauth2Flow": "ON_BEHALF_OF_TOKEN_EXCHANGE",
    }
    try:
        result = client.get_resource_oauth2_token(**request)
    except ClientError as exc:
        if not _transient(exc):
            raise
        print(f"exchange failed once, retrying in {RETRY_AFTER_SECONDS}s: {describe(exc)}")
        time.sleep(RETRY_AFTER_SECONDS)
        result = client.get_resource_oauth2_token(**request)
    token = result.get("accessToken")
    if not isinstance(token, str) or not token.strip():
        # This provider performs a back-channel exchange and returns no consent
        # URL; any delegation it needs is established at the provider already.
        # Anything but a token is a failure we must not treat as an answer.
        raise RuntimeError(f"no on-behalf-of token returned: {result.get('sessionStatus')}")
    return token
