"""Brightwell's order agent, post 08: the same agent on the SDK's server.

The runtime's HTTP contract (POST /invocations, GET /ping) is served by the
bedrock-agentcore SDK's BedrockAgentCoreApp, where posts 01 to 07 wrote it
by hand on the standard library. The runtime
validates the customer's bearer token and forwards it, as post 05, and the
agent still gets its token for the order service from AgentCore Identity on
the customer's behalf (identity.py). What changes is what happens to the
prompt. There is no routing code left in this file. Every prompt goes to a
Bedrock model (model.py) that has been handed the order gateway and the
sandbox as tools, with the memory supplied as context by the session
manager, and the model chooses what to call. The customer
the model acts for comes from the verified token; the token itself is
supplied to the gateway client by this code, so the model chooses arguments,
never credentials, and a wrong customer_id is refused by Cedar at the
gateway, as post 05 set up.

Post 08 changes nothing the agent does. The SDK's app is a Starlette
application, which ADOT instruments, so the trace the runtime started for
the request is joined before this file's code runs and post 07's traced()
is gone. What the SDK leaves to the application stays here: who the caller
is, what a valid request is, how many turns run at once, and what a client
is told when a turn fails.
"""

import base64
import json
import re
import threading
from contextlib import contextmanager

from bedrock_agentcore.runtime import BedrockAgentCoreApp
from identity import orders_token
from model import answer
from starlette.middleware import Middleware
from starlette.responses import JSONResponse
from trail import BudgetExceeded, describe

MAX_BODY_BYTES = 2 * 1024 * 1024
# A question for an order agent is a sentence or a paragraph. Anything
# larger is a cost rather than a question, and is refused before the model.
MAX_PROMPT_CHARS = 4_000

# The runtime sends its session id to the container on a header, which the
# SDK reads into the request context. It is
# the conversation's id for the memory; a caller may also name one in the
# body when invoking the agent outside the runtime. There is no default:
# two clients of one customer must not silently share a conversation. This
# is the application's own grammar for an id, with the runtime's minimum of
# 33 characters, so a conversation outside the runtime is named the way one
# inside it is. A session id is a locator within the actor's own namespace,
# never an authorisation boundary: the actor comes from the token, and any
# client holding that token may continue any of that actor's conversations
# it knows the id of.
SESSION_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{32,127}")

# How many turns one process serves at once. The SDK runs each turn on a
# worker thread and every turn calls the exchange, the memory, the gateway and the
# model, none of which the sandbox's own bound covers, so the process admits
# this many turns and tells the next to try again rather than queue it.
MAX_TURNS_IN_FLIGHT = 8
_turns_in_flight = threading.BoundedSemaphore(MAX_TURNS_IN_FLIGHT)

# The response is bounded as well as the request. The trail carries the
# model's code, up to 20,000 characters a call and eight calls a turn, so
# past this many serialised characters the response is cut in stages, each
# re-serialised and marked: code to a preview, printed output and errors to
# a preview, the answer itself, and last the trail dropped altogether.
MAX_RESPONSE_CHARS = 60_000
CODE_PREVIEW = 2_000
OUTPUT_PREVIEW = 500
RESULT_PREVIEW = 8_000
FIGURES_PREVIEW = 20

# Turns in one conversation run one at a time in this process. The server
# answers requests concurrently, and two turns restoring and appending to
# the same conversation at once would interleave its history, so a second
# request for the same actor and session waits for the first to finish. The
# runtime routes a session's requests to one microVM for its lifetime, which
# is what makes this lock the conversation's there; outside the runtime it
# is the process's only. An
# entry is counted in and out under the guard, so it exists exactly while
# a turn holds or waits for it, cannot be dropped from under a waiter, and
# the table holds one entry per conversation with a turn in flight.
_turns = {}
_turns_guard = threading.Lock()


