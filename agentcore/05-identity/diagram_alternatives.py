"""The two delegation alternatives post 05 names but does not build.

Run from this directory: python3 diagram_alternatives.py
Produces alt-saas.png and alt-aws.png referenced by POST.md.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "scripts"))

from diagram_sizing import cluster_margin
from diagram_sizing import fs as _fs
from diagram_sizing import node_height as _h
from diagrams import Cluster, Diagram, Edge
from diagrams.aws.database import Dynamodb
from diagrams.aws.ml import Bedrock
from diagrams.aws.security import IdentityAndAccessManagementIamRole
from diagrams.onprem.client import User
from diagrams.programming.language import Python
from diagrams.onprem.compute import Server

graph_attr = {"pad": "0.5", "nodesep": "0.8", "ranksep": "1.1", "fontsize": _fs(19), "fontcolor": "#0e1216"}
node_attr = {"fontsize": _fs(13)}
edge_attr = {"fontsize": _fs(12), "fontcolor": "#4a5158"}


def runtime_cluster():
    with Cluster(
        "AgentCore Runtime",
        graph_attr={"fontsize": _fs(14), "margin": cluster_margin(), "bgcolor": "#f6f3ec"},
    ):
        return Python("agent", height=_h(1))


# Alternative 1: a third-party SaaS, on-behalf-of token exchange.
with Diagram(
    "Alternative: a third-party SaaS, on-behalf-of token exchange",
    filename="alt-saas",
    outformat="png",
    show=False,
    direction="LR",
    graph_attr=graph_attr,
    node_attr=node_attr,
    edge_attr=edge_attr,
):
    customer = User("customer\n(Bearer JWT)", height=_h(2))
    agent = runtime_cluster()
    vault = Bedrock("AgentCore Identity\ntoken vault", height=_h(2))
    saas = Server("SaaS API\n(enforces the user)", height=_h(2))

    customer >> Edge(label="invoke") >> agent
    agent >> Edge(label="on-behalf-of\nexchange (RFC 8693)") >> vault
    vault >> Edge(label="user-scoped token") >> agent
    agent >> Edge(label="call with\nuser-scoped token") >> saas


# Alternative 2: a first-party AWS store, web-identity federation, IAM enforces.
with Diagram(
    "Alternative: a first-party AWS store, web-identity federation",
    filename="alt-aws",
    outformat="png",
    show=False,
    direction="LR",
    graph_attr=graph_attr,
    node_attr=node_attr,
    edge_attr=edge_attr,
):
    customer = User("customer\n(Cognito ID token)", height=_h(2))
    agent = runtime_cluster()
    sts = IdentityAndAccessManagementIamRole("STS AssumeRole\nWithWebIdentity", height=_h(2))
    ddb = Dynamodb("DynamoDB orders\n(IAM enforces rows)", height=_h(2))

    customer >> Edge(label="invoke (ID token)") >> agent
    # DynamoDB is the main rightward flow so the read edge lands on it; the
    # STS exchange is an upper branch that does not constrain the ranking.
    agent >> Edge(label="read (IAM-scoped)") >> ddb
    agent >> Edge(label="assume role with ID token,\ntrusts the Cognito OIDC provider", constraint="false") >> sts
    sts >> Edge(label="customer-scoped credentials", dir="back", constraint="false") >> agent
