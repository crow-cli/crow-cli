"""
Compaction - summarize conversation history to reduce context window.

Simplified approach:
1. Find unexecuted tool calls (tool_call_ids with no matching tool response)
2. Append fake "tool call failed - reason: compaction" for each
3. Append compaction prompt to the message history
4. Send to LLM with tool_choice="none"
5. Create new agent record with same session_id, incremented agent_idx
6. Insert compacted messages (system + summary) under new agent
7. Old agent and its messages remain untouched - full history preserved

Nothing is ever deleted.

Compaction is also the one moment when the whole session is in front of the
model at once, so it is the natural place to ask for more than a summary. Two
extra passes run over the SAME history with a different trailing prompt (see
``write_reflections``): a harness-level analysis, written globally, and
project-level ideas, written into the working tree. All three passes send a
byte-identical message prefix, which is what makes the provider's prompt-prefix
cache pay for passes two and three.
"""

from logging import Logger
from pathlib import Path

from openai import AsyncOpenAI

from crow_cli.config import Config, sampling_params_for
from crow_cli.memory import build_agent_id, now_iso
from crow_cli.agent.session import (
    AgentSession,
    make_agent_session,
)

# Where project-scoped crow state lives inside a working tree. Mirrors
# cli/source.py's PROJECT_SCOPE; duplicated rather than imported so the agent
# core does not depend on the CLI package.
PROJECT_SCOPE = Path(".agents") / "crow"

MAX_OUTPUT_TOKENS = 30000

COMPACTION_PROMPT = """Please summarize the entire conversation up to this point.
Include:
- What the user asked for
- What you attempted and the results
- What files were created/modified
- Current state of the work
- Any errors encountered
- What still needs to be done

Be thorough and detailed. This summary will replace the conversation history, so include everything a new agent would need to continue the work seamlessly.
"""


ANALYSIS_PROMPT = """You are about to be compacted: this conversation is ending and a fresh agent will pick it up from a summary. Before that happens, do the one thing the summary will not do — critique the HARNESS you are running inside.

The harness is crow-cli itself: the system prompt you were given, the tools you were handed and the names, descriptions and schemas they came with, the skills catalog, the execute REPL kernel and its ambient subtools, compaction and context management, the memory database and the tools that read it, config resolution, permission prompts and sandboxing, subagent and delegation plumbing, the ACP wire, and the way all of it renders in the user's terminal.

The harness is NOT the project in the working directory. Draw that line hard, because blurring it is the single most common way this report goes wrong.
  - HARNESS: "the edit tool's fuzzy matching silently picked the wrong occurrence and I did not notice until the tests failed."
  - PROJECT: "this repo's test suite takes four minutes to run."
Only the first kind belongs here. If you catch yourself writing about the code you were asked to write, stop and delete it.

You are the only observer of this harness who has actually been inside it for a whole session. The people who build it see the code; you see the experience. Be adversarial about your own equipment. Assume the friction you quietly worked around is a defect worth reporting, precisely because you worked around it and never mentioned it.

Write four sections, in this order, as markdown:

## What worked well
Tools, prompt rules, skills or mechanisms that earned their place. Say specifically what you did with them and what that saved. Do not pad this section with politeness — an item here is a claim that the thing should stay, so it needs the same evidence as a complaint.

## What did not work
Friction. Every moment you re-read a tool result, guessed at a parameter, retried a call, worked around a limitation, or burned tokens discovering something the harness already knew. Include the things you adapted to so smoothly you almost did not notice them — those are the worst, because nobody ever reports them.

## Bugs
Concrete, reproducible defects in the harness. For each: the exact command or call you made, the exact output or error string you got, what you expected instead, and the narrowest reproduction you can offer. If you are unsure whether something is a bug, say what you are unsure of. Never file one you cannot reproduce.

## Ideas
Changes to the harness that this session made you want. Each one: what to build, which piece of evidence above motivates it, and roughly what it costs. Small and sharp beats grand and vague.

Rules for every item in every section:
- EVIDENCE IS MANDATORY. Quote the turn, name the tool, paste the error. An item with no evidence behind it gets deleted, not softened.
- Be specific enough that someone who never saw this session can act on it. "The memory tools are confusing" is worthless. "query_memory returned 20 rows and I could not tell which session each came from, so I called it three more times" is a finding.
- Do not summarize the conversation. Do not list what was built. Do not write a TODO list for the project.
- If a section is genuinely empty, write "None observed." Do not invent items to fill it.

This text is written to a file and read cold, later, by someone with no access to this conversation. It has to stand alone. You cannot call tools on this turn — everything you need is already in the history above.
"""


