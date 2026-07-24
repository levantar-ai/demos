"""Generate the architecture diagram for post 02.

Run from this directory: python3 diagram.py
Produces architecture.png referenced by POST.md.
"""

from diagrams import Cluster, Diagram, Edge
from diagrams.aws.compute import Lambda
from diagrams.aws.network import APIGateway
from diagrams.aws.security import Cognito
from diagrams.onprem.client import User
from diagrams.programming.language import Python

graph_attr = {
    "pad": "0.6",
    "nodesep": "0.9",
    "ranksep": "1.1",
    "fontsize": "20",
    "fontcolor": "#333333",
}

node_attr = {
    "fontsize": "13",
}

edge_attr = {
    "fontsize": "12",
    "fontcolor": "#555555",
}

with Diagram(
    "An agent calling tools through AgentCore Gateway",
    filename="architecture",
    outformat="png",
    show=False,
    direction="LR",
    graph_attr=graph_attr,
    node_attr=node_attr,
    edge_attr=edge_attr,
):
    caller = User("caller")
    cognito = Cognito("Cognito\n(client credentials)")

    with Cluster(
        "AgentCore Runtime",
        graph_attr={"fontsize": "15", "margin": "25", "bgcolor": "#f3f7fa"},
    ):
        agent = Python("agent")

    with Cluster(
        "AgentCore Gateway (MCP)",
        graph_attr={"fontsize": "15", "margin": "25", "bgcolor": "#f7f4fa"},
    ):
        gateway = APIGateway("orders target")

    tool = Lambda("lookup_order")

    caller >> Edge(label="invoke") >> agent
    cognito >> Edge(label="JWT", style="dashed") >> agent
    agent >> Edge(label="tools/call") >> gateway
    gateway >> Edge(label="invoke") >> tool
