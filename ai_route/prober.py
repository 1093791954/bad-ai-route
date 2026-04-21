"""Background health probing for upstream models."""

import asyncio
import time
from typing import Optional

import httpx

from .config import load_settings
from .state import cooldown_tracker
from .upstream import get_client, build_anthropic_headers

_task: Optional[asyncio.Task] = None
_wake_event: Optional[asyncio.Event] = None


async def probe_model(model_name: str) -> tuple[bool, float, str]:
    """
    Probe a single model with a minimal real request.
    Returns (ok, latency_ms, error_msg).
    """
    settings = load_settings()
    if not settings.upstream.base_url or not settings.upstream.api_key:
        return False, 0.0, "upstream not configured"

    url = settings.upstream.base_url.rstrip("/") + "/v1/messages"
    headers = build_anthropic_headers(settings.upstream.api_key, {})
    body = {
        "model": model_name,
        "max_tokens": 1,
        "messages": [{"role": "user", "content": "hi"}],
    }

    client = await get_client()
    started = time.perf_counter()
    try:
        resp = await client.post(url, json=body, headers=headers, timeout=30.0)
        latency_ms = (time.perf_counter() - started) * 1000.0
        if resp.status_code >= 400:
            snippet = resp.text[:200]
            cooldown_tracker.mark_bad(
                model_name,
                status_code=resp.status_code,
                reason=f"probe: {snippet}",
            )
            cooldown_tracker.mark_probe(
                model_name,
                ok=False,
                latency_ms=latency_ms,
                error=f"HTTP {resp.status_code}: {snippet}",
            )
            return False, latency_ms, f"HTTP {resp.status_code}"
        cooldown_tracker.mark_probe(model_name, ok=True, latency_ms=latency_ms)
        return True, latency_ms, ""
    except Exception as e:
        latency_ms = (time.perf_counter() - started) * 1000.0
        err = f"{type(e).__name__}: {e}"
        cooldown_tracker.mark_bad(model_name, reason=f"probe: {err}")
        cooldown_tracker.mark_probe(
            model_name, ok=False, latency_ms=latency_ms, error=err
        )
        return False, latency_ms, err


async def probe_all(only_enabled: bool = True) -> dict[str, dict]:
    """Probe all (enabled) models concurrently. Returns per-model result."""
    settings = load_settings()
    targets = [
        m.name for m in settings.models if (not only_enabled or m.enabled)
    ]
    if not targets:
        return {}

    results_list = await asyncio.gather(
        *(probe_model(name) for name in targets), return_exceptions=True
    )
    out: dict[str, dict] = {}
    for name, res in zip(targets, results_list):
        if isinstance(res, Exception):
            out[name] = {"ok": False, "latency_ms": 0.0, "error": str(res)}
        else:
            ok, latency_ms, err = res
            out[name] = {"ok": ok, "latency_ms": latency_ms, "error": err}
    return out


async def _prober_loop() -> None:
    """Background loop: probe immediately, then on interval; wake on config change."""
    global _wake_event
    try:
        while True:
            settings = load_settings()
            if settings.probe_enabled:
                try:
                    await probe_all(only_enabled=True)
                except Exception as e:
                    print(f"[prober] probe_all error: {e}")

            # Reload settings in case interval changed
            settings = load_settings()
            interval = max(10, int(settings.probe_interval_seconds))
            if not settings.probe_enabled:
                # Sleep a bit longer when disabled; still wake on config change
                interval = max(interval, 60)

            assert _wake_event is not None
            try:
                await asyncio.wait_for(_wake_event.wait(), timeout=interval)
            except asyncio.TimeoutError:
                pass
            _wake_event.clear()
    except asyncio.CancelledError:
        raise


def start_prober() -> None:
    """Start the background prober task (idempotent)."""
    global _task, _wake_event
    if _task is not None and not _task.done():
        return
    _wake_event = asyncio.Event()
    _task = asyncio.create_task(_prober_loop(), name="ai-route-prober")


async def stop_prober() -> None:
    """Stop the background prober task."""
    global _task, _wake_event
    if _task is None:
        return
    _task.cancel()
    try:
        await _task
    except (asyncio.CancelledError, Exception):
        pass
    _task = None
    _wake_event = None


def notify_config_changed() -> None:
    """Wake the prober loop so it picks up new interval/enabled immediately."""
    if _wake_event is not None:
        _wake_event.set()
