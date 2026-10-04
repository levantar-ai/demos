"""The sandbox from post 04, now a tool the model may choose.

Post 04 wrote the pandas itself and ran it for every CSV it was given. Here
the code is written by the model, for a question nobody anticipated, and
this module only runs it. The session is still the Code Interpreter from
post 04, SANDBOX network mode, so what the model writes cannot reach the
network, the account or any credential the agent holds. One session per
invocation, started the first time the model reaches for the tool and
stopped by the handler when the answer is out, so nothing is left running.
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


def _consume(response):
    """Drain a tool response stream, then raise if the tool reported an error."""
    chunks, error = [], None
    for event in response.get("stream", []):
        result = event.get("result")
        if not result:
            continue
        text = "\n".join(
            item["text"]
            for item in result.get("content", [])
            if item.get("type") == "text"
        )
        if result.get("isError"):
            error = error or text or "code interpreter tool failed"
            continue
        if text:
            chunks.append(text)
    if error is not None:
        raise RuntimeError(error)
    return "\n".join(chunks).strip()


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
        if self.session_id is None:
            self.session_id = self.start(self.interpreter, "analysis")
        return self.execute(self.session_id, code)

    def close(self):
        if self.session_id is None:
            return
        session_id, self.session_id = self.session_id, None
        self.stop(self.interpreter, session_id)