IDEAS_PROMPT = """You are about to be compacted: this conversation is ending and a fresh agent will pick it up from a summary. Before that happens, do the thing nobody else in this loop can do — think about the PROJECT from outside it.

The project is the repository in the working directory. Its shape is in the directory tree and the AGENTS.md rules in your system prompt; what has been happening to it is in the conversation above.

This is not a summary. It is not a report on what was done. It is not a TODO list, and it is not a restatement of the plan already in the repo — if an idea of yours is already written down somewhere in the project, it is not an idea. Say so in one line and move on.

What this is instead: a creative, adversarial review drawn from everything you know. You are a very large model with a very wide view of how other people have solved adjacent problems. The person working here sees one repository. You see the field. Spend that.

Write these sections, in this order, as markdown:

## Assumptions worth attacking
Pick the assumptions this project keeps relying on — the load-bearing ones nobody states out loud. Argue against each concretely: what breaks if it is false, what evidence from this session suggests it might be, and what you would do instead. If an assumption survives your attack, say why; that is a useful result too.

## Prior art you should steal from
Name the actual systems, projects, papers and techniques you know that already solved a problem this project is still working on. For each: what it is, the specific mechanism worth taking, what it cost them, and how it would land here. Be concrete — a real X and a real Y, not "industry best practice". Reach into your weights for this section; that is the entire point of it.

## Directions nobody has pointed at
New places this project could go that the current plan does not mention. Research directions, capabilities, architectures, audiences, entirely different products the same code could become. Include the ones that feel slightly unreasonable — this loop is good at pruning and bad at generating, so over-produce here.

## What would make this obsolete
The strongest honest argument against this project existing in its current form. What a well-funded competitor, a change in the underlying models, or a shift in how people work would do to it. What the maintainer should be worried about and is not.

## Cheapest decisive experiments
For the open questions this session exposed, the smallest piece of work that would actually settle them. Each: the question, the experiment, roughly what it costs, and what result would mean stop.

Rules:
- Rank by expected value inside each section. Best first.
- Quality over quantity. Five ideas that change the direction of the project beat twenty that do not. Cap yourself at about seven per section and stop when you run out of real ones.
- Every idea must say what would prove it WRONG. An idea with no failure condition is a vibe, not an idea.
- Ground each idea in something from this session or this repository where you can. An idea that could apply to any project anywhere is worth less than one that could only apply here.
- Do not summarize the work. Do not flatter the project. Do not hedge.

This text is written to a file under the project's .agents/crow/ideas/ directory and read cold, later, by someone with no access to this conversation. It has to stand alone. You cannot call tools on this turn — everything you need is already in the history above.
"""


