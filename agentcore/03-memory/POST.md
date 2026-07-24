# Giving your agent memory that survives the session

## TL;DR;

How to add AgentCore Memory to an agent so it keeps short-term
conversation events within a session and recalls extracted user
preferences across sessions, with the extraction happening asynchronously
on the service side.

SOURCE CODE - All code for this post is available at:
https://github.com/levantar-ai/demos/tree/main/agentcore/03-memory

## Longer version

The agent from the first post forgets everything the moment a session
ends, which is what most agents do by default and what makes them feel
like strangers every time. Session state on its own does not fix this,
because the useful things a user tells you (their name, their
preferences, how they like to be contacted) belong to the user, not to
the session they happened to say them in.

AgentCore Memory splits this into two layers. Events are raw conversation
turns you write per actor and session, they expire after a configurable
number of days and behave as short-term memory. Strategies watch those
events and asynchronously extract structured records into namespaces,
which is the long-term memory that survives across sessions. The service
ships built-in strategies including semantic facts, summaries, user
preferences and episodic memory, plus custom strategies where you control
the extraction, and this post uses the user-preference one.

![Architecture](architecture.png)

## 1 - The memory store

The memory side is two resources, the store itself with an expiry that
defines how long raw events live, and a strategy that tells the service
what to extract and where to put it:

```hcl
resource "aws_bedrockagentcore_memory" "agent" {
  name                  = "demos_agentcore_03_memory"
  event_expiry_duration = 7
}

resource "aws_bedrockagentcore_memory_strategy" "preferences" {
  memory_id  = aws_bedrockagentcore_memory.agent.id
  name       = "UserPreferences"
  type       = "USER_PREFERENCE"
  namespaces = ["/users/{actorId}"]
}
```

The namespace template is the interesting part. `{actorId}` is filled in
per actor at extraction time, so each user gets their own
`/users/<actor>` shelf of preference records and retrieval is naturally
scoped to one user.

NOTE: the memory store is the slowest resource in this series so far to
create, 2m45s in this deployment, so it is worth creating once and
keeping rather than treating as disposable per environment.

## 2 - The agent

The agent from post 01 gains a cached boto3 client and two functions,
which is also this agent's first dependency, because memory is a
data-plane API rather than something the runtime injects:

```python
def remember(actor, session, text):
    client().create_event(
        memoryId=os.environ["MEMORY_ID"],
        actorId=actor,
        sessionId=session,
        eventTimestamp=datetime.now(timezone.utc),
        payload=[{"conversational": {"content": {"text": text}, "role": "USER"}}],
    )


def recall(actor, query):
    resp = client().retrieve_memory_records(
        memoryId=os.environ["MEMORY_ID"],
        namespace=f"/users/{actor}",
        searchCriteria={"searchQuery": query},
        maxResults=5,
    )
    return [r["content"]["text"] for r in resp.get("memoryRecordSummaries", [])]
```

Prompts starting with "remember" are stored as events, anything else is
answered by semantic search over the extracted records. The runtime role
gets the memory data-plane actions (CreateEvent, ListEvents,
RetrieveMemoryRecords and friends) scoped to this one memory store, and
Terraform passes the memory id in as an environment variable.

## 3 - Teaching it something

The invoke command is the same `aws bedrock-agentcore invoke-agent-runtime`
call as post 01, so the examples below show just the payloads and
responses. Session A, actor `andy`:

```bash
--payload '{"actor": "andy", "session": "session-a",
            "prompt": "remember: my name is Andy and I always prefer DPD for deliveries"}'
{"result": "noted"}

--payload '{"actor": "andy", "session": "session-a",
            "prompt": "remember: I like order updates by email, never SMS"}'
{"result": "noted"}
```

The events land immediately and are the short-term layer, you can read
them straight back per session:

```bash
aws bedrock-agentcore list-events --memory-id "$MEMORY_ID" \
  --actor-id andy --session-id session-a --region us-east-1 \
  --query 'events[].payload[0].conversational.content.text'
[
    "remember: I like order updates by email, never SMS",
    "remember: my name is Andy and I always prefer DPD for deliveries"
]
```

## 4 - Asking from a different session

Ask straight away from a new session and you get an honest empty answer,
because extraction is asynchronous and has not run yet:

```bash
--payload '{"actor": "andy", "session": "session-b",
            "prompt": "which delivery carrier do I prefer?"}'
{"result": []}
```

Ask again a few minutes later and the strategy has done its work:

```bash
--payload '{"actor": "andy", "session": "session-b",
            "prompt": "what do you know about my preferences?"}'
{"result": [
  "{\"context\":\"The user explicitly stated that they are a vegetarian.\",
    \"preference\":\"Is a vegetarian\",\"categories\":[\"food\",\"diet\"]}",
  "{\"context\":\"The user explicitly stated that their favourite cuisine is Thai.\",
    \"preference\":\"Favourite cuisine is Thai\",\"categories\":[\"food\",\"cuisine\"]}"
]}
```

The service turned a raw "remember:" sentence into a structured record
with the preference, the context it was stated in and categories, without
any extraction code on our side. In this deployment the records appeared
around five minutes after the event.

NOTE: events stored in the first moments after the strategy is created
can miss extraction, in this deployment two events stored straight after
the apply never produced records, while an event stored once the strategy
showed ACTIVE was extracted normally. Store after
`get-memory` reports the strategy ACTIVE.

That answer came from a different session to the one the preferences were
stored in, which is the whole point. The extracted records are attached
to the actor, not the session, so any future session for `andy` can
retrieve them.

## Conclusion

Memory in AgentCore is two deliberate layers rather than one magic box.
Events give you cheap, immediate, per-session recall with an expiry date,
and strategies turn those events into durable records per user without
you running any extraction pipeline yourself. The trade to design around
is the asynchronous gap between storing and recalling, an agent that
needs to use a fact in the same breath it learned it should read its own
session events, and lean on the extracted records for everything that
comes later.

The next post gives the agent the built-in tools, Code Interpreter and
Browser, and looks at the security model of letting an agent execute
code.

References:

- https://github.com/levantar-ai/demos/tree/main/agentcore/03-memory
- https://docs.aws.amazon.com/bedrock-agentcore/
- https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/bedrockagentcore_memory
