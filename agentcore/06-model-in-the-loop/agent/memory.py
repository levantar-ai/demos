"""Memory from post 03, now kept by the agent framework rather than by routes.

Post 03 stored and recalled on command, "remember" and "recap" were routes in
the handler. From this post the AgentCore Memory session manager records
every turn as an event in the customer's own session, the short-term memory,
and before the model sees a message it retrieves the customer's long-term
records, the USER_PREFERENCE strategy's extractions in /users/{actorId}, and
puts them in front of the message. The actor is always the verified customer,
never a value from the request body, so one customer's preferences cannot be
read into another's conversation.
"""

import os

import boto3
from bedrock_agentcore.memory.integrations.strands.config import (
    AgentCoreMemoryConfig,
    RetrievalConfig,
)
from bedrock_agentcore.memory.integrations.strands.session_manager import (
    AgentCoreMemorySessionManager,
)

# The namespace the strategy in memory.tf writes to, with the actor filled in
# by the session manager at retrieval time.
PREFERENCES = "/users/{actorId}"

# Seam for the tests: they substitute a recorder for the real manager.
make_manager = AgentCoreMemorySessionManager


def region():
    return os.environ.get("AWS_REGION") or boto3.Session().region_name


def config_for(customer, session):
    """The memory configuration for one customer's conversation."""
    return AgentCoreMemoryConfig(
        memory_id=os.environ["MEMORY_ID"],
        actor_id=customer,
        session_id=session,
        retrieval_config={PREFERENCES: RetrievalConfig(top_k=5, relevance_score=0.3)},
        filter_restored_tool_context=True,
    )


def session_manager(customer, session):
    return make_manager(config_for(customer, session), region_name=region())
