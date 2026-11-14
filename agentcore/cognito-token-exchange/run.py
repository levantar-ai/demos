"""Cognito's own token exchange behind AgentCore Identity, end to end, then torn down.

    aws-vault exec <profile> -- python3 run.py

Creates, in us-east-1, a Cognito pool on the Essentials plan with a managed
login domain, an `orders` resource server, a customer app client, an agent app
client allowed to exchange tokens, one test customer, an AgentCore workload
identity and two on-behalf-of credential providers, one per mode. It runs the
exchange through AgentCore Identity in both modes, shows the requests Cognito
refuses, and deletes everything in a finally block. Pool, client and customer ids are
redacted in what it prints, and nothing is written to disk.
"""

import base64
import json
import secrets
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

import boto3
import jwt

REGION = "us-east-1"
TOKEN_EXCHANGE = "urn:ietf:params:oauth:grant-type:token-exchange"
ACCESS_TOKEN = "urn:ietf:params:oauth:token-type:access_token"
JWT_TYPE = "urn:ietf:params:oauth:token-type:jwt"
SHOWN = ("username", "client_id", "aud", "scope", "act")

idp = boto3.client("cognito-idp", region_name=REGION)
control = boto3.client("bedrock-agentcore-control", region_name=REGION)
data = boto3.client("bedrock-agentcore", region_name=REGION)
made = {}  # what exists, so the finally block deletes exactly that
redactions = {}


def redact(value):
    text = json.dumps(value)
    for real, label in redactions.items():
        text = text.replace(real, label)
    return text


def claims(token):
    """The token's claims, verified against the pool's signing keys and issuer, with its lifetime."""
    key = jwt.PyJWKClient(f"{made['issuer']}/.well-known/jwks.json").get_signing_key_from_jwt(token).key
    # leeway: a laptop or VM clock a minute or two adrift should not fail the check
    c = jwt.decode(token, key, algorithms=["RS256"], issuer=made["issuer"], options={"verify_aud": False}, leeway=300)
    return {**{k: c[k] for k in SHOWN if k in c}, "lifetime_s": c["exp"] - c["iat"], "exp": c["exp"]}


