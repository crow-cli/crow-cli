"""A project-built agent: its own system prompt, its own compaction.

The shape this file is here to show is the last one — ``AcpAgent(...)`` taking
callables instead of config keys. Everything above it is the two contracts
those callables have to satisfy:

* a SYSTEM PROMPT callable returns
  :class:`~crow_cli.agent.prompt.SystemPromptResponse` — a Jinja template plus
  the args to render it with. One for ``session/new``, and a separate one for
  the generation compaction mints, because they are different moments and a
  project usually wants them to say different things.
* a COMPACTION callable takes
  :class:`~crow_cli.agent.compact.CompactCtx` and returns
  :class:`~crow_cli.agent.compact.CompactResponse` — the next generation's
  system prompt plus the first message of its history. It does NOT create the
  session: ``compact()`` owns the mechanics (next ``agent_idx`` inside the same
  wire session, the row, the handoff message, ``on_compact``), so a custom
  strategy never has to know how an agent id is spelled.

Run it like the crow-cli agent itself:

    uv run python examples/custom_compactor.py --config-dir ~/.agents/crow
"""

import asyncio
from pathlib import Path

import typer
from acp import run_agent

from crow_cli.agent.compact import (
    CompactCtx,
    CompactResponse,
    ask_over_history,
    default_compactor,
)
from crow_cli.agent.hooks import uv_project_hook
from crow_cli.agent.main import AcpAgent
from crow_cli.agent.prompt import SystemPromptResponse, default_system_prompt
from crow_cli.config import Config

app = typer.Typer()


# ---------------------------------------------------------------------------
# Contract 1: the system prompt. Template is static text, everything that
# varies goes in template_args — that split is what keeps the prompts table
# deduped and the provider's prefix cache warm across generations.
# ---------------------------------------------------------------------------

TEMPLATE = """You are the scheduler for {{ workspace }}.

Generation {{ generation }} of session {{ session_id }}.

{{ display_tree }}
"""


def init_sys(config: Config, cwd: str, session_id: str | None = None) -> SystemPromptResponse:
    """The prompt every NEW session gets.

    ``config``, ``cwd`` and ``session_id`` are the only things the harness
    insists on handing you; everything else in ``template_args`` is yours to
    compute. Build on the standard prompt rather than replacing it when you
    want crow's skills catalog and AGENTS.md blocks kept — note that
    ``workspace`` must survive, because the session list is filtered on it.
    """
    base = default_system_prompt(config, cwd, session_id)
    return SystemPromptResponse(
        template=TEMPLATE,
        template_args={**base.template_args, "generation": 1},
    )


def compact_sys(ctx: CompactCtx) -> SystemPromptResponse:
    """The prompt the NEXT generation gets — handed to the compactor as
    ``ctx.system_prompt``, so a custom compactor can reach it and a project can
    replace it independently of ``init_sys``.

    This is the "wild stuff" slot: the successor is a different animal from a
    fresh session. It inherits a summary instead of a conversation, so it can be
    told which generation it is, and the tree it was handed at birth is by now
    stale — recompute it against the cwd as it stands.
    """
    session = ctx.session
    fresh = default_system_prompt(ctx.config, session.cwd, session.session_id)
    return SystemPromptResponse(
        template=TEMPLATE,
        template_args={**fresh.template_args, "generation": session.agent_idx + 1},
    )


# ---------------------------------------------------------------------------
# Contract 2: compaction. Ask the model whatever you like, then describe the
# next generation. Two fields of the response are the prompt; the third is the
# system prompt you just got from ctx.system_prompt.
# ---------------------------------------------------------------------------

CRITIQUE = """Before this conversation is summarized, name one thing the harness
you are running inside did badly this session. Evidence or it did not happen.
"""


async def scheduler_compact(ctx: CompactCtx) -> CompactResponse:
    """Summarize, then spend one more pass on a harness critique.

    This is the pass crow used to run on every compaction for every user, and
    the reason it is here instead: it triples the cost of compacting, and a
    project that does not want it should not pay for it. A project that does
    want it writes twelve lines. ``ask_over_history`` is the same helper the
    default strategy uses — repaired history, one trailing user turn, streamed
    so a slow local model cannot time out.
    """
    summary = await default_compactor(ctx)

    critique, usage = await ask_over_history(ctx.llm_client, ctx.session, ctx.config, CRITIQUE)
    if ctx.logger:
        ctx.logger.info("critique pass usage: %s", usage)
    out = Path(ctx.config.config_dir) / "analysis" / f"{ctx.session.agent_id}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(critique.strip() + "\n")

    system_prompt = ctx.system_prompt(ctx)
    return CompactResponse(
        system_template=system_prompt.template,
        system_args=system_prompt.template_args,
        prompt=summary.prompt,
    )


@app.command()
def agent_run(
    config_dir: Path = typer.Option(..., "--config-dir", "-d"),
    debug: bool = typer.Option(False, "--debug"),
) -> None:
    config = Config.load(config_dir=config_dir)
    if debug:
        config.chunk_log = True

    agent = AcpAgent(
        config,
        hooks=[uv_project_hook],
        system_prompt=init_sys,
        compactor=scheduler_compact,
        compact_system_prompt=compact_sys,
    )
    asyncio.run(run_agent(agent, use_unstable_protocol=True))


if __name__ == "__main__":
    app()
