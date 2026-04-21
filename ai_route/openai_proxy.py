"""OpenAI API proxy endpoints (/v1/chat/completions, /v1/models)."""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from .config import load_settings
from .router import route_openai

router = APIRouter()


@router.post("/v1/chat/completions")
async def chat_completions(request: Request):
    """
    Proxy endpoint for OpenAI /v1/chat/completions API.
    Routes through configured models with fallback.
    """
    body = await request.json()

    # Normalize headers to lowercase for consistent access
    client_headers = {k.lower(): v for k, v in request.headers.items()}

    return await route_openai(body, client_headers)


@router.get("/v1/models")
async def list_models():
    """
    Return list of configured enabled models.
    Compatible with OpenAI /v1/models endpoint format.
    """
    settings = load_settings()

    models_data = []
    for model in settings.models:
        if model.enabled:
            models_data.append({
                "id": model.name,
                "object": "model",
                "created": 0,
                "owned_by": "ai-route-proxy",
            })

    return JSONResponse({
        "object": "list",
        "data": models_data,
    })


@router.get("/v1/models/{model_id}")
async def get_model(model_id: str):
    """Get a specific model by ID."""
    settings = load_settings()

    for model in settings.models:
        if model.name == model_id and model.enabled:
            return JSONResponse({
                "id": model.name,
                "object": "model",
                "created": 0,
                "owned_by": "ai-route-proxy",
            })

    return JSONResponse(
        {
            "error": {
                "message": f"Model '{model_id}' not found or not enabled.",
                "type": "invalid_request_error",
                "code": "model_not_found",
            }
        },
        status_code=404,
    )
