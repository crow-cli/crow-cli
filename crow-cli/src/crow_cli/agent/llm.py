"""
LLM (Large Language Model) utilities.
"""

import httpx
from openai import AsyncOpenAI

from crow_cli.agent.configure import LLMProvider
from logging import Logger
from importlib.metadata import version





def configure_llm(
    provider: LLMProvider,
    debug: bool = False,
    logger: Logger | None = None,
) -> AsyncOpenAI:
    """
    Configure async LLM client.

    Args:
        provider: LLM provider configuration
        debug: Whether to log requests

    Returns:
        Configured AsyncOpenAI client
    """
    async def log_request(request):
        """Log HTTP requests for debugging"""
        logger.info(f"\n{'=' * 20} RAW REQUEST {'=' * 20}")
        logger.info(f"{request.method} {request.url}")
        logger.info(f"Headers: {dict(request.headers)}")
        logger.info(f"Body: {request.read().decode()}")

    api_key = provider.api_key
    base_url = provider.base_url

    if debug:
        http_client = httpx.AsyncClient(event_hooks={"request": [log_request]})
    else:
        http_client = None

    client = AsyncOpenAI(
        api_key=api_key,
        base_url=base_url,
        http_client=http_client,
        default_headers={"User-Agent": f"CrowCLI/{version('crow-cli')}"},
    )
    logger.info(f"USER-AGENT: {client.user_agent}") # =
    return client
