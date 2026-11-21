"""Generate the architecture diagram for post 08.

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
from diagrams.aws.management import Cloudwatch
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

# Post 07's agent, unchanged in what it does. The SDK's app now serves the
# runtime's contract and calls the agent's one function; ADOT wraps the app,
# so the turn is inside the runtime's trace before that function runs.

with Diagram(
    "The agent of post 07 on the SDK's server, one function behind the runtime's contract",
    filename=os.environ.get("DIAGRAM_OUT", "architecture"),
    outformat="png",
    show=False,
    direction="LR",
    graph_attr=graph_attr,
    node_attr=node_attr,
    edge_attr=edge_attr,
):
    customer = User("customer\n(Bearer JWT)", height=_h(2))
    runtime = Bedrock("AgentCore Runtime\nchecks the JWT, starts the trace", height=_h(2))

    with Cluster(
        "the agent's container, started under ADOT",
        graph_attr={"fontsize": _fs(15), "margin": cluster_margin(), "bgcolor": "#f6f3ec"},
    ):
        app = Python("BedrockAgentCoreApp\nthe SDK's server\n/invocations, /ping", height=_h(3))
        fn = Python("invoke(payload, context)\nthe agent's own code", height=_h(2))

    with Cluster(
        "what the agent calls",
        graph_attr={"fontsize": _fs(15), "margin": cluster_margin(), "bgcolor": "#eef3f1"},
    ):
        model = Bedrock("Claude Sonnet 4.5", height=_h(1))
        gateway = APIGateway("AgentCore Gateway\nCedar, orders Lambda", height=_h(2))
        memory = Bedrock("AgentCore Memory", height=_h(1))

    traces = Cloudwatch("CloudWatch\none trace per turn", height=_h(2))

    customer >> Edge(label="invoke") >> runtime
    runtime >> Edge(label="POST /invocations\nsession id, trace context") >> app
    app >> Edge(label="payload, context") >> fn
    fn >> Edge(label="chat", tailport="e") >> model
    fn >> Edge(label="tools/call", tailport="e") >> gateway
    fn >> Edge(label="events", tailport="e") >> memory
    app >> Edge(label="spans", style="dashed", tailport="s") >> traces
