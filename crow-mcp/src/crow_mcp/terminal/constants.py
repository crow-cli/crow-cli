"""Terminal constants and configuration."""

import re

# PS1 metadata markers
CMD_OUTPUT_PS1_BEGIN = "\n###PS1JSON###\n"
CMD_OUTPUT_PS1_END = "\n###PS1END###"

# Regex to match PS1 metadata blocks
CMD_OUTPUT_METADATA_PS1_REGEX = re.compile(
    rf"^{CMD_OUTPUT_PS1_BEGIN.strip()}((?:(?!{CMD_OUTPUT_PS1_BEGIN.strip()}).)*?){CMD_OUTPUT_PS1_END.strip()}",
    re.DOTALL | re.MULTILINE,
)

# Default max size for command output
MAX_CMD_OUTPUT_SIZE: int = 30000

# How long to wait with no new output before asking user
NO_CHANGE_TIMEOUT_SECONDS = 30

# How often to poll for new output
POLL_INTERVAL = 0.5

# Maximum history lines to keep
HISTORY_LIMIT = 10_000

# Timeout message template
TIMEOUT_MESSAGE_TEMPLATE = (
    "The command is still running. You can:\n"
    "- Send empty command '' to continue waiting\n"
    '- Send "C-c" to interrupt\n'
    "- Use a longer timeout parameter\n"
)
