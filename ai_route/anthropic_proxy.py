"""Anthropic API proxy endpoint (/v1/messages)."""

from fastapi import APIRouter, Request

from .router import route_anthropic

router = APIRouter()


@router.post("/v1/messages")
async def messages(request: Request):
    """
    Proxy endpoint for Anthropic /v1/messages API.
    Routes through configured models with fallback.
    """
    body = await request.json()

    # Normalize headers to lowercase for consistent access
    client_headers = {k.lower(): v for k, v in request.headers.items()}

    return await route_anthropic(body, client_headers)


@router.post("/v1/messages/batches")
async def messages_batches(request: Request):
    """Batch endpoint - not supported, return error."""
    from fastapi.responses import JSONResponse
    return JSONResponse(
        {
            "type": "error",
            "error": {
                "type": "not_supported",
                "message": "Batch API is not supported by this proxy.",
            }
        },
        status_code=501,
    )
