"""Shades of Purple — builtin theme.

Canonical palette from Ahmad Awais' Shades of Purple:
VS Code theme (workbench colors) + Hyper theme (terminal ANSI colors).
https://github.com/ahmadawais/shades-of-purple-vscode
https://github.com/ahmadawais/shades-of-purple-hyper
"""

from rich import terminal_theme
from textual.theme import Theme

# VS Code workbench colors
PURPLE_BG = "#2D2B55"  # editor background
PURPLE_SIDEBAR = "#222244"  # sidebar / activity bar border
PURPLE_PANEL = "#1E1E3F"  # dropdown / section headers
SOP_YELLOW = "#FAD000"  # badges, buttons, cursor
SOP_PURPLE = "#B362FF"  # selection
SOP_PINK = "#FF2C70"  # magenta / invalid
SOP_GREEN = "#3AD900"
SOP_ORANGE = "#FF9D00"
SOP_RED = "#EC3A37"

SHADES_OF_PURPLE = Theme(
    name="shades-of-purple",
    primary=SOP_YELLOW,
    secondary=SOP_PURPLE,
    accent=SOP_PINK,
    foreground="#FFFFFF",
    background=PURPLE_BG,
    surface=PURPLE_SIDEBAR,
    panel=PURPLE_PANEL,
    success=SOP_GREEN,
    warning=SOP_ORANGE,
    error=SOP_RED,
    dark=True,
)

# Hyper theme ANSI colors (verbatim)
SHADES_OF_PURPLE_TERMINAL_THEME = terminal_theme.TerminalTheme(
    background=(30, 29, 64),  # #1E1D40
    foreground=(199, 199, 199),  # #C7C7C7
    normal=[
        (0, 0, 0),  # black - #000000
        (217, 4, 41),  # red - #D90429
        (58, 217, 0),  # green - #3AD900
        (250, 208, 0),  # yellow - #FAD000
        (105, 67, 255),  # blue - #6943FF
        (255, 44, 112),  # magenta - #FF2C70
        (128, 252, 255),  # cyan - #80FCFF
        (199, 199, 199),  # white - #C7C7C7
    ],
    bright=[
        (128, 128, 128),  # bright black - #808080
        (255, 0, 0),  # bright red - #FF0000
        (51, 255, 0),  # bright green - #33FF00
        (255, 255, 0),  # bright yellow - #FFFF00
        (0, 102, 255),  # bright blue - #0066FF
        (204, 0, 255),  # bright magenta - #CC00FF
        (0, 255, 255),  # bright cyan - #00FFFF
        (255, 255, 255),  # bright white - #FFFFFF
    ],
)
