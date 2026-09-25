"""The ACP v2 agent.

Not a subclass of anything. v2's runtime resolves handlers with
``getattr(target, spec.handler)`` and calls each with ONE positional argument —
the validated request model — so an agent is any object with the right method
names. v1's ``AcpAgent(acp.Agent)`` inherited an ABC whose signatures had to be
kept in step with the schema; here the schema is the only source of truth and
the methods simply match it.

    async def initialize(self, request: InitializeRequest) -> InitializeResponse
    async def new_session(self, request: NewSessionRequest) -> NewSessionResponse
    async def prompt(self, request: PromptRequest) -> PromptResponse
    async def cancel_session(self, notification: CancelSessionNotification) -> None

v2 also made the rest of the session surface mandatory. Advertising
``capabilities.session`` at all is now a promise to answer ``session/list``,
``session/resume`` and ``session/close`` — the three per-method markers v1 had
are gone, so there is no way to claim sessions and decline the lifecycle that
goes with them. ``session/fork`` stays optional behind its own marker, and crow
claims it: ``agent_idx``/``fork_idx`` is the schema's own shape, and delegation,
compaction and ``--fork`` are all forks.

``session/load`` is not in that list because it no longer exists. Resume
absorbed it: ``replayFrom: {"type": "start"}`` on ``session/resume`` asks for
the transcript, and :mod:`crow_cli.agent2.replay` supplies it.

The handlers are thin on purpose. Everything session-shaped lives in
:class:`~crow_cli.agent2.sessions.SessionRegistry`, everything turn-shaped in
:class:`~crow_cli.agent2.driver.SessionDriver`, and everything wire-shaped in
:class:`~crow_cli.agent2.emitter.Emitter`. What is left here is the protocol
contract itself: which capabilities crow advertises, which methods it answers,
and the one inversion that defines v2 —

**``prompt`` acknowledges, it does not run the turn.** v1 held
``session/prompt`` open for the whole turn and put the ``stopReason`` in the
response. v2 responds ``{}`` as soon as the prompt is accepted; the user
message, the running/idle states and the stop reason all travel as
``session/update`` notifications. That is not bookkeeping — it is what makes a
wake indistinguishable from a prompt, and therefore what makes background work
possible at all.
"""

from __future__ import annotations

import base64
import json
import logging
import os
from importlib.metadata import version
from typing import Any, Optional

from acp.exceptions import RequestError
from acp.experimental.v2 import schema as v2
from acp.experimental.v2.meta import PROTOCOL_VERSION

from crow_cli.agent.hooks import CommandHook, uv_project_hook
from crow_cli.agent.logger import setup_logger
# The first-run onboarding text, shown when no provider is configured. It lives
# in v1's agent module today and moves here when v1 is deleted; importing it
# beats a second copy of a 1KB user-facing string that would drift.
from crow_cli.agent.main import SETUP_MESSAGE as _SETUP_MESSAGE
from crow_cli.agent.prompt import SystemPromptFactory
from crow_cli.agent.slash import _SLASH_COMMANDS, parse_slash_command
from crow_cli.config import Config, get_default_config_dir
from crow_cli.memory import wire_session_id

# Imported for its side effect: the decorator registers /goal in the shared
# command table THIS process reads. It lives in agent2 rather than in
# agent/slash.py with the other four because v1 reads the same table and runs
# no continuation loop — see agent2/slash.py.
from . import slash as _v2_slash  # noqa: F401
from .driver import SessionDriver
from .events import Cancel, Prompt
from .replay import replay
from .sessions import SessionRegistry

logger = logging.getLogger(__name__)

#: How many sessions one ``session/list`` page carries. Same as v1's, so a
#: client paginating against one agent sees the same pages against the other.
PAGE_SIZE = 50


def encode_cursor(offset: Optional[int]) -> Optional[str]:
    """A page offset as an opaque token, or None for the last page."""
    if offset is None:
        return None
    return base64.b64encode(json.dumps({"offset": offset}).encode()).decode("ascii")


