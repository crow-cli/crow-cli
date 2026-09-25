"""rlm — recursive language modeling: ask a fork of THIS session instead of
reading the thing yourself.

Context protection by delegation. Instead of the parent reading a
maybe-relevant file (always maximally increasing context), a fork reads it
and reports yes/no on relevance. The fork is a copy of this session's history
under a new wire id, so it starts with everything the caller already knows —
warm KV cache reuse where the provider supports it, cold agent process
regardless — and its ANSWER is the only thing that comes back into the
caller's context.

The budget is ONE delegation deep (MAX_RLM_DEPTH), enforced from the
identity rail the execute prologue injects: a value resolved off the
session's own persisted row, never supplied by the model. A delegate that
tries to delegate is refused — fork-of-fork does not exist yet, and
pretending otherwise is the infinity mirror.

The transcript IS the mailbox. An rlm(wait=False) call returns immediately
with the delegate's id; its transcript lands in the same database under
that id as it works, so ``memory("list", session_id=...)`` is how an async
delegation gets collected — no delivery table, because a task owner goes
idle between launch and completion while an rlm caller is a running cell.

The driver is :mod:`crow_cli.client2.subagent` — ACP v2, where
``PromptResponse`` is empty and a turn's outcome arrives afterwards as an
idle ``state_update``. That is what makes a wait which runs out recoverable:
the notification is still coming and the queue it lands in outlives the
wait, so an impatient caller hands the turn to a background waiter and gets
a handle back instead of killing a delegate that was about to answer.
"""

import asyncio
import os
import sys
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path

import crow_cli.memory as cm
from crow_cli.client2.subagent import ChildExited, SubagentDriver, child_config

from .register import current_cell, db_uri, rlm_depth, subtool
from .results import RlmResult, RlmToolError

MAX_RLM_DEPTH = 1
_RLM_TIMEOUT = 900.0

# Same reason memory.py keeps its engine in one: importlib.reload re-executes
# this source in the EXISTING module dict, so a module-level ``_engine = None``
# would drop the handle on every reload() and leak its connection pool.
_state: dict = globals().setdefault("_state", {})


def _dispose() -> None:
    """Drop the cached engine (test hygiene, and a db_uri that changed)."""
    engine = _state.get("engine")
    if engine is not None:
        with suppress(Exception):
            engine.dispose()
    _state["engine"] = None
    _state["uri"] = None


def _engine():
    """The read-only engine for the injected crow.db, cached per uri.

    rlm only READS — the fork write happens in the child agent process — so
    it keeps its own engine rather than borrowing memory.py's private one.
    """
    uri = db_uri()
    if uri is None:
        raise RlmToolError(
            "no database — rlm() reads the crow.db that execute's prologue"
            " injects on the identity rail; outside a kernel, point the rail"
            " at one with crow_cli.tools.register.begin_cell(db_uri=…)"
        )
    if _state.get("uri") != uri:
        _dispose()
        if uri.startswith("sqlite:///"):
            # mode=ro cannot CREATE, so a missing file is "unable to open
            # database file" — true, and useless. Name the path instead.
            path = Path(uri.removeprefix("sqlite:///"))
            if not path.exists():
                raise RlmToolError(
                    f"no database at {path} — nothing has been remembered yet"
                )
        _state["engine"] = cm.get_ro_engine(uri)
        _state["uri"] = uri
    return _state["engine"]


def _identity() -> tuple[str, int]:
    """(wire_id, depth) for this cell — both from the rail, never the model."""
    cell = current_cell()
    if cell is None or not cell.session_id:
        raise RlmToolError(
            "no session identity — rlm() forks THIS session, which only"
            " exists inside an execute cell (the prologue injects it);"
            " outside a kernel there is nothing to fork"
        )
    return cell.session_id, rlm_depth()