def _fill_missing_tool_responses(messages: list[dict]) -> list[dict]:
    """
    Only checks the LAST assistant message for dangling tool calls.
    All prior turns already have their tool responses.
    """
    # Walk backwards to find the last assistant message with tool_calls
    for i in range(len(messages) - 1, -1, -1):
        msg = messages[i]
        if msg.get("role") == "assistant" and "tool_calls" in msg:
            call_ids = {
                tc.get("id") if isinstance(tc, dict) else getattr(tc, "id", None)
                for tc in msg["tool_calls"]
            }
            # Scan trailing tool responses for matching IDs
            response_ids = set()
            for j in range(i + 1, len(messages)):
                if messages[j].get("role") == "tool":
                    tcid = messages[j].get("tool_call_id")
                    if tcid:
                        response_ids.add(tcid)

            missing = call_ids - response_ids
            if not missing:
                return list(messages)  # All responded, return as-is

            result = list(messages)
            for tool_call_id in sorted(missing):
                result.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call_id,
                        "content": "Tool call was interrupted due to context compaction. Please retry if still needed.",
                    }
                )
            return result

    return list(messages)  # No tool calls found at all


def _history_prefix(session: AgentSession) -> list[dict]:
    """The session's messages, made safe to append one more user turn to.

    Two repairs, needed by every pass that ends in a user message: dangling
    tool calls on the last assistant turn get a synthetic response (providers
    reject an unanswered tool_call), and a trailing user message gets a
    lightweight assistant placeholder (providers reject user+user).

    Returns a FRESH list, rebuilt from the session each call, so every pass
    sends byte-identical bytes up to its own trailing prompt. That is what
    makes the provider's prompt-prefix cache hit on the second and third pass.
    """
    messages = _fill_missing_tool_responses(session.messages)
    if messages and messages[-1].get("role") == "user":
        messages.append(
            {
                "role": "assistant",
                "content": "Ready to compact. Calling no tools.",
            }
        )
    return messages


async def _stream_completion(
    llm: AsyncOpenAI,
    session: AgentSession,
    messages: list[dict],
    config: Config,
) -> tuple[str, dict]:
    """Send ``messages`` over a streamed request and accumulate the text.

    Streaming matters for slow (local) models: a non-streaming request has to
    generate the whole answer before the client's read timeout fires, while a
    streamed one only has to produce *a* chunk inside the timeout window.

    Returns the text and a usage dict — usage arrives on the final, choice-less
    chunk when ``include_usage`` is set, and some providers omit it.
    """
    stream = await llm.chat.completions.create(
        model=session.model_identifier,
        messages=messages,
        tools=session.tools if session.tools else None,
        tool_choice="none",
        max_tokens=MAX_OUTPUT_TOKENS,
        stream=True,
        stream_options={"include_usage": True},
        **sampling_params_for(config, session.model_identifier),
    )

    parts: list[str] = []
    usage = {
        "prompt_tokens": None,
        "completion_tokens": None,
        "total_tokens": None,
    }
    async for chunk in stream:
        if chunk.choices and chunk.choices[0].delta.content:
            parts.append(chunk.choices[0].delta.content)
        if chunk.usage:
            usage = {
                "prompt_tokens": getattr(chunk.usage, "prompt_tokens", None),
                "completion_tokens": getattr(chunk.usage, "completion_tokens", None),
                "total_tokens": getattr(chunk.usage, "total_tokens", None),
            }

    return "".join(parts), usage


async def _ask_over_history(
    llm: AsyncOpenAI,
    session: AgentSession,
    config: Config,
    prompt: str,
) -> tuple[str, dict]:
    """Ask ``prompt`` of the session's full history and stream the answer.

    The one function every compaction-time pass goes through: same history,
    same request shape, same sampling rule — only the trailing user message
    differs.
    """
    messages = _history_prefix(session)
    messages.append({"role": "user", "content": prompt})
    return await _stream_completion(llm, session, messages, config)


def analysis_path(config_dir: Path | str, agent_id: str) -> Path:
    """Where a session's harness analysis lands: ``<config_dir>/ideas/<agent>.md``.

    Global on purpose — the analysis is about crow-cli, not about the repo the
    session happened to be sitting in, so it has to survive leaving that repo.
    """
    return Path(config_dir) / "ideas" / f"{agent_id}.md"