def decode_cursor(cursor: Optional[str]) -> int:
    """An opaque token back to an offset.

    Opaque to the CLIENT and to nothing else: base64 JSON, because that is what
    v1 emitted and the TUI's history screen already round-trips it. A cursor
    that does not decode is refused rather than treated as page zero —
    restarting the listing would hand back sessions the client has already
    rendered, and it would look like the agent's history had duplicates.
    """
    if cursor is None:
        return 0
    try:
        offset = int(json.loads(base64.b64decode(cursor)).get("offset", 0))
    except Exception as exc:
        raise RequestError.invalid_params(
            {"cursor": cursor, "details": "not a cursor this agent issued"}
        ) from exc
    return max(offset, 0)


def int_meta(meta: dict, key: str) -> Optional[int]:
    """One integer out of a request's ``_meta``, or None when absent.

    ``_meta`` is the only channel the fork anchors have: v2's
    ``ForkSessionRequest`` carries the environment and nothing else, so
    ``agentIdx``/``turnIdx``/``messageOffset``/``rlmDepth`` ride there exactly
    as they rode v1's ``_meta``. A present-but-unparsable value is refused
    rather than dropped, because silently forking at HEAD when the caller asked
    for three messages back produces a delegate that can see its own
    delegation — the infinity mirror the offset exists to prevent.
    """
    value = meta.get(key)
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise RequestError.invalid_params(
            {"_meta": {key: value}, "details": f"_meta.{key} must be an integer"}
        ) from exc


def wants_replay(replay_from: Any) -> bool:
    """Whether a resume asked for the transcript.

    ``replayFrom`` is a tagged union so a future cursor can be added without a
    new method, and ``{"type": "start"}`` is the only variant that exists. An
    unknown one degrades to no replay with a log line rather than an error: the
    spec asks receivers to fall back safely on variants they do not know, the
    session is perfectly usable without the replay, and refusing the whole
    resume would fail the part that matters over the part that does not.
    """
    if replay_from is None:
        return False
    kind = getattr(replay_from, "type", None)
    if kind != "start":
        logger.warning("replayFrom type %r not honoured — resuming without replay", kind)
        return False
    return True


