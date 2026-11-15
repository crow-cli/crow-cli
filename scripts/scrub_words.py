"""Scrub words out of crow.db message history, preserving case.

Why this exists: provider-side content filters reject the WHOLE request, not
the offending message. Alibaba's compatible-mode endpoint answers

    400 {"error": {"code": "data_inspection_failed",
                   "message": "Input text data may contain inappropriate content."}}

and since every turn re-sends the entire session history, one uncensored
user message poisons every later turn of that session — the agent dies with a
bare `openai.BadRequestError: Error code: 400` forever after. Rewriting the
stored history is the fix; this is the rewrite.

Edit REPLACEMENTS, dry-run, then apply:

    uv --project . run python scripts/scrub_words.py --dry-run
    uv --project . run python scripts/scrub_words.py
    uv --project . run python scripts/scrub_words.py --session <session-id>
    uv --project . run python scripts/scrub_words.py --roles user,assistant

Scope: `messages.data` only, and only the roles you name (`user` by default —
what YOU typed is what trips the filter; tool output is machine text and
assistant text is already model-sanitized). `agents.system_prompt`,
`tasks.prompt` and `goals.objective` are left alone.

The substitution runs over the raw JSON text of the column, so a rewritten
row is byte-identical to the old one except for the replaced words — no
reserialization, no reformatting, no unicode re-escaping. base64 data URLs
are skipped so an image payload can never be corrupted. Every row that
changes is re-indexed into `messages_fts`, because that index stores its own
copy of the message text and would otherwise keep the old words searchable.

Matching is case-insensitive substring matching (that is what makes
"fucking" fall out of "fuck"), case is preserved on the way out, and keys are
tried longest-first so {"ass": ..., "asshole": ...} does the right thing.
Printed context is masked — the words never reach stdout, the transcript, or
the next request.
"""

import argparse
import json
import re
import sqlite3
import sys
from pathlib import Path

