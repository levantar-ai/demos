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

with Diagram(
    "First agent on AgentCore Runtime",
    filename="architecture",
    outformat="png",
    show=False,
    direction="LR",
):
    caller = User("caller\n(invoke-agent-runtime)")

    with Cluster("AWS us-east-1"):
        ecr = ECR("ECR\ndemos/agentcore/01-first-agent")
        role = IAMRole("execution role")
        logs = CloudwatchLogs("CloudWatch\nruntime logs")

        with Cluster("AgentCore Runtime"):
            with Cluster("microVM per session"):
                agent = Python("agent container\n:8080 /invocations /ping")

    caller >> Edge(label="POST /invocations") >> agent
    ecr >> Edge(label="image pulled at start", style="dashed") >> agent
    agent >> Edge(label="assumes", style="dashed") >> role
    agent >> Edge(label="stdout") >> logs
