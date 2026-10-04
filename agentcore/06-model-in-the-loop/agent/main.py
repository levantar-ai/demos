"""Brightwell's order agent, post 06: the model decides.

Runtime HTTP contract as post 01 (POST /invocations, GET /ping). The runtime
validates the customer's bearer token and forwards it, as post 05, and the
agent still gets its token for the order service from AgentCore Identity on
the customer's behalf (identity.py). What changes is what happens to the
prompt. There is no routing code left in this file. Every prompt goes to a
Bedrock model (model.py) that has been handed the order gateway, the sandbox
and the memory as tools, and the model chooses what to call. The customer
the model acts for comes from the verified token; the token itself is
supplied to the gateway client by this code, so the model chooses arguments,
never credentials, and a wrong customer_id is refused by Cedar at the
gateway, as post 05 set up.
"""

import base64
import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from identity import orders_token
from model import answer
from trail import BudgetExceeded

PORT = 8080
MAX_BODY_BYTES = 2 * 1024 * 1024

# The runtime sends its session id to the container on this header. It is
# the conversation's id for the memory; a caller may also name one in the
# body when invoking the agent outside the runtime. There is no default:
# two clients of one customer must not silently share a conversation.
SESSION_HEADER = "X-Amzn-Bedrock-AgentCore-Runtime-Session-Id"
SESSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")


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
    """
    claims = claims_from(headers) or {}
    if claims.get("token_use") != "access":
        return None
    username = claims.get("username")
    return username if isinstance(username, str) and username else None


def bearer_from(headers):
    """The raw bearer token the runtime forwarded, the subject of the exchange."""
    auth = headers.get("Authorization", "")
    return auth[len("Bearer "):] if auth.startswith("Bearer ") else None


def session_from(headers, payload):
    """The conversation id, the runtime's session header or else the body's,
    or None when neither names a usable one."""
    session = headers.get(SESSION_HEADER) or payload.get("session")
    return session if isinstance(session, str) and SESSION_RE.match(session) else None


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
        if customer is None:
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
        session = session_from(self.headers, payload)
        if session is None:
            self._send(400, {"error": "a session id is required"})
            return
        try:
            # Trusted code gets the token for the order service, on behalf of
            # the customer, before the model runs. The model chooses what to
            # ask the gateway; it never holds what authenticates the asking.
            gateway_token = self.exchange(bearer_from(self.headers))
            result, trail = self.respond(prompt, customer, session, gateway_token)
        except BudgetExceeded as exc:
            print(f"turn ended for {customer}: {exc}")
            self._send(502, {"error": "the model exceeded its tool budget for this turn"})
            return
        except Exception as exc:  # noqa: BLE001 — any other failure in the turn is a 502
            print(f"turn failed for {customer}: {exc}")
            self._send(502, {"error": "request failed"})
            return
        self._send(200, {"result": result, "trail": trail})

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