class CrowAgentV2:
    """One agent process, many sessions, one connection at a time.

    Constructed once and handed to ``run_agent``; the runtime calls
    :meth:`on_connect` with the connection before any request arrives.
    """

    def __init__(
        self,
        config: Optional[Config] = None,
        *,
        hooks: Optional[list[CommandHook]] = None,
        model: Optional[str] = None,
        system_prompt: Optional[SystemPromptFactory] = None,
        compactor: Any = None,
        compact_system_prompt: Any = None,
    ) -> None:
        """
        Args:
            config: Loaded configuration; defaults to ``~/.agents/crow``.
            hooks: Command hooks run before terminal execution. None means the
                default ``[uv_project_hook]``; ``[]`` disables them.
            model: Model NAME from config.yaml's ``models:`` to force for every
                session (the ``-m`` flag). Overrides the first-in-config
                default and any session's saved model.
            system_prompt: How a NEW session's system prompt is built. Called
                once per ``session/new``, never cached, so one agent serving
                several sessions resolves each against its own cwd.
            compactor: The compaction strategy every session compacts through.
            compact_system_prompt: How the generation compaction MINTS gets its
                prompt. Separate from ``system_prompt`` because a successor is
                not a fresh session — it inherits a summary instead of a
                conversation — and a project usually wants the two to differ.
        """
        if config is None:
            config = Config.load(config_dir=get_default_config_dir())
        self.config = config
        self.log = setup_logger(config.config_dir / "logs" / "crow-cli.log",
                                name="crow-agent2")

        model_override = None
        if model is not None:
            model_override = config.llm.models.get(model)
            if model_override is None:
                valid = sorted(config.llm.models)
                raise ValueError(
                    f"model {model!r} not found in config.yaml models: {valid}"
                )

        self.sessions = SessionRegistry(
            config,
            model_override=model_override,
            hooks=(hooks if hooks is not None else [uv_project_hook]),
            system_prompt=system_prompt,
            compactor=compactor,
            compact_system_prompt=compact_system_prompt,
        )
        self._slash_view = _SlashView(self.sessions)
        self.client_capabilities: Any = None

    # -- connection --------------------------------------------------------

    def on_connect(self, conn: Any) -> None:
        """Called synchronously by the runtime, before any request.

        Not awaited and not a coroutine: ``AgentSideConnection.__init__`` does
        ``if on_connect := getattr(agent, "on_connect", None): on_connect(self)``.
        """
        self.sessions.set_conn(conn)

    # -- initialize --------------------------------------------------------

    async def initialize(self, request: v2.InitializeRequest) -> v2.InitializeResponse:
        self.client_capabilities = request.capabilities
        self.log.info(
            "initialize: client %s %s, capabilities %s",
            request.info.name, request.info.version, request.capabilities,
        )
        return v2.InitializeResponse(
            # The runtime rejects anything else: InitializationState.complete
            # compares this against PROTOCOL_VERSION and fails the connection.
            protocol_version=PROTOCOL_VERSION,
            info=v2.Implementation(
                name="crow-cli", title="crow-cli", version=version("crow-cli")
            ),
            capabilities=v2.AgentCapabilities(
                session=v2.SessionCapabilities(
                    prompt=v2.PromptCapabilities(
                        image=v2.PromptImageCapabilities(),
                        embedded_context=v2.PromptEmbeddedContextCapabilities(),
                    ),
                    # Claimed because it is true, and because leaving it out
                    # costs tools: a client that reads session.mcp as absent
                    # sends no mcpServers, and the client owns crow's tool
                    # supply, so the session comes up with zero. stdio and http
                    # are what mcp_client_for actually builds; "acp" is skipped
                    # with a warning and so is not claimed.
                    mcp=v2.McpCapabilities(
                        stdio=v2.McpStdioCapabilities(),
                        http=v2.McpHttpCapabilities(),
                    ),
                    # UNSTABLE, and gated on this marker. Crow's whole
                    # delegation story is forks — agent_idx/fork_idx, rlm,
                    # --fork, compaction — so not claiming it would hide the
                    # one thing crow does that a stock agent does not.
                    fork=v2.SessionForkCapabilities(),
                    # delete and additionalDirectories are NOT claimed: crow has
                    # no session deletion and no additional-root model, and an
                    # unclaimed marker is how a client learns not to ask.
                ),
            ),
            # auth_methods deliberately omitted. v2 requires an agent that
            # advertises ANY auth method to implement both auth/login and
            # auth/logout, and crow needs neither — providers are configured in
            # config.yaml. v1 advertised a terminal-auth hint for `crow-cli
            # auth` through field_meta; v2's TerminalAuthMethod has no command
            # field to put it in, so it waits for a spec answer rather than
            # being smuggled through _meta.
        )

    # -- sessions ----------------------------------------------------------

    async def new_session(self, request: v2.NewSessionRequest) -> v2.NewSessionResponse:
        self.log.info("new_session in cwd %s", request.cwd)
        self._warn_additional("new", request.additional_directories)
        session = await self.sessions.create(request.cwd, request.mcp_servers)
        session_id = wire_session_id(session.agent_id)
        await self.sessions.driver_for(session, slash=self._slash)
        await self._advertise_commands(session_id)
        return v2.NewSessionResponse(
            session_id=session_id,
            config_options=self.sessions.config_options(session_id),
        )

    async def _advertise_commands(self, session_id: str) -> None:
        emitter = self.sessions.emitter_for(session_id)
        await emitter.available_commands(
            [
                v2.AvailableCommand(
                    name=cmd["name"],
                    description=cmd["description"],
                    input=v2.TextAvailableCommandInput(hint="[args]"),
                )
                for cmd in _SLASH_COMMANDS
            ]
        )

    def _warn_additional(self, session_id: str, directories: Optional[list]) -> None:
        """crow has no additional-root model, and does not advertise one.

        ``session.additionalDirectories`` is off in ``initialize``, so a
        compliant client never sends these. One that does gets a log line and an
        agent that keeps working in ``cwd`` alone. Refusing the whole session
        over a field the client was told we ignore would be worse, and
        half-honouring it — widening the prompt's notion of the workspace
        without widening anything that enforces it — would be worse still.
        """
        if directories:
            self.log.warning(
                "session %s: additionalDirectories %s ignored — crow has no "
                "additional-root model and does not advertise the capability",
                session_id, directories,
            )

    # -- listing -----------------------------------------------------------

    async def list_sessions(
        self, request: v2.ListSessionsRequest
    ) -> v2.ListSessionsResponse:
        """One page of the sessions this agent's store knows, newest first.

        ``cwd`` is a FILTER and optional, so omitting it lists every session
        rather than none — v1 returned an empty page for a missing cwd, which
        made "what sessions exist" unanswerable over the protocol and forced
        every client to already know the directory it was asking about.

        Absolutised before it reaches the query because that is how it was
        stored (``make_agent_session`` runs ``abspath``): a client's bare ``.``
        would otherwise match nothing and look like an empty history.
        """
        cwd = os.path.abspath(request.cwd) if request.cwd else None
        offset = decode_cursor(request.cursor)
        infos, next_offset = self.sessions.session_infos(cwd, PAGE_SIZE, offset)
        self.log.info(
            "list_sessions cwd=%s offset=%d -> %d session(s), next=%s",
            cwd, offset, len(infos), next_offset,
        )
        return v2.ListSessionsResponse(
            sessions=[v2.SessionInfo(**info) for info in infos],
            next_cursor=encode_cursor(next_offset),
        )

    # -- resume / close / fork ---------------------------------------------

    async def resume_session(
        self, request: v2.ResumeSessionRequest
    ) -> v2.ResumeSessionResponse:
        """Re-attach to a session, replaying its history when asked.

        This is ``session/load``'s job too — v2 deleted that method and gave
        resume a ``replayFrom`` cursor — so the two cases share one handler and
        differ only in whether :func:`~crow_cli.agent2.replay.replay` runs.

        The order is not free. Commands, then replay, then the driver: the
        driver's first act with nothing to do is park, and parking emits an
        idle, so starting it before the replay would put "ready for a new
        prompt" on the wire ahead of the transcript it refers to. A client
        drives its input box from that idle.

        ``mcpServers`` is honoured only for a session this process does not
        already hold, which is the case resume exists for. Re-provisioning a
        LIVE session would swap the registry's tool list under a driver whose
        ``DriverDeps.tools`` was captured when it was built, so the new servers
        would be connected and then ignored — a client wanting different tools
        closes the session and resumes it.
        """
        session_id = request.session_id
        session = await self.sessions.resolve(session_id)
        if session is None:
            self.log.error("resume for unknown session %s", session_id)
            raise RequestError.invalid_params(
                {"sessionId": session_id, "details": "unknown session"}
            )
        self._warn_additional(session_id, request.additional_directories)
        cwd = os.path.abspath(request.cwd)
        live = session_id in self.sessions.tools
        if live:
            self.log.info(
                "resume: session %s is already live here — keeping the tool "
                "supply it came up with", session_id,
            )
        await self.sessions.provision(session, request.mcp_servers)
        await self._advertise_commands(session_id)
        if wants_replay(request.replay_from):
            await replay(
                self.sessions.emitter_for(session_id),
                session.messages,
                cwd,
                self.sessions.logger_for(session_id),
            )
        await self.sessions.driver_for(session, slash=self._slash)
        return v2.ResumeSessionResponse(
            config_options=self.sessions.config_options(session_id)
        )

    async def close_session(
        self, request: v2.CloseSessionRequest
    ) -> v2.CloseSessionResponse:
        """Cancel anything in flight, free the session, answer.

        The spec's wording is to treat the ongoing work as if
        ``session/cancel`` had been called and then release the resources; the
        cancel is inside ``driver.stop()``. What does NOT follow is the idle
        ``state_update`` a real cancel is answered with. ``session/cancel`` is a
        notification, so that idle is the only channel it has to confirm
        anything; ``session/close`` is a request, and its response is the
        confirmation. Emitting a cancelled idle afterwards would be a state
        change on a session that no longer exists.

        A session this process never held is not an error — it may be live in
        another agent over the same store, or may simply never have been
        prompted — but a session that does not exist ANYWHERE is, and is
        refused the same way ``prompt`` refuses one.
        """
        session_id = request.session_id
        if not self.sessions.known(session_id):
            self.log.error("close for unknown session %s", session_id)
            raise RequestError.invalid_params(
                {"sessionId": session_id, "details": "unknown session"}
            )
        await self.sessions.close_session(session_id)
        return v2.CloseSessionResponse()

    async def fork_session(
        self, request: v2.ForkSessionRequest
    ) -> v2.ForkSessionResponse:
        """A branch of a session's history under its own wire id.

        The fork's id is its agent id, not the source's session id — that is
        what makes a fork addressable, and what lets a delegate's transcript be
        read back with no handshake.

        A failure to fork is ``invalid_params`` and not an internal error: every
        way :meth:`SessionRegistry.fork` can fail is a property of the request —
        an unknown session, an ``agentIdx`` that does not exist, a
        ``messageOffset`` that steps back past everything. The message carries
        the reason because "cannot fork" on its own is not actionable.
        """
        meta = request.field_meta or {}
        self.log.info(
            "fork_session %s cwd=%s agentIdx=%s turnIdx=%s messageOffset=%s rlmDepth=%s",
            request.session_id, request.cwd, meta.get("agentIdx"), meta.get("turnIdx"),
            meta.get("messageOffset"), meta.get("rlmDepth"),
        )
        try:
            forked = await self.sessions.fork(
                request.session_id,
                os.path.abspath(request.cwd),
                request.mcp_servers,
                agent_idx=int_meta(meta, "agentIdx"),
                turn_idx=int_meta(meta, "turnIdx"),
                message_offset=int_meta(meta, "messageOffset"),
                rlm_depth=int_meta(meta, "rlmDepth"),
            )
        except RequestError:
            raise
        except Exception as exc:
            self.log.error("fork of %s failed: %s", request.session_id, exc)
            raise RequestError.invalid_params(
                {
                    "sessionId": request.session_id,
                    "details": f"cannot fork: {exc}",
                }
            ) from exc
        fork_id = wire_session_id(forked.agent_id)
        self._warn_additional(fork_id, request.additional_directories)
        await self._advertise_commands(fork_id)
        await self.sessions.driver_for(forked, slash=self._slash)
        return v2.ForkSessionResponse(
            session_id=fork_id,
            config_options=self.sessions.config_options(fork_id),
        )

    # -- config options ----------------------------------------------------

    async def set_config_option(self, request: Any) -> v2.SetSessionConfigOptionResponse:
        """One option changed; the FULL array comes back.

        The request is a union discriminated on ``type`` — ``id`` for a
        select's value, ``boolean``, and an open variant for anything a future
        spec adds — so this is written against the fields all three share
        rather than against one of them.

        An unknown ``configId`` is refused rather than stored. The array this
        agent sent is the only place a client can have learned an id from, so
        one that is not in it is a bug worth naming; v1 stored it quietly and
        the client was left showing an option that had no effect on anything.

        No ``config_option_update`` is emitted: that notification is for changes
        the AGENT makes on its own initiative, and this one was requested. The
        response carries the array, and it carries all of it because the spec is
        explicit that one change can affect other options.
        """
        session_id = request.session_id
        config_id = request.config_id
        session = await self.sessions.resolve(session_id)
        if session is None:
            self.log.error("set_config_option for unknown session %s", session_id)
            raise RequestError.invalid_params(
                {"sessionId": session_id, "details": "unknown session"}
            )
        if config_id == "model":
            if not isinstance(request.value, str):
                raise RequestError.invalid_params(
                    {
                        "sessionId": session_id,
                        "configId": config_id,
                        "details": "the model option takes a string value",
                    }
                )
            self.log.info(
                "set_config_option: session %s model -> %s", session_id, request.value
            )
            # persist=True: this is the client's choice about the session, not
            # a process-local default, so it outlives this process. See
            # SessionRegistry.apply_model_option for what the flag buys and why
            # nothing else sets it.
            self.sessions.apply_model_option(
                session_id, request.value, session, persist=True
            )
        else:
            known = [o.config_id for o in self.sessions.config_options(session_id)]
            self.log.warning(
                "set_config_option: session %s, unknown option %r (have %s)",
                session_id, config_id, known,
            )
            raise RequestError.invalid_params(
                {
                    "sessionId": session_id,
                    "configId": config_id,
                    "known": known,
                    "details": "unknown config option",
                }
            )
        return v2.SetSessionConfigOptionResponse(
            config_options=self.sessions.config_options(session_id)
        )

    # -- prompt ------------------------------------------------------------

    async def prompt(self, request: v2.PromptRequest) -> v2.PromptResponse:
        """Accept a prompt and return. The turn runs on the driver's task.

        Returning ``{}`` immediately is the whole point of the v2 lifecycle:
        the client learns what happened from ``state_update``, so a wake, a
        queued prompt and a fresh one are the same thing by the time they
        reach the loop.
        """
        session_id = request.session_id
        # Resolve before anything is minted for the id. A logger writes a file
        # and an emitter takes a dict slot, so validating after them would let
        # a client litter the log directory with a prompt for a session that
        # never existed.
        session = await self.sessions.resolve(session_id)
        if session is None:
            self.log.error("no session found for session_id=%s", session_id)
            # v1 could answer with stop_reason="error"; v2's prompt response is
            # empty, so a JSON-RPC error is the only channel left. Better than
            # a clean acknowledgement: a client that thinks the turn started
            # will wait forever for an idle that never comes.
            raise RequestError.invalid_params(
                {"sessionId": session_id, "details": "unknown session"}
            )

        if not self.config.is_configured:
            # First run, no provider. Say so and go idle — a turn cannot run.
            emitter = self.sessions.emitter_for(session_id)
            await emitter.agent_message(
                emitter.start_message(), [v2.TextContentBlock(text=_SETUP_MESSAGE)]
            )
            await emitter.idle(stop_reason="end_turn")
            return v2.PromptResponse()

        self.sessions.logger_for(session_id).info("prompt accepted for session %s", session_id)
        driver = await self.sessions.driver_for(session, slash=self._slash)
        driver.submit(Prompt(blocks=request.prompt))
        return v2.PromptResponse()

    async def _slash(self, session: Any, text: str) -> Optional[str]:
        """Dispatch a slash command. None means "not a command — run a turn".

        The driver calls this before starting a turn, so the distinction
        matters: a message that merely starts with ``/`` (a path, say) has to
        fall through to the model rather than be swallowed.
        """
        parsed = parse_slash_command(text)
        if not parsed:
            return None
        name, args = parsed
        for cmd in _SLASH_COMMANDS:
            if cmd["name"] == name:
                return await cmd["func"](session, args, self._slash_view)
        return f"Unknown command: /{name}. Type /help for available commands."

    async def cancel_session(self, notification: v2.CancelSessionNotification) -> None:
        """Cancel the foreground work. The driver confirms via idle state.

        A notification, so there is nothing to return: per the spec the agent
        finishes sending pending updates and then emits an idle ``state_update``
        with ``stopReason: "cancelled"``. Submitting the event as well as
        cancelling the task covers a cancel that lands between turns, where
        there is no task to cancel but queued prompts must still be dropped.
        """
        session_id = notification.session_id
        log = self.sessions.logger_for(session_id)
        driver = self.sessions.drivers.get(session_id)
        if driver is None:
            log.warning("cancel for unknown session %s", session_id)
            return
        log.info("cancel requested for session %s", session_id)
        driver.cancel()
        driver.submit(Cancel())

    # -- extensions --------------------------------------------------------
    #
    # There is deliberately NO ``handle_extension_request``. crow has no
    # ``_``-prefixed surface of its own, and ``MethodRouter._handle_extension``
    # raises ``method_not_found`` when the handler attribute is missing — the
    # identical reply an explicit stub would give, which is the same reason
    # ``client2`` deleted v1's ``method_not_found`` stubs rather than porting
    # them. What sat here instead returned ``{}``: a client that asked for
    # ``_vendor/anything`` got a JSON-RPC SUCCESS back and had no way to learn
    # the agent had done nothing. Every unimplemented protocol method answers
    # ``-32601``; an extension is a method too.
    #
    # The notification hook stays because absence is NOT equivalent there. A
    # notification has no reply, so the router swallows an unhandled one
    # silently and this log line is the only trace an unexpected one leaves.

    async def handle_extension_notification(self, method: str, params: Any) -> None:
        self.log.info("extension notification: %s %s", method, params)

    # -- teardown ----------------------------------------------------------

    async def cleanup(self) -> None:
        """Stop every driver and release every MCP client."""
        await self.sessions.close()


