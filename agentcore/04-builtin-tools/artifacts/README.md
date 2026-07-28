# Deployment artifacts — captured from a real run

Captured from deploy → invoke → destroy cycles of this demo on
2026-07-28 (region `us-east-1`).

## Deploy

5 resources; the code interpreter creates in about 1s, the runtime in
12-13s.

## Analysis through the sandbox

A five-row orders CSV posted to the agent returned pandas `describe()`
output computed inside the sandbox (3.6s cold, 6.4s including the first
session start):

```
order_id     items       total
count     5.000000  5.000000    5.000000
mean   1003.000000  3.600000   60.570000
...
rows: 5
```

## Sandbox isolation (probed directly)

With `network_mode = "SANDBOX"`:

- outbound internet: `URLError <urlopen error [Errno -2] Name or service
  not known>` — no DNS at all
- AWS-ish environment variables inside the sandbox: `[]`
- instance metadata endpoint (169.254.169.254): request denied,
  `HTTP 401` (measured; a denial, not proof the address is unreachable)

## Gotchas

- Files written with `writeFiles` land in the session's working
  directory, not `/tmp`; reading `/tmp/data.csv` raises FileNotFoundError.
- Sessions outlive the invocation. A sandbox with live sessions fails to
  delete with `ConflictException: ... There are 2 active sessions`; stop
  them explicitly.

## Teardown

All resources destroyed; `list-code-interpreters` and
`list-agent-runtimes` both empty afterwards.

## External review (gpt-5.6) and second cycle

Six findings, all actioned: sessions were never stopped (leak, and it
contradicted the post's own NOTE) — now stopped in a `finally` with a
test; every tool stream consumed with `isError` raised; Content-Length
validated and the body capped at 2MB; the post reframed as trusted code
processing untrusted data rather than untrusted code execution; probe
conclusions softened to what they actually prove; `network_mode`
described as the egress control rather than the whole boundary.

Verified after the fixes: analysis still correct, and
`list-code-interpreter-sessions` returns 0 active sessions immediately
after an invocation. The metadata probe returns HTTP 401 (measured).
