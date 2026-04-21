"""Core fallback routing logic with first-chunk buffering for SSE."""

import asyncio
import json
from enum import Enum
from typing import AsyncIterator, Optional

import httpx
from fastapi import Response
from fastapi.responses import JSONResponse, StreamingResponse

from .config import load_settings, ModelEntry
from .state import cooldown_tracker
from .upstream import get_client, build_anthropic_headers, build_openai_headers


class Protocol(Enum):
    ANTHROPIC = "anthropic"
    OPENAI = "openai"


def _get_enabled_models() -> list[str]:
    """Get list of enabled model names in order."""
    settings = load_settings()
    return [m.name for m in settings.models if m.enabled]


def _replace_model_in_body(body: dict, model_name: str) -> dict:
    """Replace the model field in request body."""
    new_body = body.copy()
    new_body["model"] = model_name
    return new_body


def _build_upstream_url(protocol: Protocol, base_url: str) -> str:
    """Build the full upstream URL."""
    base = base_url.rstrip("/")
    if protocol == Protocol.ANTHROPIC:
        return f"{base}/v1/messages"
    else:
        return f"{base}/v1/chat/completions"


def _build_error_response(protocol: Protocol, message: str, status_code: int = 502) -> JSONResponse:
    """Build an error response in the appropriate format."""
    if protocol == Protocol.ANTHROPIC:
        return JSONResponse(
            {
                "type": "error",
                "error": {
                    "type": "api_error",
                    "message": message,
                }
            },
            status_code=status_code,
        )
    else:
        return JSONResponse(
            {
                "error": {
                    "message": message,
                    "type": "server_error",
                    "code": "upstream_unavailable",
                }
            },
            status_code=status_code,
        )


def _build_stream_error_event(protocol: Protocol, error: Exception) -> bytes:
    """Build an SSE error event for mid-stream failures."""
    error_msg = str(error)
    if protocol == Protocol.ANTHROPIC:
        event = {
            "type": "error",
            "error": {
                "type": "api_error",
                "message": f"Upstream stream interrupted: {error_msg}",
            }
        }
        return f"event: error\ndata: {json.dumps(event)}\n\n".encode()
    else:
        # OpenAI format: send [DONE] to signal end
        return b"data: [DONE]\n\n"


async def _read_first_chunk(
    byte_iter,
    timeout: float,
) -> Optional[bytes]:
    """
    Consume from given async iterator until meaningful SSE event is buffered.
    Caller MUST keep using the SAME iterator for remaining bytes.
    """
    buffer = b""
    try:
        async with asyncio.timeout(timeout):
            async for chunk in byte_iter:
                buffer += chunk
                # Check if we have at least one complete SSE event with data
                if b"data:" in buffer and b"\n\n" in buffer:
                    return buffer
                # Also accept if we have substantial content
                if len(buffer) > 100:
                    return buffer
    except asyncio.TimeoutError:
        return None
    except Exception:
        return None

    # Stream ended without meaningful content
    return buffer if buffer else None


async def _forward_stream(
    first_chunk: bytes,
    byte_iter,
    protocol: Protocol,
    model_name: str,
) -> AsyncIterator[bytes]:
    """Forward remaining bytes after buffered first chunk."""
    yield first_chunk
    try:
        async for chunk in byte_iter:
            yield chunk
    except Exception as e:
        # Mid-stream error - mark model as bad and send error event
        cooldown_tracker.mark_bad(model_name, reason=f"mid-stream: {e}")
        yield _build_stream_error_event(protocol, e)


async def _try_model_streaming(
    protocol: Protocol,
    model_name: str,
    url: str,
    body: dict,
    headers: dict,
    first_chunk_timeout: float,
) -> Optional[StreamingResponse]:
    """
    Try a single model for streaming request.
    Returns StreamingResponse if successful, None if should try next model.
    """
    client = await get_client()

    try:
        # Use stream context manager
        req = client.build_request("POST", url, json=body, headers=headers)
        response = await client.send(req, stream=True)

        # Check HTTP status
        if response.status_code >= 400:
            # Read error body for logging
            error_body = await response.aread()
            error_msg = error_body.decode("utf-8", errors="replace")[:200]
            cooldown_tracker.mark_bad(
                model_name,
                status_code=response.status_code,
                reason=error_msg,
            )
            await response.aclose()
            return None

        # Create a single byte iterator shared between first-chunk probe and forwarding
        byte_iter = response.aiter_bytes()

        # Wait for first meaningful chunk
        first_chunk = await _read_first_chunk(byte_iter, first_chunk_timeout)
        if first_chunk is None:
            cooldown_tracker.mark_bad(model_name, reason="no-first-chunk-timeout")
            await response.aclose()
            return None

        # Success! Create streaming response
        async def stream_generator():
            try:
                async for chunk in _forward_stream(first_chunk, byte_iter, protocol, model_name):
                    yield chunk
            finally:
                await response.aclose()

        # Build response headers
        resp_headers = {}
        if "content-type" in response.headers:
            resp_headers["content-type"] = response.headers["content-type"]
        else:
            resp_headers["content-type"] = "text/event-stream"

        # Forward some headers
        for h in ["x-request-id", "anthropic-ratelimit-requests-remaining"]:
            if h in response.headers:
                resp_headers[h] = response.headers[h]

        return StreamingResponse(
            stream_generator(),
            status_code=response.status_code,
            headers=resp_headers,
            media_type="text/event-stream",
        )

    except httpx.TimeoutException as e:
        cooldown_tracker.mark_bad(model_name, reason=f"timeout: {e}")
        return None
    except httpx.ConnectError as e:
        cooldown_tracker.mark_bad(model_name, reason=f"connect: {e}")
        return None
    except httpx.RemoteProtocolError as e:
        cooldown_tracker.mark_bad(model_name, reason=f"protocol: {e}")
        return None
    except Exception as e:
        cooldown_tracker.mark_bad(model_name, reason=f"error: {e}")
        return None


