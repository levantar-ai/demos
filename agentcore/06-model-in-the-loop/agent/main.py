"""Brightwell's order agent, post 06: the model decides.

Runtime HTTP contract as post 01 (POST /invocations, GET /ping). The runtime
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
"""

import base64
import json
import re
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from identity import orders_token
from model import answer
from trail import BudgetExceeded, describe

PORT = 8080
MAX_BODY_BYTES = 2 * 1024 * 1024
# A question for an order agent is a sentence or a paragraph. Anything
# larger is a cost rather than a question, and is refused before the model.
MAX_PROMPT_CHARS = 4_000

# The runtime sends its session id to the container on this header. It is
# the conversation's id for the memory; a caller may also name one in the
# body when invoking the agent outside the runtime. There is no default:
# two clients of one customer must not silently share a conversation. This
# is the application's own grammar for an id, with the runtime's minimum of
# 33 characters, so a conversation outside the runtime is named the way one
# inside it is. A session id is a locator within the actor's own namespace,
# never an authorisation boundary: the actor comes from the token, and any
# client holding that token may continue any of that actor's conversations
# it knows the id of.
SESSION_HEADER = "X-Amzn-Bedrock-AgentCore-Runtime-Session-Id"
SESSION_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{32,127}")

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


def session_from(headers, payload):
    """The conversation id, the runtime's session header or else the body's,
    or None when neither names a usable one."""
    session = headers.get(SESSION_HEADER) or payload.get("session")
    return session if isinstance(session, str) and SESSION_RE.fullmatch(session) else None


class Handler(BaseHTTPRequestHandler):
    exchange = staticmethod(orders_token)
    respond = staticmethod(answer)

    def do_GET(self):
        if self.path == "/ping":
            self._send(200, {"status": "Healthy"})
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/invocations":
            self._send(404, {"error": "not found"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._send(400, {"error": "invalid Content-Length"})
            return
        if length <= 0 or length > MAX_BODY_BYTES:
            self._send(413, {"error": "request body must be 1..2MB"})
            return
        # The body is read before anything is decided about it, so an early
        # response never races a client that is still sending.
        body = self.rfile.read(length)
        # Who is asking comes from the token the runtime verified, never from
        # the body. This catches a missing or unusable token, it is not a
        # second authentication, the runtime's authorizer is the only one.
        customer = customer_from(self.headers)
        subject = subject_from(self.headers)
        if customer is None or subject is None:
            self._send(401, {"error": "no verified caller"})
            return
        try:
            payload = json.loads(body or b"{}")
        except json.JSONDecodeError:
            self._send(400, {"error": "invalid JSON"})
            return
        if not isinstance(payload, dict):
            self._send(400, {"error": "payload must be a JSON object"})
            return
        prompt = payload.get("prompt")
        if not isinstance(prompt, str) or not prompt.strip():
            self._send(400, {"error": "prompt is required"})
            return
        if len(prompt) > MAX_PROMPT_CHARS:
            self._send(400, {"error": f"prompt is longer than {MAX_PROMPT_CHARS} characters"})
            return
        session = session_from(self.headers, payload)
        if session is None:
            self._send(400, {"error": "a session id is required"})
            return
        try:
            with one_turn(subject, session):
                # Trusted code gets the token for the order service, on behalf
                # of the customer, before the model runs. The model chooses
                # what to ask the gateway; it never holds what authenticates
                # the asking.
                gateway_token = self.exchange(bearer_from(self.headers))
                result, trail, unsupported = self.respond(prompt, customer, session, gateway_token, subject)
        except BudgetExceeded as exc:
            print(f"turn ended for {customer}: {exc}")
            self._send(502, {"error": "the model exceeded its tool budget for this turn"})
            return
        except Exception as exc:  # noqa: BLE001 — any other failure in the turn is a 502
            # The class and an AWS error code only; a message can carry a
            # response body, a token or the model's code.
            print(f"turn failed for {customer}: {describe(exc)}")
            self._send(502, {"error": "request failed"})
            return
        # The trail is the route the model took and what its code printed;
        # unsupported_figures lists any figure in the answer that no tool
        # result in the conversation, the prompt or the date contains.
        self._send(200, {"result": result, "trail": trail, "unsupported_figures": unsupported})

    def _send(self, status, body):
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt, *args):
        print(f"{self.address_string()} {fmt % args}")


if __name__ == "__main__":
    print(f"agent listening on :{PORT}")
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()  # nosec B104 - the container listens on all interfaces by design
