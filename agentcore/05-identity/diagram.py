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
from diagrams.aws.network import APIGateway
from diagrams.aws.security import Cognito, IdentityAndAccessManagementIamPermissions
from diagrams.onprem.client import User
from diagrams.programming.language import Python

graph_attr = {
    "pad": "0.6",
    "nodesep": "0.9",
    "ranksep": "1.2",
    "fontsize": _fs(20),
    "fontcolor": "#0e1216",
}
node_attr = {"fontsize": _fs(13)}
edge_attr = {"fontsize": _fs(12), "fontcolor": "#4a5158"}

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
        "AgentCore Runtime  -  validates the customer's JWT",
        graph_attr={"fontsize": _fs(15), "margin": cluster_margin(), "bgcolor": "#f6f3ec"},
    ):
        agent = Python("agent", height=_h(1))

    with Cluster(
        "AgentCore Gateway  -  Policy in AgentCore evaluates Cedar per call",
        graph_attr={"fontsize": _fs(15), "margin": cluster_margin(), "bgcolor": "#efece4"},
    ):
        gateway = APIGateway("gateway", height=_h(1))
        policy = IdentityAndAccessManagementIamPermissions(
            "Cedar policy\ncustomer_id == caller", height=_h(2)
        )

    orders = Lambda("orders", height=_h(1))

    customer >> Edge(label="sign in", style="dashed") >> cognito
    customer >> Edge(label="invoke\n(Bearer JWT)") >> agent
    agent >> Edge(label="list_orders\n(customer's JWT)") >> gateway
    gateway >> Edge(label="validates JWT", style="dashed", constraint="false") >> cognito
    gateway >> Edge(label="evaluate", style="dashed") >> policy
    gateway >> Edge(label="permit:\ncaller's own orders") >> orders
