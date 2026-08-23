"""crow_cli — the Crow agent CLI.

AcpAgent resolves lazily (PEP 562) so importing any leaf module (e.g. the
MCP memory telemetry facade) doesn't pay for the whole agent stack.
"""

from importlib.metadata import version

__all__ = ["AcpAgent", "__version__"]

# Single source of truth: [project].version in pyproject.toml, read through
# the installed package metadata. Frozen binaries bundle that metadata via
# copy_metadata('crow-cli') in crow-cli.spec.
__version__ = version("crow-cli")


def __getattr__(name):
    if name == "AcpAgent":
        from crow_cli.agent import AcpAgent

        return AcpAgent
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