def _delegate_prompt(prompt: str, depth: int) -> str:
    """The delegate's prompt. The house idiom for fork behaviour control is
    PROMPT INSTRUCTIONS — the analysis/ideas forks stay read-only the same
    way — not history surgery.
    """
    return (
        "You are a delegate: a copy of the agent above, forked from its own"
        " history to carry out a delegated task without spending its context."
        " Everything you need is already in the history you were forked"
        " with.\n\n"
        "Handle the request and stop. Do not start unrelated work, and do not ask"
        " for clarification — nobody is listening; the agent that sent you is"
        " blocked on this response.\n\n"
        f"Do not delegate again: you are delegation {depth} of a maximum"
        f" {MAX_RLM_DEPTH}, the budget is spent, and rlm() will refuse you."
        "\n\n"
        "Unless the request asks you to change something, change nothing:"
        " you inherited your source's tools, and an edit you make is an edit"
        " it never hears about.\n\n"
        "---\n\n" + prompt
    )


def _delegate_answer(engine, fork_id: str) -> str:
    """The delegate's final answer, read from the shared sqlite.

    The fork's wire id IS its agent_id, so this is a direct row lookup — no
    trunk scan, because task/_child_answer's shape (max agent_idx of the
    trunk) is wrong here: the delegate IS a fork, and load_agent_messages
    chains the trunk prefix in front of its own rows.
    """
    agent = cm.get_agent(engine, fork_id)
    if agent is None:
        return "(the delegate produced no transcript)"
    return cm.last_assistant_text(
        cm.load_agent_messages(engine, agent),
        fallback="(the delegate produced no final answer)",
    )


async def _drive(fork_id: str, driver: SubagentDriver, text: str | None) -> None:
    """One delegate turn in the background, and then the driver is reaped.

    ``text`` is None for a HAND-OFF: the prompt already went out and the
    caller that sent it has left, so what is left is seeing the turn home —
    ``driver.wait``, not ``driver.prompt``, because asking the delegate its
    own question a second time is not a timeout recovery.

    Neither branch is on a clock. A delegation nobody is blocked on has no
    deadline to miss (task's watcher does the same), and killing a delegate
    for being slow loses the answer AND the context the delegation existed to
    protect. The transcript is the record: nobody waits on this task, so a
    failure prints one line to stderr and drops, and keeping the reference in
    _state["live"] is what keeps an idle asyncio.Task from being
    garbage-collected mid-flight.
    """
    try:
        if text is None:
            await driver.wait(fork_id)
        else:
            await driver.prompt(fork_id, text)
    except Exception as e:
        print(
            f"rlm: delegate {fork_id} failed: {type(e).__name__}: {e}",
            file=sys.stderr,
        )
    finally:
        _state.get("live", {}).pop(fork_id, None)
        with suppress(Exception):
            await driver.close()


@dataclass
class LiveDelegate:
    """One delegate this kernel is driving in the background.

    ``task`` is kept because an unreferenced asyncio.Task can be garbage
    collected mid-flight. ``driver`` is kept because it is the only handle on
    the child process, and "the delegate is not lost" is a claim somebody had
    better be able to check — and to cancel.
    """

    fork_id: str
    driver: SubagentDriver
    task: asyncio.Task


def _hand_off(
    fork_id: str, driver: SubagentDriver, text: str | None
) -> LiveDelegate:
    """Put a delegate into the background and return its handle."""
    task = asyncio.create_task(
        _drive(fork_id, driver, text), name=f"crow-rlm-{fork_id}"
    )
    live = LiveDelegate(fork_id=fork_id, driver=driver, task=task)
    _state.setdefault("live", {})[fork_id] = live
    return live


def _handle(fork_id: str, prompt: str, depth: int) -> RlmResult:
    """The not-yet-answered result: a wire id and a promise, no answer.

    One shape for both ways a delegation can be outstanding — launched with
    ``wait=False``, or waited for and the wait ran out — because from the
    caller's side they are the same situation, and ``RlmResult.text`` already
    says what to do about it.
    """
    return RlmResult(
        session_id=fork_id, answer="", prompt=prompt, waited=False, depth=depth
    )


