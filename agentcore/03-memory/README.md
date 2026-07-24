# 03 — Short-term and long-term memory with AgentCore Memory

Extends the first agent with AgentCore Memory: conversation turns are
stored as events (short-term, per session), and a `USER_PREFERENCE`
strategy asynchronously extracts preference records (long-term) that the
agent retrieves across sessions from the `/users/{actorId}` namespace.

## What gets created

- Everything from demo 01 (ECR repo, runtime execution role, runtime),
  namespaced `demos-agentcore-03-memory-*`
- AgentCore Memory `demos_agentcore_03_memory` (7-day event expiry)
- Memory strategy `UserPreferences` (`USER_PREFERENCE`, namespace
  `/users/{actorId}`)
- Runtime role additionally allows the memory data-plane calls
  (CreateEvent, ListEvents, RetrieveMemoryRecords, ...) on this memory only

## Run it

```bash
make demo-init demo-apply DEMO=agentcore/03-memory
```

Tell it something, then ask from a different session:

```bash
ARN=$(cd terraform && terraform output -raw runtime_arn)

aws-vault exec lev:andy.rea -- aws bedrock-agentcore invoke-agent-runtime \
  --cli-binary-format raw-in-base64-out --agent-runtime-arn "$ARN" \
  --runtime-session-id "any-session-id-of-33-chars-or-more-00a" \
  --payload '{"actor": "andy", "session": "session-a", "prompt": "remember: I always prefer DPD"}' \
  --region us-east-1 /dev/stdout

# extraction is asynchronous; give it a minute or two, then:
aws-vault exec lev:andy.rea -- aws bedrock-agentcore invoke-agent-runtime \
  --cli-binary-format raw-in-base64-out --agent-runtime-arn "$ARN" \
  --runtime-session-id "any-session-id-of-33-chars-or-more-00b" \
  --payload '{"actor": "andy", "session": "session-b", "prompt": "which carrier do I prefer?"}' \
  --region us-east-1 /dev/stdout
```

## Tear down

```bash
make demo-destroy DEMO=agentcore/03-memory
```
