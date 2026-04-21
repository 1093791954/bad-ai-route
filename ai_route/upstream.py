"""Upstream HTTP client management."""

from typing import Optional
import httpx

from .config import load_settings


# Global client instance (lazy init)
_client: Optional[httpx.AsyncClient] = None


async def get_client() -> httpx.AsyncClient:
    """Get or create the global async HTTP client."""
    global _client
    if _client is None or _client.is_closed:
        settings = load_settings()
        _client = httpx.AsyncClient(
            http2=False,  # HTTP/1.1 is more stable for most proxies
            timeout=httpx.Timeout(
                connect=10.0,
                read=settings.upstream.request_timeout,
                write=30.0,
                pool=10.0,
            ),
            limits=httpx.Limits(
                max_connections=100,
                max_keepalive_connections=20,
            ),
        )
    return _client


async def close_client() -> None:
    """Close the global client."""
    global _client
    if _client is not None and not _client.is_closed:
        await _client.aclose()
        _client = None


def build_anthropic_headers(api_key: str, client_headers: dict) -> dict:
    """Build headers for Anthropic API requests."""
    headers = {
        "content-type": "application/json",
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
    }

    # Forward select headers from client
    forward_headers = [
        "anthropic-beta",
        "anthropic-dangerous-direct-browser-access",
        "user-agent",
    ]
    for h in forward_headers:
        if h in client_headers:
            headers[h] = client_headers[h]

    return headers


def build_openai_headers(api_key: str, client_headers: dict) -> dict:
    """Build headers for OpenAI API requests."""
    headers = {
        "content-type": "application/json",
        "authorization": f"Bearer {api_key}",
    }

    # Forward select headers from client
    forward_headers = [
        "user-agent",
        "openai-organization",
        "openai-project",
    ]
    for h in forward_headers:
        if h in client_headers:
            headers[h] = client_headers[h]

    return headers
