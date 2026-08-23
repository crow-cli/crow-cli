"""
Agent runner entry point for PyInstaller builds.

This script is used as a separate entry point to run the agent
when the main application is frozen with PyInstaller.
"""

import asyncio
import sys
from pathlib import Path

# Add the src directory to the path so we can import crow_cli
# This is needed for PyInstaller frozen builds
if getattr(sys, "frozen", False):
    # Running in a PyInstaller bundle
    # The executable is in dist/crow-cli, and the frozen application
    # should have crow_cli module available via sys.path
    pass

from crow_cli.agent.main import main as agent_main

if __name__ == "__main__":
    agent_main()
