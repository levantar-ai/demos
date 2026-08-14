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

## External review (gpt-5.6-sol via OpenAI API) and second cycle

Nine findings, all accepted. Key changes: agent gained short-term recall
("recap" via ListEvents), session validation, generic 502s (exception
detail logged server-side only), IAM trimmed to the three actions used,
actor-id-authorization NOTE, and the post's evidence redone so the shown
events match the retrieved records.

Second deploy verified the fixes and reproduced the activation-window
behaviour decisively: events stored seconds after the strategy reported
ACTIVE were never extracted (60+ minutes), while the same event stored
once the strategy had settled extracted in 52 seconds. Before/after
outputs for the same query captured for the post. All resources
destroyed after; runtimes and memories confirmed empty.

## Pre-publication re-review (gpt-5.6-sol via OpenAI API), 2026-08-14

POST.md had moved on in five commits since the review above, two of them
substantive (the least-privilege memory statement and the AWS
shared-responsibility citation), so the post went back through the gate
before being published to levantar.ai.

Seven findings, no blockers. Five actioned:

- Section 2 claimed "anything else returns the matching extracted
  preference records", which skipped the order-number route to the post 02
  gateway tool that this agent still carries. Prose now names both routes
  and the twenty-event ceiling on `recap`.
- The activation-window NOTE asserted events were "never extracted". The
  artifacts only support "no records an hour later", so the claim is now
  bounded, scoped to `us-east-1`, and labelled an observation rather than
  service behaviour to design against.
- The actor-id NOTE inferred too much from a citation about
  session-to-user mapping, and suggested deriving an actor from the
  caller's IAM principal, which the workload does not automatically
  receive. It now separates store-level IAM from application-enforced
  actor mapping.
- The broad handler reported every failure as a memory failure, including
  failures from the gateway route it also wraps. Message and log line are
  now neutral.
- "takes minutes rather than seconds" softened to "can take several
  minutes"; the unsupported "cheap" dropped from the conclusion.

Two declined. The `SOURCE CODE ... available at:` callout and the
`References:` heading were flagged as house-style colon violations, but
they are series-wide conventions shared with posts 01, 02 and 04, so
changing them here alone would break the series.

Re-review confirmed all five resolved and caught one leftover absolute
("they just never became records") contradicting the bounded claim four
lines above it, now fixed. Verdict: ready to publish.

No redeploy. The two code changes are an error-string and a comment, so
the deploy evidence recorded above still holds. Agent tests pass (8/8).

## Wiring diagram and video caption (gpt-5.6-sol), 2026-08-14

A reader asked whether `remember`, `recap` and `recall` were AWS vocabulary,
and then how the prompt reached them. Both are answered in the post now
rather than only in the code.

Added a caption under the video saying the walkthrough starts after
`terraform apply`, since it does and three of the four demos show the apply
on camera. The claim it carries, seven resources with the memory store slow
at close to three minutes, comes from the deploy recorded at the top of this
file.

Added `routing.py`, which draws the path from a prompt to an AWS API call in
the house diagram style, and a paragraph naming the three operations the
function names wrap.

Four findings, all actioned. "Four string tests" was wrong twice over, since
there are two `startswith` calls, a regex and a fallback, and the regex is
evaluated before the chain even though the prefixes take precedence. "The
test is on the word rather than the colon" overstated it, because
`startswith` is a character test that also matches "remembered". The
diagram's standfirst called the fallback a test. And the new prose carried a
colon inside "remember:", against house style.

Re-review confirmed all four resolved with nothing introduced. No redeploy,
no re-record. Prose and a new diagram only.
