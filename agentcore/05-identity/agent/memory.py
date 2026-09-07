"""Short-term events and long-term preference recall with AgentCore Memory.

Carried forward from post 03 so this demo stands alone. Post 04 is about
the code sandbox, so none of this is discussed there.
"""

import os
from datetime import datetime, timezone

import boto3

_client = None


def client():
    global _client
    if _client is None:
        _client = boto3.client("bedrock-agentcore")
    return _client


def remember(actor, session, text):
    client().create_event(
        memoryId=os.environ["MEMORY_ID"],
        actorId=actor,
        sessionId=session,
        eventTimestamp=datetime.now(timezone.utc),
        payload=[{"conversational": {"content": {"text": text}, "role": "USER"}}],
    )


def recap(actor, session):
    resp = client().list_events(
        memoryId=os.environ["MEMORY_ID"],
        actorId=actor,
        sessionId=session,
        maxResults=20,
    )
    return [
        p["conversational"]["content"]["text"]
        for e in resp.get("events", [])
        for p in e.get("payload", [])
        if "conversational" in p
    ]


def recall(actor, query):
    resp = client().retrieve_memory_records(
        memoryId=os.environ["MEMORY_ID"],
        namespace=f"/users/{actor}",
        searchCriteria={"searchQuery": query},
        maxResults=5,
    )
    return [r["content"]["text"] for r in resp.get("memoryRecordSummaries", [])]
