# RULES

- always use absolute paths
- terminals are not persistent
- never use git for any reason
- user search liberally
- always test code you write, do not assume it works

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
