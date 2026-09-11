"""Generate the architecture diagram for post 05.

Run from this directory: python3 diagram.py
Produces architecture.png referenced by POST.md.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "scripts"))

from diagram_sizing import cluster_margin
from diagram_sizing import fs as _fs
from diagram_sizing import node_height as _h
from diagrams import Cluster, Diagram, Edge
from diagrams.aws.compute import Lambda
from diagrams.aws.ml import Bedrock
from diagrams.aws.network import APIGateway
from diagrams.aws.security import Cognito, IdentityAndAccessManagementIamPermissions
from diagrams.onprem.client import User
from diagrams.programming.language import Python

graph_attr = {
    "pad": "0.6",
    "nodesep": "0.7",
    "ranksep": "1.1",
    "fontsize": _fs(20),
    "fontcolor": "#0e1216",
    "labelloc": "t",
}
node_attr = {"fontsize": _fs(13)}
edge_attr = {"fontsize": _fs(12), "fontcolor": "#4a5158"}

# The agent does not relay the customer's Cognito token to the gateway. It asks
# AgentCore Identity, on the customer's behalf, to exchange that token for one
# audience-restricted to the order gateway: the on-behalf-of flow. Cognito's
# token endpoint does not offer the RFC 8693 grant, so, as in AWS's
# sample-cognito-oauth2-token-exchange, a small front door implements the
# grant and a second Cognito pool mints the token through its custom
# authentication flow. The gateway trusts that pool; Cedar still checks the
# customer. Inbound auth on the runtime is unchanged.

with Diagram(
    "The agent's order-service token, brokered by AgentCore Identity on the customer's behalf",
    filename=os.environ.get("DIAGRAM_OUT", "architecture"),
    outformat="png",
    show=False,
    direction="LR",
    graph_attr=graph_attr,
    node_attr=node_attr,
    edge_attr=edge_attr,
):
    customer = User("customer\n(Bearer JWT)", height=_h(2))
    cognito = Cognito("customer pool", height=_h(1))

    with Cluster(
        "AgentCore Runtime",
        graph_attr={"fontsize": _fs(15), "margin": cluster_margin(), "bgcolor": "#f6f3ec"},
    ):
        rt_auth = Bedrock("AgentCore Identity\ninbound auth\n(CUSTOM_JWT)", height=_h(3))
        agent = Python("agent", height=_h(1))

    with Cluster(
        "AgentCore Identity  -  on behalf of the customer",
        graph_attr={"fontsize": _fs(15), "margin": cluster_margin(), "bgcolor": "#eef3f1"},
    ):
        identity = Bedrock(
            "workload identity,\nOBO credential provider,\nToken Vault", height=_h(3)
        )

    with Cluster(
        "token exchange  -  the AWS sample's shape: a front door, a second Cognito pool mints",
        graph_attr={"fontsize": _fs(15), "margin": cluster_margin(), "bgcolor": "#f3eeee"},
    ):
        exchange = Lambda("front door (RFC 8693)\nclient secret, request checks,\nverifies the customer's JWT", height=_h(3))
        pool2 = Cognito("exchange pool\ntriggers verify again, then\nCognito mints, 5 min", height=_h(3))

    with Cluster(
        "AgentCore Gateway  -  Policy in AgentCore evaluates Cedar per call",
        graph_attr={"fontsize": _fs(15), "margin": cluster_margin(), "bgcolor": "#efece4"},
    ):
        gw_auth = Bedrock("JWT authorizer\ntrusts the exchange pool,\naud = orders client", height=_h(3))
        gateway = APIGateway("gateway", height=_h(1))
        policy = IdentityAndAccessManagementIamPermissions(
            "Cedar policy\ncustomer_id ==\ntoken customer_id", height=_h(3)
        )

    orders = Lambda("orders", height=_h(1))

    # Inbound, unchanged: the customer's Cognito token, validated at the runtime.
    customer >> Edge(label="sign in", style="dashed") >> cognito
    customer >> Edge(label="invoke\n(Bearer JWT)") >> rt_auth
    rt_auth >> Edge(label="validated") >> agent

    # On behalf of the customer: the agent asks AgentCore Identity for a token
    # for the order service. Identity brokers the RFC 8693 exchange with the
    # customer's token as the subject; the front door runs the exchange pool's
    # custom auth flow with that token as the answer, and Cognito mints.
    agent >> Edge(label="a token for the order service,\non behalf of the customer") >> identity
    identity >> Edge(label="RFC 8693 exchange\n(subject = the customer's JWT)") >> exchange
    exchange >> Edge(label="CUSTOM_AUTH,\nanswer = the customer's JWT") >> pool2

    # The minted token, not the customer's, goes to the gateway.
    agent >> Edge(label="list_orders\n(the minted token,\n5 min, aud = orders client)") >> gw_auth
    gw_auth >> Edge(label="validated") >> gateway
    gateway >> Edge(label="evaluate", style="dashed") >> policy
    gateway >> Edge(label="matching customer_id:\npermit the call") >> orders
