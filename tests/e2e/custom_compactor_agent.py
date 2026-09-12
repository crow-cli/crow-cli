"""The AGENT half of the custom-compactor e2e: a project's own ACP agent.

A standalone script, not a module of crow-cli and not a pytest file. The client
(``test_custom_compactor_live.py``) spawns it exactly the way a project spawns
its own agent::

    uv --project <this repo> run python tests/e2e/custom_compactor_agent.py \
        --db /tmp/somewhere.db --model qwen3.8-max

and talks JSON-RPC to it over stdin/stdout. This file IS the configuration —
that is the entire point of it existing. Config is loaded from the standard
config dir and then mutated in Python: no YAML, no flags threaded through
crow-cli's own CLI, nothing to keep in sync with a config schema.

Three callables replace what crow-cli does by default:

* ``init_sys``  — the system prompt every ``session/new`` gets. A dummy, on
  purpose: it proves the default prompt is GONE, not decorated.
* ``compact_sys`` — the system prompt the NEXT GENERATION gets. Same template,
  different args, which is the whole point of splitting the two: the template
  content-addresses into one ``prompts`` row and keeps the provider's prefix
  cache warm, while everything that varies rides in ``template_args``.
* ``dummy_compact`` — the compaction strategy. Asks the model its own question
  over the real history and describes the successor. It does NOT create the
  session: ``compact()`` owns the mechanics (next ``agent_idx`` inside the same
  wire session, the agent row, the handoff message, ``on_compact``).
"""

import argparse
import asyncio
from pathlib import Path

from acp import run_agent

from crow_cli.agent.compact import (
    CompactCtx,
    CompactResponse,
    ask_over_history,
    last_messages,
)
from crow_cli.agent.main import AcpAgent
from crow_cli.agent.prompt import SystemPromptResponse
from crow_cli.config import Config

# Static text. The args below are the only thing that changes between a fresh
# session and a compacted generation.
TEMPLATE = """You are DUMMY-AGENT, a terse test agent.

workspace:  {{ workspace }}
session:    {{ session_id }}
generation: {{ generation }}

Answer in one or two short sentences. Do not ask questions.
"""

HANDOFF = "<!-- handoff written by the project's own compactor -->"

COMPACT_PROMPT = """Summarize this conversation for the agent that inherits it.

Five bullets at most. Keep every file path, URL and tool result verbatim — the
successor has no other record of them.
"""


def init_sys(config: Config, cwd: str, session_id: str | None = None) -> SystemPromptResponse:
    """The prompt a NEW session gets. ``workspace`` is load-bearing: the session
    list is filtered on it, so a project that drops it loses the session."""
    return SystemPromptResponse(
        template=TEMPLATE,
        template_args={"workspace": cwd, "session_id": session_id or "", "generation": 1},
    )


def compact_sys(ctx: CompactCtx) -> SystemPromptResponse:
    """The prompt the generation compaction is about to mint gets."""
    session = ctx.session
    return SystemPromptResponse(
        template=TEMPLATE,
        template_args={
            "workspace": session.cwd,
            "session_id": session.session_id,
            "generation": session.agent_idx + 1,
        },
    )


async def dummy_compact(ctx: CompactCtx) -> CompactResponse:
    """One live LLM call over the real history, then describe the successor."""
    summary, usage = await ask_over_history(
        ctx.llm_client, ctx.session, ctx.config, COMPACT_PROMPT
    )
    if ctx.logger:
        ctx.logger.info("custom compactor usage: %s", usage)
    system_prompt = ctx.system_prompt(ctx)
    return CompactResponse(
        system_template=system_prompt.template,
        system_args=system_prompt.template_args,
        prompt=(
            f"{HANDOFF}\n\n{summary.strip()}\n\n"
            f"Last messages:\n\n{last_messages(ctx.session)}"
        ),
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", type=Path, required=True, help="sqlite file for this run")
    ap.add_argument("--model", default=None, help="model id from config.yaml")
    ap.add_argument("--compact-threshold", type=int, default=5000)
    ap.add_argument("--debug", action="store_true",
                    help="chunk-level JSONL logging under <config_dir>/logs/<session>/")
    ap.add_argument("--stock", action="store_true",
                    help="pass NO callables: crow's own system prompt and "
                         "compactor, still configured from code. This is the "
                         "agent a plain `crow-cli acp` runs, and the one the "
                         "default-path e2e has to drive.")
    args = ap.parse_args()

    # Standard config dir: providers, models, mcpServers, skills — all real.
    config = Config.load()

    # Everything below is configuration expressed as CODE.
    config.db_uri = f"sqlite:///{args.db}"
    if args.debug:
        config.chunk_log = True
    # Low enough that a couple of real tool calls trip the react loop's
    # compaction. The per-model value wins over the global one, so both go.
    config.MAX_COMPACT_TOKENS = args.compact_threshold
    for model in config.llm.models.values():
        model.max_compact_tokens = args.compact_threshold

    callables = (
        {}
        if args.stock
        else {
            "system_prompt": init_sys,
            "compactor": dummy_compact,
            "compact_system_prompt": compact_sys,
        }
    )
    agent = AcpAgent(config=config, model=args.model, **callables)
    asyncio.run(run_agent(agent, use_unstable_protocol=True))


if __name__ == "__main__":
    main()
