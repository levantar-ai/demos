"""Print the claims that matter from a JWT, without verifying it.

For looking at the token AgentCore Identity minted, in the runbook and the
video. Verification is the gateway's job, not this script's.

Usage: python3 show_token.py <jwt>
"""

import base64
import json
import sys


def part(segment):
    return json.loads(base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4)))


header, payload = (part(s) for s in sys.argv[1].split(".")[:2])
print(f"alg      {header.get('alg')}   kid {header.get('kid')}")
for claim in ("iss", "aud", "username", "scope", "act"):
    if claim in payload:
        print(f"{claim:8} {payload[claim]}")
if "exp" in payload and "iat" in payload:
    print(f"lifetime {payload['exp'] - payload['iat']} seconds")
