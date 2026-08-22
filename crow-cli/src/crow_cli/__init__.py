"""crow_cli — the Crow agent CLI.

AcpAgent resolves lazily (PEP 562) so importing any leaf module (e.g. the
MCP memory telemetry facade) doesn't pay for the whole agent stack.
"""

__all__ = ["AcpAgent"]


def __getattr__(name):
    if name == "AcpAgent":
        from crow_cli.agent import AcpAgent

        return AcpAgent
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
