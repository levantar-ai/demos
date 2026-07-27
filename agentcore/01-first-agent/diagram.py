"""Generate the architecture diagram for post 01.

Run from this directory: python3 diagram.py
Produces architecture.png referenced by POST.md.
"""

import os

from diagrams import Cluster, Diagram, Edge
from diagrams.aws.compute import ECR
from diagrams.aws.management import CloudwatchLogs
from diagrams.aws.security import IAMRole
from diagrams.onprem.client import User
from diagrams.programming.language import Python

_BOOST = int(os.environ.get("DIAGRAM_FONT_BOOST", "0"))


def _fs(v):
    return str(int(v) + _BOOST)

graph_attr = {
    "pad": "0.6",
    "nodesep": "0.9",
    "ranksep": "1.1",
    "fontsize": _fs(20),
    "fontcolor": "#333333",
}

node_attr = {
    "fontsize": _fs(13),
}

edge_attr = {
    "fontsize": _fs(12),
    "fontcolor": "#555555",
}

with Diagram(
    "First agent on AgentCore Runtime",
    filename=os.environ.get("DIAGRAM_OUT", "architecture"),
    outformat="png",
    show=False,
    direction="LR",
    graph_attr=graph_attr,
    node_attr=node_attr,
    edge_attr=edge_attr,
):
    caller = User("caller")
    ecr = ECR("ECR image\n(git SHA tag)")

    with Cluster(
        "AgentCore Runtime  -  one microVM per session",
        graph_attr={"fontsize": _fs(15), "margin": "25", "bgcolor": "#f3f7fa"},
    ):
        agent = Python("echo agent\nport 8080")

    logs = CloudwatchLogs("runtime logs")
    role = IAMRole("execution role")

    caller >> Edge(label="invoke") >> agent
    ecr >> Edge(label="pull", style="dashed") >> agent
    agent >> Edge(label="stdout") >> logs
    agent >> Edge(label="assume", style="dashed") >> role

# Env overrides used by scripts/render-social.py