# Allow running as a plain script from the repo root (uv --project puts
# src/ on the path; direct python invocations may not).
_SRC = str(Path(__file__).resolve().parent.parent / "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from crow_cli.memory.messages import message_text  # noqa: E402

DB_PATH = Path.home() / ".agents" / "crow" / "crow.db"

# word -> replacement. Both sides lowercase; case is preserved on output.
REPLACEMENTS = {
}

# Whose messages to rewrite. Widen with --roles when the echo matters too.
DEFAULT_ROLES = ("user",)

# A data URL's payload is JSON-safe base64 and runs to the closing quote.
_BASE64_SPAN = re.compile(r"data:[\w.+/-]*;base64,[A-Za-z0-9+/=]+")

SNIPPET_LIMIT = 40
SNIPPET_CONTEXT = 24


def build_pattern(replacements: dict[str, str]) -> re.Pattern:
    """One case-insensitive alternation, longest key first."""
    keys = sorted((k.lower() for k in replacements), key=len, reverse=True)
    if len(set(keys)) != len(keys):
        sys.exit("REPLACEMENTS has two keys that differ only by case")
    return re.compile("|".join(re.escape(k) for k in keys), re.IGNORECASE)


def _escape_like(s: str) -> str:
    return s.replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_")


def mask(text: str, pattern: re.Pattern) -> str:
    """Blank out every match so the words never reach stdout."""
    return pattern.sub(lambda m: "*" * len(m.group(0)), text)


def scrub(text: str, pattern: re.Pattern, lookup: dict[str, str], counts: dict[str, int]) -> str:
    """Replace outside base64 spans, preserving the case pattern of each hit."""

    def repl(m: re.Match) -> str:
        word = m.group(0)
        out = lookup[word.lower()]
        counts[word.lower()] = counts.get(word.lower(), 0) + 1
        if word.isupper():
            return out.upper()
        if word[:1].isupper():
            return out[:1].upper() + out[1:]
        return out

    pieces = []
    pos = 0
    for span in _BASE64_SPAN.finditer(text):
        pieces.append(pattern.sub(repl, text[pos : span.start()]))
        pieces.append(text[span.start() : span.end()])
        pos = span.end()
    pieces.append(pattern.sub(repl, text[pos:]))
    return "".join(pieces)


def _select_sql(roles: tuple[str, ...], session: str | None, keys: list[str]) -> tuple[str, list]:
    where = [f"m.role IN ({','.join('?' * len(roles))})"]
    params: list = list(roles)
    if session:
        where.append("a.session_id = ?")
        params.append(session)
    # Case-insensitive prefilter in C, so we only json-parse candidate rows.
    likes = " OR ".join(
        "LOWER(CAST(m.data AS TEXT)) LIKE ? ESCAPE '\\'" for _ in keys
    )
    where.append(f"({likes})")
    params += [f"%{_escape_like(k)}%" for k in keys]
    sql = (
        "SELECT m.id, m.agent_id, m.role, m.fork_idx, m.data "
        "FROM messages m JOIN agents a ON a.agent_id = m.agent_id "
        f"WHERE {' AND '.join(where)} ORDER BY m.id"
    )
    return sql, params


def _reindex(conn: sqlite3.Connection, row: sqlite3.Row, new_data: str, has_fts: bool) -> None:
    """Point messages_fts at the rewritten text (it stores its own copy)."""
    if not has_fts:
        return
    conn.execute("DELETE FROM messages_fts WHERE rowid = ?", (row["id"],))
    conn.execute(
        "INSERT INTO messages_fts(rowid, agent_id, role, fork_idx, text) "
        "VALUES (?, ?, ?, ?, ?)",
        (
            row["id"],
            row["agent_id"],
            row["role"],
            row["fork_idx"],
            message_text(json.loads(new_data)),
        ),
    )


def main(argv: list[str] | None = None, replacements: dict[str, str] | None = None) -> int:
    replacements = replacements if replacements is not None else REPLACEMENTS
    if not replacements:
        sys.exit("REPLACEMENTS is empty — nothing to do")

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--db", type=Path, default=DB_PATH)
    ap.add_argument("--session", default=None, help="restrict to one session_id")
    ap.add_argument(
        "--roles",
        default=",".join(DEFAULT_ROLES),
        help="comma-separated message roles to rewrite (default: user)",
    )
    ap.add_argument("--dry-run", action="store_true", help="report, change nothing")
    args = ap.parse_args(argv)

    roles = tuple(r.strip() for r in args.roles.split(",") if r.strip())
    lookup = {k.lower(): v for k, v in replacements.items()}
    pattern = build_pattern(replacements)

    if not args.db.exists():
        sys.exit(f"Database not found: {args.db}")

    print(f"Database: {args.db}")
    print(f"Session:  {args.session or '(all)'}")
    print(f"Roles:    {', '.join(roles)}")
    print(f"Words:    {len(lookup)}")

    conn = sqlite3.connect(str(args.db), timeout=60)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 60000")
    has_fts = (
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type IN ('table','view') AND name='messages_fts'"
        ).fetchone()
        is not None
    )
    if not has_fts:
        print("note: no messages_fts table here, skipping re-index")

    sql, params = _select_sql(roles, args.session, sorted(lookup, key=len, reverse=True))
    rows = conn.execute(sql, params).fetchall()
    print(f"Scanning {len(rows)} candidate message(s)...")

    counts: dict[str, int] = {}
    changed = 0
    shown = 0
    for row in rows:
        raw = row["data"]
        if not isinstance(raw, str):
            raw = json.dumps(raw, ensure_ascii=False)
        new = scrub(raw, pattern, lookup, counts)
        if new == raw:
            continue
        changed += 1
        if shown < SNIPPET_LIMIT:
            for m in pattern.finditer(raw):
                if shown >= SNIPPET_LIMIT:
                    break
                shown += 1
                ctx = raw[max(0, m.start() - SNIPPET_CONTEXT) : m.end() + SNIPPET_CONTEXT]
                print(f"  [{row['role']}] id={row['id']}: ...{mask(ctx, pattern)}...")
        if not args.dry_run:
            conn.execute("UPDATE messages SET data = ? WHERE id = ?", (new, row["id"]))
            _reindex(conn, row, new, has_fts)

    if args.dry_run:
        conn.rollback()
    else:
        conn.commit()
    conn.close()

    if shown < sum(counts.values()):
        print(f"  ... {sum(counts.values()) - shown} more hit(s) not shown")
    for word in sorted(counts):
        print(f"  {mask(word, pattern)} -> {lookup[word]}: {counts[word]}")
    print(f"\n{'Would modify' if args.dry_run else 'Modified'} {changed} row(s).")
    if args.dry_run and changed:
        print("Run without --dry-run to apply.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
