"""Generate the architecture diagram for post 07.

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
from diagrams.aws.devtools import XRay
from diagrams.aws.management import Cloudwatch, CloudwatchLogs
from diagrams.aws.ml import Bedrock
from diagrams.aws.network import APIGateway
from diagrams.onprem.client import User
from diagrams.programming.language import Python

graph_attr = {
    "pad": "0.6",
    "nodesep": "0.9",
    "ranksep": "1.3",
    "fontsize": _fs(20),
    "fontcolor": "#0e1216",
    "labelloc": "t",
    # Curved edges, so a connector passes beside a label rather than
    # through it on the way into the node.
    "splines": "spline",
}
node_attr = {"fontsize": _fs(13)}
edge_attr = {"fontsize": _fs(12), "fontcolor": "#4a5158"}

# The agent of post 06, unchanged, now started under ADOT. Its spans and the
# content they record go to the runtime's own log group; the gateway's and
# the memory's spans go through X-Ray, which Transaction Search writes to
# aws/spans; their application logs go to log groups of the demo's. All of
# it carries the trace id the runtime started, so CloudWatch shows one turn
# as one trace.

with Diagram(
    "The agent of post 06, traced: one turn is one trace across the runtime, the gateway and the memory",
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
        agent = Python("agent of post 06\nunder ADOT,\nin the runtime's trace", height=_h(3))
        model = Bedrock("Claude Sonnet 4.5", height=_h(1))

    with Cluster(
        "what the agent calls",
        graph_attr={"fontsize": _fs(15), "margin": cluster_margin(), "bgcolor": "#eef3f1"},
    ):
        gateway = APIGateway("AgentCore Gateway\nCedar, orders Lambda", height=_h(2))
        memory = Bedrock("AgentCore Memory", height=_h(1))

    with Cluster(
        "CloudWatch",
        graph_attr={"fontsize": _fs(15), "margin": cluster_margin(), "bgcolor": "#f6f3ec"},
    ):
        runtime_logs = CloudwatchLogs("runtime log group\nspans, prompts, replies\ndemo key, 7 days", height=_h(3))
        xray = XRay("X-Ray to aws/spans\n(Transaction Search)", height=_h(2))
        vended = CloudwatchLogs("gateway and memory\napplication logs\ndemo key, 7 days", height=_h(3))
        console = Cloudwatch("GenAI Observability\nand Logs Insights", height=_h(2))

    customer >> Edge(label="invoke, trace started") >> agent
    agent >> Edge(label="chat") >> model
    agent >> Edge(label="tools/call\ntrace context", tailport="s") >> gateway
    agent >> Edge(label="events\ntrace context", tailport="s") >> memory

    agent >> Edge(label="spans and content", style="dashed", tailport="s") >> runtime_logs
    # Into the side of a node, so no arrow crosses the label under its icon.
    gateway >> Edge(label="spans", style="dashed", headport="w") >> xray
    memory >> Edge(label="spans", style="dashed", headport="w") >> xray
    gateway >> Edge(label="logs", style="dashed") >> vended
    memory >> Edge(style="dashed") >> vended
    runtime_logs >> Edge(label="one trace id", headport="w") >> console
    xray >> Edge(tailport="e", headport="w") >> console
