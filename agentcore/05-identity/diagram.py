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

# Inbound Auth is one half of AgentCore Identity (the other is Outbound Auth);
# AWS documents JWT authentication for the runtime and gateway as being done
# "with AgentCore Identity". It is not a shared service the two endpoints call
# out to. It is a CUSTOM_JWT authorizer configured on each of them, validating
# the customer's Cognito token at that endpoint's door before the request
# reaches the agent or the gateway tool. So it is drawn as a checkpoint inside
# each cluster, on the way in, using the pool's OIDC discovery to fetch and
# cache the JWKS it validates against.
IDENTITY = "AgentCore Identity\ninbound auth\n(CUSTOM_JWT)"

with Diagram(
    "The customer's identity enforced at the gateway",
    filename=os.environ.get("DIAGRAM_OUT", "architecture"),
    outformat="png",
    show=False,
    direction="LR",
    graph_attr=graph_attr,
    node_attr=node_attr,
    edge_attr=edge_attr,
):
    customer = User("customer\n(Bearer JWT)", height=_h(2))
    cognito = Cognito("Cognito pool", height=_h(1))

    with Cluster(
        "AgentCore Runtime",
        graph_attr={"fontsize": _fs(15), "margin": cluster_margin(), "bgcolor": "#f6f3ec"},
    ):
        rt_auth = Bedrock(IDENTITY, height=_h(2))
        agent = Python("agent", height=_h(1))

    with Cluster(
        "AgentCore Gateway  -  Policy in AgentCore evaluates Cedar per call",
        graph_attr={"fontsize": _fs(15), "margin": cluster_margin(), "bgcolor": "#efece4"},
    ):
        gw_auth = Bedrock(IDENTITY, height=_h(2))
        gateway = APIGateway("gateway", height=_h(1))
        policy = IdentityAndAccessManagementIamPermissions(
            "Cedar policy\ncustomer_id ==\ncaller's username", height=_h(2)
        )

    orders = Lambda("orders", height=_h(1))

    # Main request path, left to right. The customer's token passes through the
    # runtime authorizer before the agent runs, and through the gateway
    # authorizer before the gateway processes the call.
    customer >> Edge(label="sign in", style="dashed") >> cognito
    customer >> Edge(label="invoke\n(Bearer JWT)") >> rt_auth
    rt_auth >> Edge(label="validated") >> agent
    agent >> Edge(label="list_orders\n(customer's JWT)") >> gw_auth
    gw_auth >> Edge(label="validated") >> gateway
    gateway >> Edge(label="evaluate", style="dashed") >> policy
    gateway >> Edge(label="permit:\ncaller's own orders") >> orders

    # Each authorizer is configured with the pool's discovery URL and fetches
    # the OIDC metadata and JWKS from it to validate signatures locally, with
    # caching. Cognito does not push keys, and there is no per-request lookup.
    rt_auth >> Edge(style="dashed", constraint="false") >> cognito
    gw_auth >> Edge(style="dashed", constraint="false") >> cognito
