"""Generate the architecture diagram for post 06.

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
from diagrams.aws.security import IdentityAndAccessManagementIamPermissions
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

# The prompt goes to a model. Trusted code in the agent still establishes who
# the customer is and gets the token for the order service from AgentCore
# Identity on their behalf (post 05's chain, unchanged and not redrawn here),
# and builds the tools with it. The model chooses which tools to call and
# with what arguments; Cedar at the gateway refuses a customer_id that is
# not the token's.

with Diagram(
    "A model handed the tools the series built, choosing what to call; identity stays in trusted code",
    filename=os.environ.get("DIAGRAM_OUT", "architecture"),
    outformat="png",
    show=False,
    direction="LR",
    graph_attr=graph_attr,
    node_attr=node_attr,
    edge_attr=edge_attr,
):
    customer = User("customer\n(Bearer JWT)", height=_h(2))

    with Cluster(
        "AgentCore Runtime",
        graph_attr={"fontsize": _fs(15), "margin": cluster_margin(), "bgcolor": "#f6f3ec"},
    ):
        rt_auth = Bedrock("inbound auth\n(CUSTOM_JWT)", height=_h(2))
        # The identity chain of post 05 is unchanged and drawn there; here it
        # is a line in the agent's label so the layout stays one pipeline.
        agent = Python(
            "agent, trusted code\ncustomer from the verified token,\ngateway token minted on their behalf\nby AgentCore Identity (post 05)",
            height=_h(4),
        )
        model = Bedrock("Claude Sonnet 4.5\nchooses tools and arguments", height=_h(2))

    with Cluster(
        "the tools the model may choose",
        graph_attr={"fontsize": _fs(15), "margin": cluster_margin(), "bgcolor": "#eef3f1"},
    ):
        gateway = APIGateway("AgentCore Gateway\n(MCP) orders___list_orders", height=_h(2))
        policy = IdentityAndAccessManagementIamPermissions(
            "Cedar policy\ncustomer_id ==\ntoken customer_id", height=_h(3)
        )
        sandbox = Bedrock("Code Interpreter\nrun_python, SANDBOX", height=_h(2))
        memory = Bedrock("AgentCore Memory\nevery turn stored,\npreferences recalled", height=_h(3))

    orders = Lambda("orders", height=_h(1))

    customer >> Edge(label="invoke\n(Bearer JWT)") >> rt_auth
    rt_auth >> Edge(label="validated") >> agent
    agent >> Edge(label="prompt + system prompt\nnaming the customer") >> model

    model >> Edge(label="list_orders(customer_id)\nthe minted token in the header") >> gateway
    gateway >> Edge(label="evaluate", style="dashed") >> policy
    gateway >> Edge(label="matching customer_id:\npermit") >> orders
    model >> Edge(label="run_python(code)\nthe pandas it wrote") >> sandbox
    model >> Edge(label="turns in,\npreferences out", style="dashed") >> memory
