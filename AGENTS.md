# RULES

- always use absolute paths
- terminals are not persistent
- user search liberally
- always test code you write, do not assume it works

# USEFUL COMMANDS

## Query My Bluesky PDS (ATProto)

When I need to fetch my posts from my self-hosted PDS:

```bash
# Fetch author feed from public API
curl -s "https://public.api.bsky.app/xrpc/app.bsky.feed.getAuthorFeed?actor=did:plc:6amf2dzllh6lvnsqxsr4nf6e&limit=100" | jq -r '.feed[] | .post | select(.author.did == "did:plc:6amf2dzllh6lvnsqxsr4nf6e") | select(.record.text != null and .record.text != "") | "[\(.record.createdAt[0:10])] \(.record.text | gsub("\n"; " ") | .[0:280])"'
```

My DID: `did:plc:6amf2dzllh6lvnsqxsr4nf6e`
My PDS: `pds.advanced-eschatonics.com`
My Handle: `advanced-eschatonics.com`

## Why Not agentskills.io?

**What Agent Skills Is:**
- Folders with `SKILL.md` files (metadata + instructions)
- Progressive disclosure: load name/desc at startup, full instructions on activation
- Bundles scripts, templates, reference materials
- Developed by Anthropic, adopted by Cursor, VS Code, Claude, etc.

**Why crow-cli Doesn't Need It:**

crow-cli already has:
- Web search (SearXNG MCP tool) → can look up how to do anything
- Terminal (curl, jq, grep, etc.) → can execute commands directly
- File tools (read, write, edit) → can create/modify scripts on the fly
- Web fetch → can pull documentation as needed

Agent Skills is for agents WITHOUT web access that need pre-packaged knowledge. But crow-cli HAS the web. So instead of:

```
my-skill/
├── SKILL.md          # "how to query ATProto PDS"
├── scripts/
└── references/
```

You just... do it:
```bash
curl -s "https://public.api.bsky.app/xrpc/app.bsky.feed.getAuthorFeed?actor=did:plc:..." | jq -r '...'
```

**The Philosophy:**

Agent Skills = "Write once, use everywhere" across multiple agent products.
crow-cli = "No frameworks. Just tools. Figure it out."

If the agent can search the web and run terminal commands, it doesn't need pre-packaged skill folders. It can just... solve the problem.

**When Agent Skills Makes Sense:**
- Enterprise agents without web access
- Need for auditable, version-controlled workflows
- Multiple agent products sharing same skills

**When It Doesn't:**
- You built your own agent with web + terminal access
- You value minimal dependencies over pre-packaged knowledge
- Your agent can figure things out on its own

# SUPER IMPORTANT RULES

## RUNNING SCRIPTS
- ALWAYS USE: `uv --project /path/to/project run /path/to/script.py`
- NEVER USE: `uv run /path/to/script.py` (missing --project flag)

## INSTALLING DEPENDENCIES
- ALWAYS USE: `uv --project /path/to/project pip install <package>`
- NEVER USE: `pip install` directly (without uv wrapper)

## CRITICAL
The --project flag is REQUIRED for both running scripts AND installing dependencies.
Missing this flag is a critical error.
NEVER IMPORT ANYWHERE BUT THE TOP OF THE FILE
NEVER rm -rf ~/.crow that will destroy all of your configs NEVER FUCKING DO THAT
ALL YOUR CONFIGS LIVE IN ~/.crow 

DO NOT FUCKING DELETE I CANNOT BELIEVE I HAVE TO SAY THIS BUT I DO BECAUSE OH MY FUCKING GOD
TREAT ANY ~/.SOMETHING DIRECTORY AS VALUABLE DATA