async def _try_model_non_streaming(
    protocol: Protocol,
    model_name: str,
    url: str,
    body: dict,
    headers: dict,
) -> Optional[Response]:
    """
    Try a single model for non-streaming request.
    Returns Response if successful, None if should try next model.
    """
    client = await get_client()

    try:
        response = await client.post(url, json=body, headers=headers)

        # Check HTTP status
        if response.status_code >= 400:
            error_msg = response.text[:200]
            cooldown_tracker.mark_bad(
                model_name,
                status_code=response.status_code,
                reason=error_msg,
            )
            return None

        # Success! Return the response
        return Response(
            content=response.content,
            status_code=response.status_code,
            headers={"content-type": response.headers.get("content-type", "application/json")},
        )

    except httpx.TimeoutException as e:
        cooldown_tracker.mark_bad(model_name, reason=f"timeout: {e}")
        return None
    except httpx.ConnectError as e:
        cooldown_tracker.mark_bad(model_name, reason=f"connect: {e}")
        return None
    except Exception as e:
        cooldown_tracker.mark_bad(model_name, reason=f"error: {e}")
        return None


async def route_request(
    protocol: Protocol,
    request_body: dict,
    client_headers: dict,
) -> Response:
    """
    Route a request through enabled models with fallback.

    Args:
        protocol: ANTHROPIC or OPENAI
        request_body: The parsed JSON request body
        client_headers: Headers from the client request (lowercased keys)

    Returns:
        Response to send to client
    """
    settings = load_settings()
    enabled_models = _get_enabled_models()

    if not enabled_models:
        return _build_error_response(
            protocol,
            "No models configured. Please configure models in the web UI.",
            status_code=503,
        )

    if not settings.upstream.base_url:
        return _build_error_response(
            protocol,
            "Upstream base_url not configured. Please configure in the web UI.",
            status_code=503,
        )

    # Determine if streaming
    is_streaming = request_body.get("stream", False)

    # Build base URL and headers
    url = _build_upstream_url(protocol, settings.upstream.base_url)
    if protocol == Protocol.ANTHROPIC:
        headers = build_anthropic_headers(settings.upstream.api_key, client_headers)
    else:
        headers = build_openai_headers(settings.upstream.api_key, client_headers)

    # Try each model in order
    tried_models = []
    for model_name in enabled_models:
        # Check cooldown
        if not cooldown_tracker.is_available(model_name):
            remaining = cooldown_tracker.get_remaining_cooldown(model_name)
            tried_models.append(f"{model_name} (cooldown {remaining:.0f}s)")
            continue

        tried_models.append(model_name)

        # Replace model in body
        body = _replace_model_in_body(request_body, model_name)

        if is_streaming:
            result = await _try_model_streaming(
                protocol,
                model_name,
                url,
                body,
                headers,
                settings.upstream.first_chunk_timeout,
            )
        else:
            result = await _try_model_non_streaming(
                protocol,
                model_name,
                url,
                body,
                headers,
            )

        if result is not None:
            return result

    # All models failed
    return _build_error_response(
        protocol,
        f"All models unavailable. Tried: {', '.join(tried_models)}",
        status_code=502,
    )


async def route_anthropic(request_body: dict, client_headers: dict) -> Response:
    """Route an Anthropic API request."""
    return await route_request(Protocol.ANTHROPIC, request_body, client_headers)


async def route_openai(request_body: dict, client_headers: dict) -> Response:
    """Route an OpenAI API request."""
    return await route_request(Protocol.OPENAI, request_body, client_headers)
