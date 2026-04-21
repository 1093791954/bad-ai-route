"""Entry point for running AI-Route as a module."""

import sys
import threading
import webbrowser

import uvicorn

from .config import load_settings, get_config_path


def main():
    """Main entry point."""
    # Load settings to get host/port
    settings = load_settings()
    host = settings.listen_host
    port = settings.listen_port

    config_path = get_config_path()
    print(f"AI-Route starting...")
    print(f"  Config file: {config_path}")
    print(f"  Listen: http://{host}:{port}")
    print(f"  Web UI: http://{host}:{port}/ui")
    print(f"  Anthropic API: http://{host}:{port}/v1/messages")
    print(f"  OpenAI API: http://{host}:{port}/v1/chat/completions")
    print()

    # Open browser after a short delay
    url = f"http://{host}:{port}/ui"

    def open_browser():
        try:
            webbrowser.open(url)
        except Exception as e:
            print(f"Could not open browser: {e}")

    threading.Timer(1.0, open_browser).start()

    # Run uvicorn
    uvicorn.run(
        "ai_route.app:app",
        host=host,
        port=port,
        log_level="info",
    )


if __name__ == "__main__":
    main()
