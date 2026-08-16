"""Generate the architecture diagram for post 04.

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
    "Untrusted analysis in an AgentCore sandbox",
    filename=os.environ.get("DIAGRAM_OUT", "architecture"),
    outformat="png",
    show=False,
    direction="LR",
    graph_attr=graph_attr,
    node_attr=node_attr,
    edge_attr=edge_attr,
):
    caller = User("caller\n(CSV)", height=_h(2))

    with Cluster(
        "AgentCore Runtime",
        graph_attr={"fontsize": _fs(15), "margin": cluster_margin(), "bgcolor": "#f6f3ec"},
    ):
        agent = Python("agent", height=_h(1))

    with Cluster(
        "Code Interpreter  -  SANDBOX: no network, no credentials",
        graph_attr={"fontsize": _fs(15), "margin": cluster_margin(), "bgcolor": "#efece4"},
    ):
        sandbox = Bedrock("pandas session", height=_h(1))

    caller >> Edge(label="invoke") >> agent
    agent >> Edge(label="results", dir="back") >> sandbox
    sandbox >> Edge(label="writeFiles,\nexecuteCode", style="dashed", dir="back") >> agent