def ideas_path(cwd: Path | str, agent_id: str) -> Path:
    """Where a session's project ideas land: ``<cwd>/.agents/crow/ideas/<agent>.md``.

    Project-local on purpose — these are ideas for THIS repository and belong
    in its working tree, where they get committed alongside the code they are
    about.
    """
    return Path(cwd) / PROJECT_SCOPE / "ideas" / f"{agent_id}.md"


def _note_header(kind: str, session: AgentSession) -> str:
    """Provenance for a reflection file, written by code rather than asked of
    the model — a frontmatter block the model has to reproduce is a frontmatter
    block the model gets subtly wrong."""
    return (
        "---\n"
        f"kind: {kind}\n"
        f"session: {session.session_id}\n"
        f"agent: {session.agent_id}\n"
        f"model: {session.model_identifier or ''}\n"
        f"cwd: {session.cwd}\n"
        f"generated: {now_iso()}\n"
        "---\n\n"
    )


async def write_reflections(
    session: AgentSession,
    llm: AsyncOpenAI,
    config: Config,
    logger: Logger = None,
) -> dict[str, Path | None]:
    """Run the analysis and ideas passes over ``session`` and write each out.

    Called at the end of ``compact()`` on the session being compacted — its
    history is the material and its ``agent_id`` names the files, so a reader
    can join either note back to the exact generation that produced it.

    Never raises. By the time this runs the summary is written and the new
    agent row is in the database; losing a critique to a provider timeout must
    not cost the user their compaction. Each pass fails alone and is logged.
    """
    analysis = analysis_path(config.config_dir, session.agent_id)
    ideas = ideas_path(session.cwd, session.agent_id)
    if analysis == ideas:
        # cwd is $HOME (or otherwise the config dir's parent), so the project
        # scope and the global scope are the same directory and both notes
        # would land on one file. The global note keeps the designed name; the
        # project note takes a suffixed one rather than silently clobbering it.
        ideas = ideas.with_name(f"{session.agent_id}-project.md")
    passes = (
        ("analysis", ANALYSIS_PROMPT, analysis),
        ("ideas", IDEAS_PROMPT, ideas),
    )
    written: dict[str, Path | None] = {}
    for kind, prompt, path in passes:
        try:
            text, usage = await _ask_over_history(llm, session, config, prompt)
        except Exception:
            written[kind] = None
            if logger:
                logger.warning(f"Compaction {kind} pass failed", exc_info=True)
            continue
        if not text.strip():
            written[kind] = None
            if logger:
                logger.warning(f"Compaction {kind} pass returned no text")
            continue
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(_note_header(kind, session) + text.strip() + "\n")
        except OSError:
            written[kind] = None
            if logger:
                logger.warning(f"Could not write {kind} to {path}", exc_info=True)
            continue
        written[kind] = path
        if logger:
            logger.info(f"Compaction {kind} written to {path} (usage: {usage})")
    return written


