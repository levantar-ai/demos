# Deployment artifacts — captured from a real run

Captured from the deploy and invoke cycle of this demo on 2026-10-04 (region
`us-east-1`, account `134570442530`), policy engine in `ENFORCE`. Demo 05 was
destroyed earlier the same day (63 resources, state empty, three
service-created log groups deleted by hand) before this stack went up.

## What was deployed

Everything from demo 05, namespaced `demos-agentcore-06-model-in-the-loop-*`
and `demos_agentcore_06_*`, plus the model. `terraform apply` with image
`1adae91` was 61 added, first time, no IAM race on this run. The runtime was
then replaced once to correct its name from `demos_agentcore_06_identity`
(a slip in the copy forward) to `demos_agentcore_06_model_in_the_loop`.

- Model `us.anthropic.claude-sonnet-4-5-20250929-v1:0`, the cross-region
  inference profile, which `get-inference-profile` reports routes to the
  foundation model in `us-east-1`, `us-east-2` and `us-west-2`. The runtime
  role is allowed `InvokeModel` and `InvokeModelWithResponseStream` on the
  profile ARN, and on those three foundation-model ARNs with a
  `bedrock:InferenceProfileArn` condition naming the profile.
- Customer pool `us-east-1_v7MGuvchz`, customers client
  `6ie3t9a4ke46hmun49bcoc0drf`, customers `c-1000` and `c-1001` created by
  hand with permanent passwords held outside the repository.
- Exchange pool `us-east-1_OVJf34beI`, orders client `48jqmtdirctqktnp7373ln9ems`,
  front door `https://1iwena4g3a.execute-api.us-east-1.amazonaws.com`,
  workload identity `demos_agentcore_06_agent`, credential provider
  `demos_agentcore_06_obo`. Unchanged from demo 05 in design.
- Memory `demos_agentcore_06_memory-vpxsF05lWU` with the `USER_PREFERENCE`
  strategy on `/users/{actorId}`; the runtime role gained `GetEvent`.
- Code Interpreter `demos_agentcore_06_interpreter-48bd8FeiBQ`, `SANDBOX`
  network mode.

## The turns

<<LIVE_TURNS>>

## Memory

The seed turn in session `live-06-seed-session-…001` stored five events for
actor `c-1000`: the USER and ASSISTANT messages and three non-conversational
events the Strands session manager writes for session and agent state.

<<LIVE_MEMORY>>

## What the live run taught

<<LIVE_LESSONS>>

## External review (gpt-5.6-sol via the OpenAI API)

<<REVIEW>>
