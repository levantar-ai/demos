"""Generate the architecture diagram for post 03.

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
from diagrams.aws.ml import Bedrock
from diagrams.onprem.client import User
from diagrams.programming.language import Python

graph_attr = {
    "pad": "0.6",
    "nodesep": "0.9",
    "ranksep": "1.1",
    "fontsize": _fs(20),
    "fontcolor": "#0e1216",  # --ink
}

node_attr = {
    "fontsize": _fs(13),
}

edge_attr = {
    "fontsize": _fs(12),
    "fontcolor": "#4a5158",  # --ink-2
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
    caller = User("caller", height=_h(1))

    with Cluster(
        "AgentCore Runtime",
        graph_attr={"fontsize": _fs(15), "margin": cluster_margin(), "bgcolor": "#f6f3ec"},
    ):
        agent = Python("agent", height=_h(1))

    with Cluster(
        "AgentCore Memory",
        graph_attr={"fontsize": _fs(15), "margin": cluster_margin(), "bgcolor": "#efece4"},
    ):
        events = Bedrock("events\n(short-term)", height=_h(2))
        records = Bedrock("preference records\n(long-term)", height=_h(2))

    caller >> Edge(label="invoke") >> agent
    agent >> Edge(label="create_event") >> events
    events >> Edge(label="USER_PREFERENCE strategy\nextracts async", style="dashed") >> records
    records >> Edge(label="retrieve_memory_records", style="dashed", constraint="false") >> agent

# Env overrides used by scripts/render-social.py
