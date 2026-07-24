# Deployment artifacts — captured from a real run

Captured from an actual deploy → invoke → destroy cycle of this demo on
2026-07-24 (region `us-east-1`). Raw material for the post.

## Deploy

7 resources. The memory store was the slow one at 2m45s; the strategy
attached in 1s and the runtime created in 13s.

## Short-term (events)

Two "remember:" prompts stored via the agent in session A returned
`{"result": "noted"}` and were immediately readable back with
`list-events --query 'events[].payload[0].conversational.content.text'`.

## Long-term (extracted records)

- Recall from session B immediately after storing returned `{"result": []}`
  because extraction is asynchronous.
- Two events stored straight after the apply (while the strategy had just
  been created) never produced records.
- A third event stored once `get-memory` showed the strategy ACTIVE was
  extracted normally; records appeared roughly five minutes after the
  event:

```json
["{\"context\":\"The user explicitly stated that they are a vegetarian.\",\"preference\":\"Is a vegetarian\",\"categories\":[\"food\",\"diet\"]}",
 "{\"context\":\"The user explicitly stated that their favourite cuisine is Thai.\",\"preference\":\"Favourite cuisine is Thai\",\"categories\":[\"food\",\"cuisine\"]}"]
```

- The recall came from a different session (session B) to the one the
  preference was stored in (session A), demonstrating actor-scoped
  long-term memory via the `/users/{actorId}` namespace.

## Teardown

`terraform destroy`: 7/7 destroyed; `list-agent-runtimes` and
`list-memories` both empty afterwards.

## Internal review

An adversarial three-lens review (AWS facts, code/prose consistency,
voice) confirmed six findings before external review, all fixed: missing
`--query` on the list-events example, non-exhaustive strategy list
(episodic exists), function count, elided invoke commands noted, and a
banned sentence fragment (also present in post 02, fixed there too).
