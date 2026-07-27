"""Generate the architecture diagram for post 03.

Run from this directory: python3 diagram.py
Produces architecture.png referenced by POST.md.
"""

import os

from diagrams import Cluster, Diagram, Edge
from diagrams.aws.ml import Bedrock
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
    "An agent that remembers, with AgentCore Memory",
    filename=os.environ.get("DIAGRAM_OUT", "architecture"),
    outformat="png",
    show=False,
    direction="LR",
    graph_attr=graph_attr,
    node_attr=node_attr,
    edge_attr=edge_attr,
):
    caller = User("caller")

    with Cluster(
        "AgentCore Runtime",
        graph_attr={"fontsize": _fs(15), "margin": "25", "bgcolor": "#f3f7fa"},
    ):
        agent = Python("agent")

    with Cluster(
        "AgentCore Memory",
        graph_attr={"fontsize": _fs(15), "margin": "25", "bgcolor": "#f7f4fa"},
    ):
        events = Bedrock("events\n(short-term)")
        records = Bedrock("preference records\n(long-term)")

    caller >> Edge(label="invoke") >> agent
    agent >> Edge(label="create_event") >> events
    events >> Edge(label="USER_PREFERENCE strategy\nextracts async", style="dashed") >> records
    records >> Edge(label="retrieve_memory_records", style="dashed", constraint="false") >> agent

# Env overrides used by scripts/render-social.py