def token_endpoint(form):
    """POST to the pool's token endpoint as the agent's client. Returns (status, body)."""
    basic = base64.b64encode(f"{made['agent']}:{made['agent_secret']}".encode()).decode()
    req = urllib.request.Request(
        f"https://{made['domain']}.auth.{REGION}.amazoncognito.com/oauth2/token",
        data=urllib.parse.urlencode(form).encode(),
        headers={"Authorization": f"Basic {basic}", "Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:  # nosec B310 - fixed https endpoint
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def build():
    suffix = secrets.token_hex(4)
    made["pool_name"] = f"demos-tokenx-{suffix}"  # recorded first, so teardown can find a pool whose create response was lost
    pool = idp.create_user_pool(
        PoolName=made["pool_name"],
        UserPoolTier="ESSENTIALS",
        AdminCreateUserConfig={"AllowAdminCreateUserOnly": True},
        UserPoolTags={"Project": "demos", "Demo": "cognito-token-exchange"},
    )["UserPool"]["Id"]
    made["pool"] = pool
    made["issuer"] = f"https://cognito-idp.{REGION}.amazonaws.com/{pool}"
    redactions[pool] = "<pool>"

    # The token endpoint refused exchanges until the domain used managed login version 2.
    made["domain"] = f"demos-tokenx-{suffix}"
    idp.create_user_pool_domain(Domain=made["domain"], UserPoolId=pool, ManagedLoginVersion=2)
    idp.create_resource_server(
        UserPoolId=pool, Identifier="orders", Name="orders", Scopes=[{"ScopeName": "read", "ScopeDescription": "read orders"}]
    )

    made["customers"] = idp.create_user_pool_client(
        UserPoolId=pool, ClientName="customers", ExplicitAuthFlows=["ALLOW_USER_PASSWORD_AUTH", "ALLOW_REFRESH_TOKEN_AUTH"]
    )["UserPoolClient"]["ClientId"]
    agent = idp.create_user_pool_client(
        UserPoolId=pool,
        ClientName="agent",
        GenerateSecret=True,
        # The two new flows. boto3 passes them through; the Terraform provider rejects them.
        ExplicitAuthFlows=["ALLOW_TOKEN_EXCHANGE_IMPERSONATION", "ALLOW_TOKEN_EXCHANGE_DELEGATION", "ALLOW_REFRESH_TOKEN_AUTH"],
        AllowedOAuthFlows=["client_credentials"],  # for the actor token in delegation mode
        AllowedOAuthScopes=["orders/read"],
        AllowedOAuthFlowsUserPoolClient=True,
    )["UserPoolClient"]
    made["agent"], made["agent_secret"] = agent["ClientId"], agent["ClientSecret"]
    redactions.update({made["customers"]: "<customer client>", made["agent"]: "<agent client>"})

    made["password"] = "Aa1!" + secrets.token_urlsafe(24)
    idp.admin_create_user(UserPoolId=pool, Username="c-1000", MessageAction="SUPPRESS")
    idp.admin_set_user_password(UserPoolId=pool, Username="c-1000", Password=made["password"], Permanent=True)

    # Names are recorded before each create, so teardown finds anything a failed create left behind.
    made["workload"] = f"demos-tokenx-{suffix}"
    control.create_workload_identity(name=made["workload"])
    made["providers"] = []
    for mode, actor in (("impersonation", {"actorTokenContent": "NONE"}),
                        ("delegation", {"actorTokenContent": "M2M", "actorTokenScopes": ["orders/read"]})):
        name = f"demos-tokenx-{suffix}-{mode}"
        made["providers"].append((mode, name))
        control.create_oauth2_credential_provider(
            name=name,
            credentialProviderVendor="CustomOauth2",
            oauth2ProviderConfigInput={"customOauth2ProviderConfig": {
                "oauthDiscovery": {"discoveryUrl": f"{made['issuer']}/.well-known/openid-configuration"},
                "clientId": made["agent"],
                "clientSecret": made["agent_secret"],
                "clientAuthenticationMethod": "CLIENT_SECRET_BASIC",
                "onBehalfOfTokenExchangeConfig": {"grantType": "TOKEN_EXCHANGE", "tokenExchangeGrantTypeConfig": actor},
            }},
        )

    # A new domain takes a minute or two to resolve and answer.
    status = None
    for _ in range(30):
        try:
            status, _body = token_endpoint({"grant_type": "client_credentials", "scope": "orders/read"})
        except urllib.error.URLError as e:
            status = e.reason
        if status == 200:
            return
        time.sleep(10)
    raise RuntimeError(f"the token endpoint never answered, last result {status}")


def exercise():
    customer = idp.initiate_auth(
        ClientId=made["customers"], AuthFlow="USER_PASSWORD_AUTH",
        AuthParameters={"USERNAME": "c-1000", "PASSWORD": made["password"]},
    )["AuthenticationResult"]["AccessToken"]
    redactions[jwt.decode(customer, options={"verify_signature": False})["sub"]] = "<customer sub>"
    own = claims(customer)
    print("customer's own token", redact(own))

    workload = data.get_workload_access_token_for_jwt(workloadName=made["workload"], userToken=customer)["workloadAccessToken"]

    def through_agentcore(provider, **extra):
        return data.get_resource_oauth2_token(
            workloadIdentityToken=workload, resourceCredentialProviderName=provider,
            oauth2Flow="ON_BEHALF_OF_TOKEN_EXCHANGE", scopes=[], audiences=["orders"], **extra,
        )["accessToken"]

    for mode, provider in made["providers"]:
        token = claims(through_agentcore(provider, customParameters={"subject_token_type": ACCESS_TOKEN}))
        print(f"\nAgentCore Identity, {mode}", redact(token))
        print("  expires no later than the customer's token:", token["exp"] <= own["exp"])

    print("\nRefused")
    try:
        through_agentcore(made["providers"][0][1])
        print("  AgentCore without the subject token type: unexpectedly accepted")
    except data.exceptions.ValidationException as e:
        print("  AgentCore without the subject token type:", str(e).split(": ", 1)[-1])
    base = {"grant_type": TOKEN_EXCHANGE, "subject_token": customer, "audience": "orders"}
    for label, form in (("subject typed as a generic JWT", {**base, "subject_token_type": JWT_TYPE}),
                        ("asking for orders/read", {**base, "subject_token_type": ACCESS_TOKEN, "scope": "orders/read"})):
        status, body = token_endpoint(form)
        print(f"  token endpoint, {label}: {status} {redact(body)}")


def teardown():
    """Delete what build() made, newest first. Returns whatever could not be deleted."""
    steps = [(f"provider {n}", lambda n=n: control.delete_oauth2_credential_provider(name=n))
             for _, n in made.get("providers", [])]
    if "workload" in made:
        steps.append(("workload identity", lambda: control.delete_workload_identity(name=made["workload"])))
    if "domain" in made:
        steps.append(("domain", lambda: idp.delete_user_pool_domain(Domain=made["domain"], UserPoolId=made["pool"])))
    if "pool" not in made and "pool_name" in made:
        for found in idp.list_user_pools(MaxResults=60)["UserPools"]:
            if found["Name"] == made["pool_name"]:
                made["pool"] = found["Id"]
    if "pool" in made:
        steps.append(("pool", lambda: idp.delete_user_pool(UserPoolId=made["pool"])))
    left = []
    for label, step in steps:
        for attempt in range(3):
            try:
                step()
                print(f"deleted {label}")
                break
            except Exception as e:  # noqa: BLE001 - report and keep deleting the rest
                if "NotFound" in type(e).__name__:
                    print(f"already gone {label}")
                    break
                if attempt == 2:
                    print(f"FAILED to delete {label}: {e}")
                    left.append(label)
                else:
                    time.sleep(10)
    return left


if __name__ == "__main__":
    left = []
    try:
        build()
        exercise()
    finally:
        print()
        left = teardown()
        if left:
            print("LEFT BEHIND, delete these by hand:", ", ".join(left))
    sys.exit(1 if left else 0)