@contextmanager
def one_turn(actor, session):
    """Hold the conversation's turn for the block."""
    key = (actor, session)
    with _turns_guard:
        entry = _turns.setdefault(key, [threading.Lock(), 0])
        entry[1] += 1
    try:
        with entry[0]:
            yield
    finally:
        with _turns_guard:
            entry[1] -= 1
            if entry[1] == 0:
                del _turns[key]


def claims_from(headers):
    """The bearer token's claims, or None when there is no usable token.

    The runtime has already checked the signature, issuer, expiry and client
    against the pool's discovery document before forwarding the header, so
    this decodes the payload and does not verify it again.
    """
    auth = headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    try:
        payload = auth[len("Bearer "):].split(".")[1]
        payload += "=" * (-len(payload) % 4)
        claims = json.loads(base64.urlsafe_b64decode(payload))
    except (IndexError, ValueError):
        return None
    return claims if isinstance(claims, dict) else None


def customer_from(headers):
    """The calling customer. Brightwell's customer ids are the pool's usernames.

    Only an access token carries the username claim this relies on, so the
    token type is checked rather than assumed from the authorizer settings.
    The username is what the orders service and Cedar know the customer by;
    it is not what memory is keyed by, since an administrator can delete a
    username and create it again for someone else.
    """
    claims = claims_from(headers) or {}
    if claims.get("token_use") != "access":
        return None
    username = claims.get("username")
    return username if isinstance(username, str) and username else None


def subject_from(headers):
    """The token's subject, the pool's immutable id for the user, which keys
    the memory and the turn lock."""
    claims = claims_from(headers) or {}
    if claims.get("token_use") != "access":
        return None
    subject = claims.get("sub")
    return subject if isinstance(subject, str) and subject else None


def bearer_from(headers):
    """The raw bearer token the runtime forwarded, the subject of the exchange."""
    auth = headers.get("Authorization", "")
    return auth[len("Bearer "):] if auth.startswith("Bearer ") else None


def session_from(runtime_session, payload):
    """The conversation id, the runtime's session or else the body's, or
    None when neither names a usable one."""
    session = runtime_session or payload.get("session")
    return session if isinstance(session, str) and SESSION_RE.fullmatch(session) else None


def _size(turn):
    return len(json.dumps(turn))


def _cut_steps(turn, field, limit, mark, nested=False):
    steps = []
    for step in turn.get("trail", []):
        holder = step.get("input") if nested else step
        value = holder.get(field) if isinstance(holder, dict) else None
        if isinstance(value, str) and len(value) > limit:
            if nested:
                step = dict(step, input=dict(step["input"], **{field: value[:limit]}), **{mark: True})
            else:
                step = dict(step, **{field: value[:limit], mark: True})
        steps.append(step)
    return dict(turn, trail=steps)


def bounded(turn):
    """The turn as the response carries it, within MAX_RESPONSE_CHARS. Past
    that it is cut in stages, re-serialised after each and marked: each
    step's code to CODE_PREVIEW, each step's printed output and error to
    OUTPUT_PREVIEW, the answer to RESULT_PREVIEW, and last the trail
    dropped. What remains is always within the bound."""
    if _size(turn) <= MAX_RESPONSE_CHARS:
        return turn
    turn = _cut_steps(turn, "code", CODE_PREVIEW, "input_truncated", nested=True)
    if _size(turn) <= MAX_RESPONSE_CHARS:
        return turn
    turn = _cut_steps(turn, "output", OUTPUT_PREVIEW, "output_truncated")
    turn = _cut_steps(turn, "error", OUTPUT_PREVIEW, "error_truncated")
    if _size(turn) <= MAX_RESPONSE_CHARS:
        return turn
    result = turn.get("result")
    if isinstance(result, str) and len(result) > RESULT_PREVIEW:
        turn = dict(turn, result=result[:RESULT_PREVIEW], result_truncated=True)
    figures = turn.get("unsupported_figures")
    if isinstance(figures, list) and len(figures) > FIGURES_PREVIEW:
        turn = dict(turn, unsupported_figures=figures[:FIGURES_PREVIEW], unsupported_figures_truncated=True)
    if _size(turn) <= MAX_RESPONSE_CHARS:
        return turn
    turn = dict(turn, trail=[], trail_truncated=True)
    if _size(turn) <= MAX_RESPONSE_CHARS:
        return turn
    # Nothing recognisable is left to cut, so the answer alone goes back,
    # which with every other field dropped is within the bound by
    # construction.
    return {"result": str(turn.get("result", ""))[:RESULT_PREVIEW], "trail": [], "unsupported_figures": [],
            "restated": bool(turn.get("restated")), "response_truncated": True}