async def compact(
    session: AgentSession,
    llm: AsyncOpenAI,
    config: Config,
    on_compact: callable = None,
    logger: Logger = None,
) -> AgentSession:
    """
    Compact the conversation by summarizing it into a single message.

    Creates a new agent record. Old agent and messages are preserved.

    Once the summary is durable, two more passes run over the same history —
    a harness analysis and a set of project ideas, each written to its own
    markdown file (see ``write_reflections``). Those are best-effort: they
    cannot fail the compaction.

    Args:
        session: The session to compact
        llm: The LLM client for summarization
        cwd: Current working directory
        on_compact: Callback function(old_agent_id, compacted_session)
        logger: Logger instance

    Returns:
        The new session object with compacted history
    """
    original_session_id = session.session_id
    original_agent_idx = session.agent_idx

    if logger:
        logger.info(
            f"Compacting agent {session.agent_id} ({len(session.messages)} messages)..."
        )

    # 1-4. Repair the history, append the compaction prompt, and stream the
    # summary. Same per-model sampling rule as the react loop: the model's
    # reasoning_effort XOR temperature. Never the provider default (temp 1.0
    # makes the model ramble instead of compress) and never the session's
    # request_params temperature.
    #
    # Streaming is not cosmetic here: a non-streaming request must produce the
    # ENTIRE summary before the client's read timeout fires, which kills
    # compaction outright on slow local models (the summary can be tens of
    # thousands of tokens). Streamed, the timeout only applies between chunks.
    summary, usage = await _ask_over_history(llm, session, config, COMPACTION_PROMPT)
    if logger:
        logger.info(f"Compact usage: {usage}")

    # 5. Create new agent record: same session_id AND fork, next agent_idx
    new_agent_idx = original_agent_idx + 1
    new_agent_id = build_agent_id(original_session_id, new_agent_idx, session.fork_idx)
    new_session = await make_agent_session(
        config,
        session.tools,
        session.model_identifier if session.model_identifier else "",
        session.cwd,
        session_id=original_session_id,
        agent_idx=new_agent_idx,
        fork_idx=session.fork_idx,
    )

    last_msgs = last_messages(session)
    new_agent_prompt = f"{summary}\n\nLast messages:\n\n{last_msgs}"
    await new_session.add_message(
        {"role": "user", "content": new_agent_prompt},
    )

    if logger:
        logger.info(
            f"Compacted: agent {session.agent_id} -> {new_agent_id}, "
            f"{len(session.messages)} messages -> {len(new_session.messages)}"
        )

    # Callback for async task contexts
    if on_compact:
        on_compact(session.agent_id, new_session)

    # Two more passes over the same warm history: a harness-level analysis
    # (global, <config_dir>/ideas/) and project-level ideas (in the working
    # tree, <cwd>/.agents/crow/ideas/). Both are named for the generation
    # being compacted, because that is the history they read. Best-effort —
    # write_reflections logs and swallows, it never raises.
    await write_reflections(session, llm, config, logger=logger)

    return new_session


def unroll_content(content: str | list | None) -> str:
    """Flatten one message's content to text.

    ``None`` is not a defensive default here — it is the standard OpenAI shape
    for an assistant turn that did nothing but call tools, and ``add_message``
    persists whatever dict it is handed without normalizing it. Returning it
    unchanged made ``last_messages`` die on ``len(None)`` and took the whole
    compaction down with it.
    """
    if content is None:
        return ""
    if isinstance(content, list):
        new_content = [
            x.get("text", "")
            for x in content
            if isinstance(x, dict) and x.get("type") == "text"
        ]
        return " ".join(new_content)
    else:
        return content

def last_messages(session: AgentSession, n_messages: int = 20, max_chars: int = 300):
    if len(session.messages) > n_messages:
        last_msgs = session.messages[-n_messages:]
    else:
        last_msgs = session.messages
    last_msgs_list = []
    for msg in last_msgs:
        role = msg["role"]
        if role == "user":
            last_msgs_list.append("USER:")
            content = unroll_content(msg.get("content", ""))
            last_msgs_list.append(content)
        if role == "tool":
            last_msgs_list.append("TOOL RESULT:")
            content = unroll_content(msg.get("content", ""))
            new_content = content[:max_chars] if len(content) > max_chars else content
            last_msgs_list.append(new_content)
        if role == "assistant":
            last_msgs_list.append("ASSISTANT:")
            content = unroll_content(msg.get("content", ""))
            new_content = content[:max_chars] if len(content) > max_chars else content
            last_msgs_list.append(new_content)
            tool_calls = msg.get("tool_calls", [])
            for tool_call in tool_calls:
                tool_args = tool_call.get("function", {})
                name = tool_args.get("name", "")
                arguments = tool_args.get("arguments", "")
                last_msgs_list.append(f"TOOL — {name}:")
                new_args = (
                    arguments[:max_chars] if len(arguments) > max_chars else arguments
                )
                last_msgs_list.append(new_args)
    return "\n".join(last_msgs_list)
