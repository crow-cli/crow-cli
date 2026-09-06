"""rlm — recursive language modeling: ask a fork of THIS session instead of
reading the thing yourself.

The pattern TODO.md named and kept: context protection by delegation.
Instead of the parent reading a maybe-relevant file (always maximally
increasing context), a fork reads it and reports yes/no on relevance. The
fork is a copy of this session's history under a new wire id, so it starts
with everything the caller already knows — warm KV cache reuse where the
provider supports it, cold agent process regardless — and its ANSWER is the
only thing that comes back into the caller's context.

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
"""

import asyncio
import os
import sys
from contextlib import suppress
from pathlib import Path

import crow_cli.memory as cm
from crow_cli.client.subagent import SubagentDriver, child_config

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
    PROMPT INSTRUCTIONS (TODO.md: "the analysis/ideas forks rely on PROMPT
    INSTRUCTIONS to stay read-only") — not history surgery.
    """
    return (
        "You are a delegate: a copy of the agent above, forked from its own"
        " history to answer ONE question without spending its context."
        " Everything you need is already in the history you were forked"
        " with.\n\n"
        "Answer the question and stop. Do not start new work, and do not ask"
        " for clarification — nobody is listening; the agent that sent you is"
        " blocked on this answer.\n\n"
        f"Do not delegate again: you are delegation {depth} of a maximum"
        f" {MAX_RLM_DEPTH}, the budget is spent, and rlm() will refuse you."
        "\n\n"
        "Unless the question asks you to change something, change nothing:"
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


async def _drive(
    fork_id: str, driver: SubagentDriver, text: str, timeout: float | None,
) -> None:
    """One delegate turn in the background. The transcript is the record —
    nobody waits on this task, so a failure prints one line to stderr and
    drops; keeping the reference in _state["live"] is what keeps an idle
    asyncio.Task from being garbage-collected mid-flight.
    """
    try:
        await asyncio.wait_for(driver.prompt(fork_id, text), timeout)
    except Exception as e:
        print(
            f"rlm: delegate {fork_id} failed: {type(e).__name__}: {e}",
            file=sys.stderr,
        )
    finally:
        _state.get("live", {}).pop(fork_id, None)
        with suppress(Exception):
            await driver.close()


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
    """Fork this session and have the copy answer ONE question, so the
    answer — not the reading it took to find it — is what lands in your
    context.

    The delegate starts with everything you already know (it is forked from
    your history), answers, and stops. ``print(r.text)`` is the display
    channel: ``r.answer`` is the whole answer for slicing and grepping,
    ``r.session_id`` is the delegate's id, and its transcript is readable
    with ``memory("list", session_id=...)`` — which is also how an async
    delegation gets collected.

    Args:
        prompt: the ONE question. Put in it everything the delegate needs
          that is not already in your history.
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
          (default 900). None waits forever. The delegate is not lost on
          timeout — its transcript keeps growing under r.session_id.

    Raises RlmToolError when the budget is spent (this session already IS a
    delegate), when there is no identity rail, or when the fork/prompt
    fails.
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
        task = asyncio.create_task(_drive(fork_id, driver, text, timeout))
        _state.setdefault("live", {})[fork_id] = task
        return RlmResult(
            session_id=fork_id,
            answer="",
            prompt=prompt,
            waited=False,
            depth=depth + 1,
        )
    try:
        resp = await asyncio.wait_for(driver.prompt(fork_id, text), timeout)
    except TimeoutError as e:
        raise RlmToolError(
            f"delegate {fork_id} did not answer within {timeout}s — it is"
            " not lost: its transcript keeps growing under that id, read it"
            f' with memory("list", session_id="{fork_id}")'
        ) from e
    finally:
        with suppress(Exception):
            await driver.close()
    return RlmResult(
        session_id=fork_id,
        answer=_delegate_answer(engine, fork_id),
        prompt=prompt,
        waited=True,
        depth=depth + 1,
        stop_reason=resp.stop_reason,
    )
