"""crow_cli.agent — the ACP agent.

AcpAgent resolves lazily (PEP 562): importing a leaf module of this package
(session, react, logger, ...) must not drag in agent.main, which closes the
config -> agent.logger -> agent.main -> compact -> config import circle.
"""

__all__ = ["AcpAgent"]


def __getattr__(name):
    if name == "AcpAgent":
        from crow_cli.agent.main import AcpAgent

        return AcpAgent
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
