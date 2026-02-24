"""
LLM (Large Language Model) utilities.
"""

import httpx
from crow_cli.agent.config import LLMProvider
from openai import AsyncOpenAI


def log_request(request):
    """Log HTTP requests for debugging"""
    print(f"\n{'=' * 20} RAW REQUEST {'=' * 20}")
    print(f"{request.method} {request.url}")
    print(f"Headers: {dict(request.headers)}")
    print(f"Body: {request.read().decode()}")
    print(f"{'=' * 53}\n")


def configure_llm(
    provider: LLMProvider,
    debug: bool = False,
) -> AsyncOpenAI:
    """
    Configure async LLM client.

    Args:
        provider: LLM provider configuration
        debug: Whether to log requests

    Returns:
        Configured AsyncOpenAI client
    """
    api_key = provider.api_key
    base_url = provider.base_url

    if debug:
        http_client = httpx.AsyncClient(event_hooks={"request": [log_request]})
    else:
        http_client = None

    return AsyncOpenAI(
        api_key=api_key,
        base_url=base_url,
        http_client=http_client,
    )
