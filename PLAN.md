# PLAN — TUI image attachments as ACP image content

## **DO NOT ASK USER FOR FEEDBACK — THIS IS THE USER FEEDBACK.**
## **DO NOT ASK USER FOR NEXT STEPS — THESE ARE THE NEXT STEPS.**

Build/test gate: `uv --project . run pytest tests/unit tests/mcp -q` after
each step; full `./run_tests.sh tests/unit tests/memory tests/mcp
tests/integration -q` at the end. Commit when green, Session-Id trailer.

Prior sprint (toad absorption, phases 1–4) is COMPLETE — git history.

## Steps

1. `tui/prompt/resource.py::load_resource` — branch on mime BEFORE the
   read: `mime_type.startswith("image/")` → `read_bytes()` (text=None),
   same as the compressed-encoding path. Keep the octet-stream fallback
   for unknown types as-is (text read).
   - Verify: existing resource tests green + new unit cases (png → data,
     gz → data, .py → text).
2. `tui/acp/prompt.py::build` — when `resource.data is not None` and
   mime is `image/*`, emit `{"type": "image", "data": b64, "mimeType":
   mime}` instead of the resource/blob block; non-image binaries keep the
   resource blob path.
   - Verify: unit test builds a prompt with `@tiny.png` (1×1 real png
     fixture, bytes in the test) → one image block, correct b64 + mime;
     `@README.md` still a text resource; agent/prompt.py round-trips
     ImageContentBlock already (no change there).
3. Full gate + live smoke: TUI prompt with an image @-mention, confirm
   the agent describes it (vision model).
