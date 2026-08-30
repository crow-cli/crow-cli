# TODO

## **DO NOT ASK USER FOR FEEDBACK — THIS IS THE USER FEEDBACK.**
## **DO NOT ASK USER FOR NEXT STEPS — THESE ARE THE NEXT STEPS.**

Prior sprint (toad absorption polish: attribution sweep, TOML agent store,
sqlite consolidation, v5→v6 migration) is COMPLETE — see git history
(phases landed 2026-08-29, gate 498 green).

## Items (unordered)

- [ ] Migrate the TUI's ACP client off the hand-rolled stack. `tui/jsonrpc.py`
      + `tui/acp/` are toad legacy: own Request/MethodCall futures, own
      dispatch loop, own subprocess plumbing — while `client/` (main.py,
      subagent.py) already speaks ACP through the official `acp` SDK
      (ClientSideConnection, concurrent dispatch, protocol-correct
      notification semantics). Rolled-own is where bugs like the 2026-08-29
      cancel-lag fester. NOTE: the tactical fix c739dec6 did NOT resolve the
      felt lag — user confirmed live 2026-08-29 ("that turn cancellation did
      NOT work"); user's call: fix it in the full python-sdk ACP-ification,
      i.e. this item. Scope: replace tui/acp/agent.py's transport layer with
      acp.spawn_agent_process/ClientSideConnection, keep the Textual widget
      + message surface. Cancel must preempt everything (see PLAN.md).
- [ ] TUI prompt attachments: image files must upload as ACP image content,
      not text. Bug (seen live 2026-08-29, session
      mindful-beneficial-groundhog-of-blizzard): `@photo.png` in a prompt
      went over session/prompt as text. Root cause:
      `tui/prompt/resource.py::load_resource` — `mimetypes.guess_file_type`
      gives png/jpeg/webp `encoding=None`, so they hit the
      `read_text(errors="replace")` branch and become mojibake text blocks.
      Fix: mime startswith `image/` → read bytes, and `tui/acp/prompt.py::build`
      emits `{"type": "image", "data": <b64>, "mimeType": ...}` (ACP
      ImageContentBlock — agent side already consumes these, see
      agent/prompt.py). Extensions to cover at least: png jpeg jpg webp gif
      bmp ico avif. Test: unit test on build() with a tiny real png fixture.
