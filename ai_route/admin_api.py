"""Admin API endpoints for configuration and health monitoring."""

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from .config import (
    load_settings,
    save_settings,
    mask_api_key,
    is_masked_key,
    Settings,
    UpstreamConfig,
    ModelEntry,
)
from .state import cooldown_tracker

router = APIRouter(prefix="/api")


@router.get("/config")
async def get_config():
    """Get current configuration (with masked API key)."""
    settings = load_settings()

    # Mask the API key for security
    config_dict = settings.model_dump()
    if config_dict["upstream"]["api_key"]:
        config_dict["upstream"]["api_key"] = mask_api_key(config_dict["upstream"]["api_key"])

    return JSONResponse(config_dict)


@router.put("/config")
async def update_config(request: Request):
    """Update configuration."""
    try:
        data = await request.json()

        # Load current settings to preserve masked API key if needed
        current_settings = load_settings()

        # Handle API key - if it's masked, keep the original
        if "upstream" in data and "api_key" in data["upstream"]:
            if is_masked_key(data["upstream"]["api_key"]):
                data["upstream"]["api_key"] = current_settings.upstream.api_key

        # Validate and save
        new_settings = Settings.model_validate(data)
        save_settings(new_settings)

        return JSONResponse({"status": "ok", "message": "Configuration saved"})

    except Exception as e:
        return JSONResponse(
            {"status": "error", "message": str(e)},
            status_code=400,
        )


@router.post("/models/probe")
async def probe_models():
    """
    Probe upstream for available models.
    Tries both OpenAI and Anthropic model list endpoints.
    """
    settings = load_settings()

    if not settings.upstream.base_url or not settings.upstream.api_key:
        return JSONResponse(
            {"status": "error", "message": "Upstream not configured"},
            status_code=400,
        )

    base_url = settings.upstream.base_url.rstrip("/")
    api_key = settings.upstream.api_key
    models = []

    async with httpx.AsyncClient(timeout=30.0) as client:
        # Try OpenAI /v1/models endpoint
        try:
            resp = await client.get(
                f"{base_url}/v1/models",
                headers={"Authorization": f"Bearer {api_key}"},
            )
            if resp.status_code == 200:
                data = resp.json()
                if "data" in data:
                    for m in data["data"]:
                        model_id = m.get("id", "")
                        if model_id and model_id not in models:
                            models.append(model_id)
        except Exception as e:
            print(f"OpenAI models probe failed: {e}")

        # If no models found, try Anthropic-style (some proxies may have different endpoints)
        # Note: Anthropic doesn't have a standard models endpoint, but some proxies do

    if not models:
        return JSONResponse(
            {
                "status": "error",
                "message": "Could not fetch models from upstream. Please add models manually.",
                "models": [],
            },
            status_code=200,  # Return 200 so UI can handle gracefully
        )

    return JSONResponse({
        "status": "ok",
        "models": sorted(models),
    })


@router.get("/health")
async def get_health():
    """Get health status of all configured models."""
    settings = load_settings()
    cooldown_states = cooldown_tracker.snapshot()

    health = {}
    for model in settings.models:
        name = model.name
        if name in cooldown_states:
            health[name] = cooldown_states[name]
        else:
            health[name] = {
                "available": True,
                "cooldown_remaining": 0,
                "last_error_code": None,
                "last_error_msg": "",
            }

    return JSONResponse({
        "models": health,
        "cooldown_seconds": settings.cooldown_seconds,
    })


@router.post("/health/reset")
async def reset_health():
    """Reset all model cooldowns."""
    cooldown_tracker.reset_all()
    return JSONResponse({"status": "ok", "message": "All cooldowns cleared"})


@router.post("/health/reset/{model_name}")
async def reset_model_health(model_name: str):
    """Reset cooldown for a specific model."""
    cooldown_tracker.reset_model(model_name)
    return JSONResponse({"status": "ok", "message": f"Cooldown cleared for {model_name}"})
