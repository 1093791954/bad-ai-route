"""Configuration model and persistence for AI-Route."""

import json
import os
import tempfile
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field


class UpstreamConfig(BaseModel):
    """Upstream API configuration."""
    base_url: str = ""
    api_key: str = ""
    request_timeout: float = Field(default=60.0, description="Request timeout in seconds")
    first_chunk_timeout: float = Field(default=20.0, description="First chunk wait timeout in seconds")


class ModelEntry(BaseModel):
    """A model entry with enable/disable state."""
    name: str
    enabled: bool = True


class Settings(BaseModel):
    """Main application settings."""
    listen_host: str = "127.0.0.1"
    listen_port: int = 18624
    cooldown_seconds: int = Field(default=30, description="Cooldown duration after model failure")
    probe_enabled: bool = Field(default=True, description="Enable background health probing")
    probe_interval_seconds: int = Field(default=300, ge=10, description="Interval between health probes in seconds")
    upstream: UpstreamConfig = Field(default_factory=UpstreamConfig)
    models: list[ModelEntry] = Field(default_factory=list)


# Default config file path (next to the package or cwd)
_CONFIG_PATH: Optional[Path] = None


def get_config_path() -> Path:
    """Get the config file path."""
    global _CONFIG_PATH
    if _CONFIG_PATH is not None:
        return _CONFIG_PATH

    # Try to find config.json in several locations
    candidates = [
        Path.cwd() / "config.json",
        Path(__file__).parent.parent / "config.json",
    ]
    for p in candidates:
        if p.exists():
            _CONFIG_PATH = p
            return p

    # Default to cwd
    _CONFIG_PATH = Path.cwd() / "config.json"
    return _CONFIG_PATH


def set_config_path(path: Path) -> None:
    """Override the config file path."""
    global _CONFIG_PATH
    _CONFIG_PATH = path


def load_settings() -> Settings:
    """Load settings from config.json, creating default if not exists."""
    config_path = get_config_path()

    if not config_path.exists():
        # Create default config
        settings = Settings()
        save_settings(settings)
        return settings

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return Settings.model_validate(data)
    except (json.JSONDecodeError, Exception) as e:
        print(f"Warning: Failed to load config from {config_path}: {e}")
        return Settings()


def save_settings(settings: Settings) -> None:
    """Atomically save settings to config.json."""
    config_path = get_config_path()

    # Write to temp file then atomic rename
    fd, tmp_path = tempfile.mkstemp(
        suffix=".json",
        prefix="config_",
        dir=config_path.parent
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(settings.model_dump(), f, indent=2, ensure_ascii=False)

        # Atomic replace
        os.replace(tmp_path, config_path)
    except Exception:
        # Clean up temp file on error
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise


def mask_api_key(key: str) -> str:
    """Mask API key for display, showing only first 4 and last 4 chars."""
    if len(key) <= 8:
        return "*" * len(key)
    return key[:4] + "*" * (len(key) - 8) + key[-4:]


def is_masked_key(key: str) -> bool:
    """Check if a key is a masked placeholder."""
    return "****" in key
