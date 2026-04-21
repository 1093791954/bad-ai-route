"""In-process state management: model cooldown tracking."""

import time
from dataclasses import dataclass, field
from threading import Lock
from typing import Optional

from .config import load_settings


@dataclass
class CooldownEntry:
    """Cooldown state for a single model."""
    cooldown_until: float = 0.0
    last_error_code: Optional[int] = None
    last_error_msg: str = ""


class CooldownTracker:
    """Track model cooldown states (in-memory, resets on restart)."""

    def __init__(self):
        self._entries: dict[str, CooldownEntry] = {}
        self._lock = Lock()

    def mark_bad(
        self,
        model_name: str,
        *,
        status_code: Optional[int] = None,
        reason: str = ""
    ) -> None:
        """Mark a model as temporarily unavailable."""
        settings = load_settings()
        cooldown_seconds = settings.cooldown_seconds

        with self._lock:
            entry = self._entries.setdefault(model_name, CooldownEntry())
            entry.cooldown_until = time.time() + cooldown_seconds
            entry.last_error_code = status_code
            if reason:
                entry.last_error_msg = reason
            elif status_code:
                entry.last_error_msg = f"HTTP {status_code}"
            else:
                entry.last_error_msg = "unknown"

    def is_available(self, model_name: str) -> bool:
        """Check if a model is currently available (not in cooldown)."""
        with self._lock:
            entry = self._entries.get(model_name)
            if entry is None:
                return True
            return time.time() >= entry.cooldown_until

    def get_remaining_cooldown(self, model_name: str) -> float:
        """Get remaining cooldown seconds for a model (0 if available)."""
        with self._lock:
            entry = self._entries.get(model_name)
            if entry is None:
                return 0.0
            remaining = entry.cooldown_until - time.time()
            return max(0.0, remaining)

    def snapshot(self) -> dict[str, dict]:
        """Get a snapshot of all model states for /api/health."""
        with self._lock:
            now = time.time()
            result = {}
            for name, entry in self._entries.items():
                remaining = max(0.0, entry.cooldown_until - now)
                result[name] = {
                    "available": remaining <= 0,
                    "cooldown_remaining": round(remaining, 1),
                    "last_error_code": entry.last_error_code,
                    "last_error_msg": entry.last_error_msg,
                }
            return result

    def reset_all(self) -> None:
        """Clear all cooldowns (for manual reset)."""
        with self._lock:
            self._entries.clear()

    def reset_model(self, model_name: str) -> None:
        """Clear cooldown for a specific model."""
        with self._lock:
            self._entries.pop(model_name, None)


# Global singleton
cooldown_tracker = CooldownTracker()
