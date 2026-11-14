"""The post 05 architecture redrawn on Cognito's own token exchange.

Run from this directory: python3 diagram.py
Produces after.png. The before is agentcore/05-identity/architecture.png.
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

# Post 05's front door, exchange pool and four triggers are gone. AgentCore
# Identity's on-behalf-of provider points at the customer pool, which mints
# the token itself. run.py exercised AgentCore Identity and Cognito in both
# modes, calling Identity directly rather than from a deployed agent, so the
# runtime and gateway clusters are dashed and the orders Lambda says so.

with Diagram(
    "The same agent on Cognito's own token exchange. The dashed boxes were not part of the live test",
    filename=os.environ.get("DIAGRAM_OUT", "after"),
    outformat="png",
    show=False,
    direction="LR",
    graph_attr=graph_attr,
    node_attr=node_attr,
    edge_attr=edge_attr,
):
    customer = User("customer\n(Bearer JWT)", height=_h(2))
    sign_in = Cognito("customer pool", height=_h(1))

    with Cluster(
        "AgentCore Runtime (the test called AgentCore Identity directly)",
        graph_attr={"fontsize": _fs(15), "margin": cluster_margin(), "bgcolor": "#f6f3ec", "style": "dashed"},
    ):
        rt_auth = Bedrock("AgentCore Identity\ninbound auth\n(CUSTOM_JWT)", height=_h(3))
        agent = Python("agent", height=_h(1))

    with Cluster(
        "AgentCore Identity, on behalf of the customer",
        graph_attr={"fontsize": _fs(15), "margin": cluster_margin(), "bgcolor": "#eef3f1"},
    ):
        identity = Bedrock("workload identity,\nOBO credential provider,\nToken Vault", height=_h(3))

    cognito = Cognito("the same customer pool,\ntoken endpoint,\nCognito mints", height=_h(3))

    with Cluster(
        "AgentCore Gateway, trusts the customer pool, Cedar per call (not yet run)",
        graph_attr={"fontsize": _fs(15), "margin": cluster_margin(), "bgcolor": "#efece4", "style": "dashed"},
    ):
        gw_auth = Bedrock("JWT authorizer,\naud = orders", height=_h(2))
        gateway = APIGateway("gateway", height=_h(1))
        policy = IdentityAndAccessManagementIamPermissions("Cedar policy\nusername ==\ncustomer_id argument", height=_h(3))

    orders = Lambda("orders\n(not yet run)", height=_h(2))

    customer >> Edge(label="sign in", style="dashed") >> sign_in
    customer >> Edge(label="invoke\n(Bearer JWT)") >> rt_auth
    rt_auth >> Edge(label="validated") >> agent

    agent >> Edge(label="a token for the order service") >> identity
    identity >> Edge(label="RFC 8693 exchange\n(subject = the customer's token,\nactor = the agent's client)") >> cognito

    agent >> Edge(label="list_orders\n(the exchanged token,\naud = orders, act = the agent)") >> gw_auth
    gw_auth >> Edge(label="validated") >> gateway
    gateway >> Edge(label="evaluate", style="dashed") >> policy
    gateway >> Edge(label="matching customer:\npermit the call") >> orders