class Admitted:
    """The two bounds the SDK leaves to the application, as ASGI middleware
    so they are applied before the SDK reads and parses the body: a request
    must declare a body of at most MAX_BODY_BYTES, and the process admits
    MAX_TURNS_IN_FLIGHT turns at once."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] != "POST":
            return await self.app(scope, receive, send)
        length = dict(scope["headers"]).get(b"content-length", b"")
        if not length.isdigit() or not 0 < int(length) <= MAX_BODY_BYTES:
            return await refused(413, "request body must be 1..2MB")(scope, receive, send)
        if not _turns_in_flight.acquire(blocking=False):
            busy = f"the agent is serving {MAX_TURNS_IN_FLIGHT} turns already; try again"
            return await refused(503, busy)(scope, receive, send)
        try:
            await self.app(scope, receive, send)
        finally:
            _turns_in_flight.release()


def refused(status, error):
    return JSONResponse({"error": error}, status_code=status)


app = BedrockAgentCoreApp(middleware=[Middleware(Admitted)])

# The on-behalf-of exchange and the model, named here so the contract tests
# can stand in for both.
exchange = orders_token
respond = answer


@app.entrypoint
def invoke(payload, context):
    """One turn. The SDK has parsed the JSON body and calls this on a worker
    thread, inside the request's trace."""
    # Who is asking comes from the token the runtime verified, never from
    # the body. This catches a missing or unusable token, it is not a
    # second authentication, the runtime's authorizer is the only one.
    headers = context.request_headers or {}
    customer = customer_from(headers)
    subject = subject_from(headers)
    if customer is None or subject is None:
        return refused(401, "no verified caller")
    if not isinstance(payload, dict):
        return refused(400, "payload must be a JSON object")
    prompt = payload.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        return refused(400, "prompt is required")
    if len(prompt) > MAX_PROMPT_CHARS:
        return refused(400, f"prompt is longer than {MAX_PROMPT_CHARS} characters")
    session = session_from(context.session_id, payload)
    if session is None:
        return refused(400, "a session id is required")
    # Every failure is answered here. An exception that reached the SDK
    # would go back to the client as a 500 carrying its message.
    try:
        with one_turn(subject, session):
            # Trusted code gets the token for the order service, on behalf
            # of the customer, before the model runs. The model chooses
            # what to ask the gateway; it never holds what authenticates
            # the asking.
            gateway_token = exchange(bearer_from(headers))
            turn = respond(prompt, customer, session, gateway_token, subject)
        # The trail is the route the model took and what its code printed;
        # unsupported_figures lists any figure in the answer that no tool
        # result in the conversation or the date contains, after the one
        # restatement the check may have asked for.
        return bounded(turn)
    except BudgetExceeded as exc:
        print(f"turn ended for {customer}: {exc}")
        return refused(502, "the model exceeded its tool budget for this turn")
    except Exception as exc:  # noqa: BLE001 — any other failure in the turn is a 502
        # The class and an AWS error code only; a message can carry a
        # response body, a token or the model's code.
        print(f"turn failed for {customer}: {describe(exc)}")
        return refused(502, "request failed")


if __name__ == "__main__":
    # The host is named because the SDK binds to localhost unless it finds
    # Docker's marker file, and the runtime has to reach the port.
    app.run(host="0.0.0.0")  # nosec B104 - the container listens on all interfaces by design