class _SlashView:
    """The attribute surface v1's slash handlers read, backed by the registry.

    ``agent/slash.py`` reaches into ``AcpAgent`` privates — ``_config``,
    ``_config_values``, ``_sessions``, ``_logger_for``, ``_prompt_tasks``.
    Forking the command table to suit v2 would mean two ``/compact``
    implementations to keep in step, so the handlers get this instead. It is a
    view, not a copy: every attribute resolves live, so ``/compact`` writing a
    new agent row lands in the same dict the driver reads.
    """

    def __init__(self, registry: SessionRegistry) -> None:
        self._r = registry

    @property
    def _config(self) -> Config:
        return self._r.config

    @property
    def _config_values(self) -> dict:
        return self._r.config_values

    @property
    def _sessions(self) -> dict:
        return self._r.sessions

    @property
    def _compactor(self) -> Any:
        return self._r.compactor

    @property
    def _compact_system_prompt(self) -> Any:
        return self._r.compact_system_prompt

    def _logger_for(self, session_id: str) -> Any:
        return self._r.logger_for(session_id)

    def _default_model_value(self) -> str:
        return self._r.default_model_value()

    @property
    def _engine(self) -> Any:
        """The registry's long-lived write engine, or None with no ``db_uri``.

        ``/goal`` is the only handler that asks for it — the others work on the
        in-memory session or on config. It is the SAME engine the driver
        settles goals through, which is the point: the status a person writes
        has to be the one the driver reads at the idle transition, and two
        engines on one file would only be a way to get a stale read.
        """
        return self._r.engine

    @property
    def _prompt_tasks(self) -> "_Stoppable":
        return _Stoppable(self._r)


class _Stoppable:
    """``_prompt_tasks`` for v1's ``/stop``: session id -> something cancellable.

    v1 held the prompt's ``asyncio.Task`` here and called ``.cancel()`` on it.
    v2's equivalent is the driver, whose ``cancel()`` kills the in-flight turn
    and keeps the session alive — which is what ``/stop`` always meant to do,
    and what ``session/cancel`` now does properly.
    """

    def __init__(self, registry: SessionRegistry) -> None:
        self._r = registry

    def get(self, session_id: str, default: Any = None) -> Any:
        return self._r.drivers.get(session_id, default)
