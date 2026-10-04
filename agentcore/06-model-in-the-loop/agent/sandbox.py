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
from strands import tool

_client = None


def client():
    global _client
    if _client is None:
        _client = boto3.client("bedrock-agentcore")
    return _client


MAX_CODE_CHARS = 20_000
MAX_OUTPUT_CHARS = 8_000


def _consume(response):
    """Drain a tool response stream, then raise if the tool reported an error.

    The stream carries either a result or a service exception shape such as
    accessDeniedException or throttlingException. Anything that is not a
    result is a failure and is raised, never read as an empty success.
    """
    chunks, error, retained, truncated = [], None, 0, False
    for event in response.get("stream", []):
        result = event.get("result")
        if not result:
            kinds = ", ".join(sorted(event)) or "empty event"
            detail = next((v.get("message") for v in event.values() if isinstance(v, dict) and v.get("message")), "")
            raise RuntimeError(f"code interpreter stream error ({kinds}) {detail}".strip())
        text = "\n".join(
            item["text"]
            for item in result.get("content", [])
            if item.get("type") == "text"
        )
        if result.get("isError"):
            error = error or text or "code interpreter tool failed"
            continue
        # Keep at most the limit in memory; the rest of the stream is read
        # and dropped rather than accumulated.
        if text and retained < MAX_OUTPUT_CHARS:
            chunks.append(text[: MAX_OUTPUT_CHARS - retained])
            retained += len(chunks[-1])
        elif text:
            truncated = True
    if error is not None:
        raise RuntimeError(error[:MAX_OUTPUT_CHARS])
    text = "\n".join(chunks).strip()
    if truncated or len(text) >= MAX_OUTPUT_CHARS:
        text = text[:MAX_OUTPUT_CHARS] + f"\n... output truncated at {MAX_OUTPUT_CHARS} characters"
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
    stop = staticmethod(stop_session)

    def __init__(self, interpreter=None):
        self.interpreter = interpreter or os.environ.get("CODE_INTERPRETER_ID", "")
        self.session_id = None

    @tool
    def run_python(self, code: str) -> str:
        """Run Python code in an isolated sandbox and return what it prints.

        Use this for any calculation, aggregation, date arithmetic or
        comparison over the customer's orders rather than working it out in
        your head. pandas is installed. The sandbox has no network access and
        no credentials, so put the data you need into the code itself, for
        example as a list of dicts from an earlier tool result, and print the
        results you want to read. Variables persist between calls within one
        conversation turn. A traceback is returned when the code fails, so
        fix the code and run it again.

        Args:
            code: The Python source to execute. Print anything you need back.
        """
        if len(code) > MAX_CODE_CHARS:
            raise ValueError(f"code is {len(code)} characters, the limit is {MAX_CODE_CHARS}")
        if self.session_id is None:
            self.session_id = self.start(self.interpreter, "analysis")
        return self.execute(self.session_id, code)

    def close(self):
        """Stop the session. The id is forgotten only once the stop succeeded,
        so a failed stop can be retried by whoever catches the error; the
        service's own 900 second session timeout is the backstop."""
        if self.session_id is None:
            return
        self.stop(self.interpreter, self.session_id)
        self.session_id = None
