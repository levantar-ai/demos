"""The sandbox from post 04, now a tool the model may choose.

Post 04 wrote the pandas itself and ran it for every CSV it was given. Here
the code is written by the model, for a question nobody anticipated, and
this module only runs it. The session is still the Code Interpreter from
post 04, SANDBOX network mode, so what the model writes cannot reach the
network, the account or any credential the agent holds. One session per
invocation, started the first time the model reaches for the tool and
stopped when the answer is out; the service's session timeout is the
backstop if that stop fails. Code and output are capped so a runaway loop
is bounded in what it can send and read back.
"""

import os

import boto3
from botocore.config import Config
from strands import tool

_client = None

# How long the agent waits on one code interpreter call. This is the agent's
# wait, not the execution: the service may keep running the code until the
# session ends. No automatic retries, a timed-out call is reported as such.
WAIT_SECONDS = 180


def client():
    global _client
    if _client is None:
        _client = boto3.client(
            "bedrock-agentcore",
            config=Config(read_timeout=WAIT_SECONDS, connect_timeout=10, retries={"max_attempts": 1}),
        )
    return _client


MAX_CODE_CHARS = 20_000
MAX_OUTPUT_CHARS = 8_000


def _consume(response):
    """Drain a tool response stream, then raise if the tool reported an error.

    The stream carries either a result or a service exception shape such as
    accessDeniedException or throttlingException. Anything that is not a
    result is a failure and is raised, never read as an empty success.
    """
    # What is kept across events is bounded, output and error alike, with the
    # separators counted. Each event is materialised by boto3 before it gets
    # here, so the bound is on what the agent accumulates, not on what the
    # service sends.
    out, err = _Bounded(), _Bounded()
    for event in response.get("stream", []):
        result = event.get("result")
        if not result:
            kinds = ", ".join(sorted(event)) or "empty event"
            detail = next((v.get("message") for v in event.values() if isinstance(v, dict) and v.get("message")), "")
            raise RuntimeError(f"code interpreter stream error ({kinds}) {detail[:MAX_OUTPUT_CHARS]}".strip())
        target = err if result.get("isError") else out
        for item in result.get("content", []):
            if item.get("type") == "text":
                target.add(item.get("text", ""))
    if err.seen:
        raise RuntimeError(err.text() or "code interpreter tool failed")
    return out.text()


class _Bounded:
    """Text accumulated up to MAX_OUTPUT_CHARS, separators included."""

    def __init__(self):
        self.parts, self.retained, self.truncated, self.seen = [], 0, False, False

    def add(self, text):
        self.seen = True
        if not text:
            return
        room = MAX_OUTPUT_CHARS - self.retained - (1 if self.parts else 0)
        if room <= 0:
            self.truncated = True
            return
        if len(text) > room:
            text, self.truncated = text[:room], True
        self.parts.append(text)
        self.retained += len(text) + (1 if len(self.parts) > 1 else 0)

    def text(self):
        text = "\n".join(self.parts).strip()
        if self.truncated:
            text += f"\n... output truncated at {MAX_OUTPUT_CHARS} characters"
        return text


def _call(session_id, name, **arguments):
    response = client().invoke_code_interpreter(
        codeInterpreterIdentifier=os.environ["CODE_INTERPRETER_ID"],
        sessionId=session_id,
        name=name,
        arguments=arguments,
    )
    return _consume(response)


def write_files(session_id, path, text):
    return _call(session_id, "writeFiles", content=[{"path": path, "text": text}])


def execute_code(session_id, code, language="python"):
    return _call(session_id, "executeCode", code=code, language=language)


def stop_session(interpreter, session_id):
    client().stop_code_interpreter_session(
        codeInterpreterIdentifier=interpreter, sessionId=session_id
    )


def session_for(interpreter, name):
    resp = client().start_code_interpreter_session(
        codeInterpreterIdentifier=interpreter,
        name=name,
        sessionTimeoutSeconds=900,
    )
    return resp["sessionId"]


class Sandbox:
    """One sandbox session for one invocation.

    The model sees a single tool, run_python. The session behind it is
    created on the first call, kept for the rest of the invocation so
    variables survive between calls, and closed by whoever created this
    object. The seams are class attributes so the tests can stand in for
    the service without touching AWS.
    """

    start = staticmethod(session_for)
    execute = staticmethod(execute_code)
    put = staticmethod(write_files)
    stop = staticmethod(stop_session)

    def __init__(self, interpreter=None):
        self.interpreter = interpreter or os.environ.get("CODE_INTERPRETER_ID", "")
        self.session_id = None
        # Files a handoff failed to write or refresh. While any is listed the
        # tool refuses to run, so code cannot read a stale copy from an
        # earlier turn as if it were the latest result.
        self.unavailable = set()

    @tool
    def run_python(self, code: str) -> str:
        """Run Python code in an isolated sandbox and return what it prints.

        Use this for any counting, summing, averaging, sorting or date
        arithmetic over the customer's orders rather than working it out in
        your head. pandas is installed. The sandbox has no network access and
        no credentials. When the latest orders___list_orders call in this
        conversation returned non-empty text and the agent successfully
        wrote it, that text is available as orders.json, a JSON object with
        an "orders" list. Read that file. Never put order rows into the
        code. If the latest call failed, returned no usable text or could
        not be written, this tool refuses to run until orders___list_orders
        is called again and succeeds. Print the results you want to read.
        Variables
        persist between calls within one conversation turn. An execution
        error is returned when the code fails, so correct the code and run
        it again.

        Args:
            code: The Python source to execute. Print anything you need back.
        """
        if len(code) > MAX_CODE_CHARS:
            raise ValueError(f"code is {len(code)} characters, the limit is {MAX_CODE_CHARS}")
        if self.unavailable:
            names = ", ".join(sorted(self.unavailable))
            raise RuntimeError(f"{names} could not be written to the sandbox this turn; call the tool that provides it again")
        if self.session_id is None:
            self.session_id = self.start(self.interpreter, "analysis")
        return self.execute(self.session_id, code)

    def write(self, path, text):
        """Put a file into this turn's session, starting it if needed.

        Called by trusted code, not by the model: the handoff hook writes
        the gateway's result here so the model computes over the rows the
        gateway returned rather than over a copy it typed into its code.
        """
        if self.session_id is None:
            self.session_id = self.start(self.interpreter, "analysis")
        self.put(self.session_id, path, text)

    def close(self):
        """Stop the session, retrying once. The id is forgotten only once the
        stop succeeded; if both attempts fail the error reaches the caller,
        and the service's 900 second session lifetime is the backstop."""
        if self.session_id is None:
            return
        try:
            self.stop(self.interpreter, self.session_id)
        except Exception as exc:  # noqa: BLE001 — one retry, then the caller hears about it
            print(f"stopping sandbox session {self.session_id} failed once, retrying: {exc}")
            self.stop(self.interpreter, self.session_id)
        self.session_id = None
