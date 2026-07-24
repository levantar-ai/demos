"""Generate the architecture diagram for post 01.

Run from this directory: python3 diagram.py
Produces architecture.png referenced by POST.md.
"""

from diagrams import Cluster, Diagram, Edge
from diagrams.aws.compute import ECR
from diagrams.aws.management import CloudwatchLogs
from diagrams.aws.security import IAMRole
from diagrams.onprem.client import User
from diagrams.programming.language import Python

graph_attr = {
    "pad": "0.75",
    "nodesep": "1.0",
    "ranksep": "1.4",
    "splines": "ortho",
    "fontsize": "22",
}

node_attr = {
    "fontsize": "14",
    "height": "1.6",
}

edge_attr = {
    "fontsize": "13",
}

cluster_attr = {
    "fontsize": "16",
    "margin": "30",
}

with Diagram(
    "First agent on AgentCore Runtime",
    filename="architecture",
    outformat="png",
    show=False,
    direction="LR",
    graph_attr=graph_attr,
    node_attr=node_attr,
    edge_attr=edge_attr,
):
    caller = User("caller")

    with Cluster("AWS us-east-1", graph_attr=cluster_attr):
        ecr = ECR("ECR image\n(git SHA tag)")
        role = IAMRole("execution\nrole")
        logs = CloudwatchLogs("runtime\nlogs")

        with Cluster("AgentCore Runtime", graph_attr=cluster_attr):
            with Cluster("microVM per session", graph_attr=cluster_attr):
                agent = Python("echo agent\nport 8080")

    caller >> Edge(label="invoke") >> agent
    ecr >> Edge(label="pull", style="dashed") >> agent
    agent >> Edge(label="assume", style="dashed") >> role
    agent >> Edge(label="stdout") >> logs