@subtool(tool="rlm")
async def rlm(
    prompt: str,
    *,
    offset: int = 1,
    wait: bool = True,
    tools: bool = True,
    model: str | None = None,
    timeout: float | None = _RLM_TIMEOUT,
) -> RlmResult:
    """Fork this session and have the copy handle a delegated request, so the
    response — not the reading it took to find it — is what lands in your
    context.

    The delegate starts with everything you already know (it is forked from
    your history), answers, and stops. ``print(r.text)`` is the display
    channel: ``r.answer`` is the whole answer for slicing and grepping, and
    ``r.session_id`` is the delegate's WIRE id — for a fork, its ``agent_id``
    (``{session}-{agent}-{fork}``). ``memory("list", session_id=...)``
    resolves a bare session id or a wire agent id, so the transcript is
    readable under that id — which is also how an async delegation gets
    collected.

    Args:
        prompt: the request for the delegate. Put in it everything the delegate
          needs that is not already in your history.
        offset: messages back from HEAD to fork (default 1 — the delegate
          never sees the moment you chose to delegate, or it would wonder
          why "it" did not work and try again). The server snaps the cut
          off any tool-call group or prior delegation that must not end a
          history.
        wait: True blocks until the delegate answers. False returns the
          handle immediately and the delegate runs in the background; collect
          it later via memory("list", session_id=r.session_id).
        tools: False strips the delegate's tool supply (an interrogation
          fork); True inherits this session's MCP servers.
        model: override the delegate's model (default: inherit yours).
        timeout: seconds to wait before giving up on a BLOCKING delegation
          (default 900). None waits forever. Running out is not a failure and
          does not raise: the delegate keeps working, the call comes back as
          an unwaited handle (``r.waited`` False), and
          ``memory("list", session_id=r.session_id)`` collects it exactly as
          it would a ``wait=False`` one.

    Raises RlmToolError when the budget is spent (this session already IS a
    delegate), when there is no identity rail, when the fork fails, or when
    the delegate dies before it answers.
    """
    wire_id, depth = _identity()
    if depth >= MAX_RLM_DEPTH:
        raise RlmToolError(
            f"delegation budget spent: this session is already {depth} deep"
            f" (MAX_RLM_DEPTH={MAX_RLM_DEPTH}) — a delegate cannot delegate,"
            " or the mirror is back. Answer from the history you were forked"
            " with."
        )
    engine = _engine()
    cwd = os.getcwd()
    servers = cm.get_session_mcp_servers(engine, wire_id) if tools else []
    driver = SubagentDriver()
    try:
        await driver.start(cwd, model=model, **child_config())
        fork_id = await driver.fork_session(
            wire_id,
            cwd,
            mcp_servers=servers,
            message_offset=offset,
            rlm_depth=depth + 1,
        )
    except Exception as e:
        with suppress(Exception):
            await driver.close()
        raise RlmToolError(f"could not fork session '{wire_id}': {e}") from e

    text = _delegate_prompt(prompt, depth + 1)
    if not wait:
        _hand_off(fork_id, driver, text)
        return _handle(fork_id, prompt, depth + 1)
    handed_off = False
    try:
        stop = await driver.prompt(fork_id, text, timeout=timeout)
    except TimeoutError:
        # What ran out is the caller's patience, not the delegate's turn: it
        # is mid-work, its transcript is the mailbox, and the answer is still
        # coming. So the turn goes to a background waiter and the caller gets
        # the handle an async delegation would have got. Raising here — and
        # closing the driver in the finally, which kills the child — is what
        # v1 did while its own message promised the delegate was "not lost".
        handed_off = True
        _hand_off(fork_id, driver, None)
    except ChildExited as e:
        raise RlmToolError(
            f"delegate {fork_id} died before it answered: {e}"
        ) from e
    finally:
        if not handed_off:
            with suppress(Exception):
                await driver.close()
    if handed_off:
        return _handle(fork_id, prompt, depth + 1)
    return RlmResult(
        session_id=fork_id,
        answer=_delegate_answer(engine, fork_id),
        prompt=prompt,
        waited=True,
        depth=depth + 1,
        stop_reason=stop,
    )
