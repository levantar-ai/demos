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
import threading
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout

import boto3
from botocore.config import Config
from strands import tool

_client = None

# How long the agent waits on one code interpreter call, wall clock, enforced
# here by running the call on a worker thread and abandoning it at the
# deadline. Starting, writing, running and stopping all go through it. The
# code may still be running in the session after that; the stop at the end
# of the turn ends it when the stop succeeds. One HTTP attempt per call, so
# a slow call is not silently made twice. At most MAX_IN_FLIGHT calls are in
# flight in the process at once, admitted by a semaphore the worker releases
# when its call finishes, so nothing queues behind the workers: a call that
# finds every slot taken is refused outright, except a stop, which waits for
# a slot so that a busy process still ends its sessions.
WAIT_SECONDS = 180
MAX_IN_FLIGHT = 8
_calls = ThreadPoolExecutor(max_workers=MAX_IN_FLIGHT, thread_name_prefix="sandbox-call")
_slots = threading.BoundedSemaphore(MAX_IN_FLIGHT)


def client():
    global _client
    if _client is None:
        _client = boto3.client(
            "bedrock-agentcore",
            config=Config(read_timeout=WAIT_SECONDS, connect_timeout=10, retries={"total_max_attempts": 1}),
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


class Abandoned(RuntimeError):
    """A call the agent gave up waiting on. The service may still be
    running it."""


def _invoke(session_id, name, arguments):
    response = client().invoke_code_interpreter(
        codeInterpreterIdentifier=os.environ["CODE_INTERPRETER_ID"],
        sessionId=session_id,
        name=name,
        arguments=arguments,
    )
    return _consume(response)


def _start(interpreter, name):
    resp = client().start_code_interpreter_session(
        codeInterpreterIdentifier=interpreter,
        name=name,
        sessionTimeoutSeconds=900,
    )
    return resp["sessionId"]


def _stop(interpreter, session_id):
    client().stop_code_interpreter_session(
        codeInterpreterIdentifier=interpreter, sessionId=session_id
    )


def _held(fn, args):
    """Run the call on the worker and give the slot back when it is over,
    however it ended, so an abandoned call holds its slot only as long as
    its HTTP attempt lasts."""
    try:
        return fn(*args)
    finally:
        _slots.release()


def _call(name, fn, *args, wait=False):
    """Run one service call with a wall-clock deadline, one of at most
    MAX_IN_FLIGHT in the process. A call that finds no free slot is refused,
    unless it asked to wait, which a stop does."""
    admitted = _slots.acquire(timeout=WAIT_SECONDS) if wait else _slots.acquire(blocking=False)
    if not admitted:
        raise RuntimeError(f"{name} refused: the sandbox already has {MAX_IN_FLIGHT} calls in flight; try again")
    try:
        future = _calls.submit(_held, fn, args)
    except BaseException:
        _slots.release()
        raise
    try:
        return future.result(timeout=WAIT_SECONDS)
    except FutureTimeout:
        raise Abandoned(
            f"{name} did not finish within {WAIT_SECONDS} seconds; the session will be stopped at the end of the turn"
        ) from None


def write_files(session_id, path, text):
    return _call("writeFiles", _invoke, session_id, "writeFiles", {"content": [{"path": path, "text": text}]})


def execute_code(session_id, code, language="python"):
    return _call("executeCode", _invoke, session_id, "executeCode", {"code": code, "language": language})


def session_for(interpreter, name):
    return _call("startCodeInterpreterSession", _start, interpreter, name)


def stop_session(interpreter, session_id):
    return _call("stopCodeInterpreterSession", _stop, interpreter, session_id, wait=True)


class Sandbox:
    """One sandbox session for one invocation.

    The model sees a single tool, run_python. The session behind it is
    created on the first call, kept for the rest of the invocation so
    variables survive between calls, and closed by whoever created this
    object. Files that trusted code stages for the session are written
    into it just before the first call's code runs, so a turn in which the
    model never runs code starts no session. One lock serialises starting
    the session, writing to it, running in it and stopping it. The seams
    are class attributes so the tests can stand in for the service without
    touching AWS.
    """

    start = staticmethod(session_for)
    execute = staticmethod(execute_code)
    put = staticmethod(write_files)
    stop = staticmethod(stop_session)

    def __init__(self, interpreter=None):
        self.interpreter = interpreter or os.environ.get("CODE_INTERPRETER_ID", "")
        self.session_id = None
        self._lock = threading.Lock()
        # Set when a call was given up on at the deadline: the service may
        # still be running it when the session is stopped.
        self.abandoned = False
        # Files held for the session, path to text, written before the next
        # run and forgotten once written. Trusted code puts them here.
        self.staged = {}
        self.written = []
        # Files whose latest providing call produced nothing to stage. While
        # any is listed the tool refuses to run, so code cannot read a copy
        # from an earlier turn as if it were the latest result.
        self.unavailable = set()

    @tool
    def run_python(self, code: str) -> str:
        """Run Python code in an isolated sandbox and return what it prints.

        Use this for any counting, summing, averaging, sorting or date
        arithmetic over the customer's orders rather than working it out in
        your head. pandas is installed. The sandbox has no network access and
        no credentials. When the latest orders___list_orders call in this
        conversation returned non-empty text, the agent writes that text
        into the sandbox as orders.json, a JSON object with an "orders"
        list, before your code runs. Read that file with totals as
        decimals, json.load(open("orders.json"), parse_float=Decimal), and
        print money to two decimal places. Never put order rows into the
        code. If the latest call failed or returned no usable text, this
        tool refuses to run until orders___list_orders is called again and
        succeeds; if the file could not be written, the error says so and
        running again writes it again. Print every figure your answer will
        state, including how many orders a figure covers; do not state a
        number the code did not print. Variables persist between calls
        within one conversation turn. An execution error is returned when
        the code fails, so correct the code and run it again.

        Args:
            code: The Python source to execute. Print anything you need back.
        """
        if len(code) > MAX_CODE_CHARS:
            raise ValueError(f"code is {len(code)} characters, the limit is {MAX_CODE_CHARS}")
        with self._lock:
            if self.unavailable:
                names = ", ".join(sorted(self.unavailable))
                raise RuntimeError(
                    f"{names} not available this turn: the latest call that provides it did not produce a result; "
                    "call that tool again"
                )
            if self.session_id is None:
                self.session_id = self.start(self.interpreter, "analysis")
            for path in list(self.staged):
                try:
                    self.put(self.session_id, path, self.staged[path])
                except Exception as exc:
                    raise RuntimeError(f"{path} could not be written to the sandbox: {exc}; run again to retry") from exc
                del self.staged[path]
                self.written.append(path)
            try:
                return self.execute(self.session_id, code)
            except Abandoned:
                self.abandoned = True
                raise

    def stage(self, path, text):
        """Hold a file for this turn's session. It is written just before
        the model's code next runs, by run_python, so staging starts no
        session. Called by trusted code, not by the model: the handoff hook
        stages the gateway's result here so the model computes over the
        rows the gateway returned rather than over a copy it typed into its
        code."""
        with self._lock:
            self.staged[path] = text
            self.unavailable.discard(path)

    def withhold(self, path):
        """Forget anything staged under this path and refuse to run until
        it is staged again."""
        with self._lock:
            self.staged.pop(path, None)
            self.unavailable.add(path)

    def close(self):
        """Stop the session, retrying once. The id is forgotten only once the
        stop succeeded; if both attempts fail the error reaches the caller,
        and the service's 900 second session lifetime is the backstop. A
        stop is what ends code the agent gave up waiting on, so one with an
        abandoned call behind it is logged as such."""
        with self._lock:
            if self.session_id is None:
                return
            if self.abandoned:
                print(f"stopping sandbox session {self.session_id} with an abandoned call still in flight")
            try:
                self.stop(self.interpreter, self.session_id)
            except Exception as exc:  # noqa: BLE001 — one retry, then the caller hears about it
                print(f"stopping sandbox session {self.session_id} failed once, retrying: {type(exc).__name__}")
                self.stop(self.interpreter, self.session_id)
            self.session_id = None
