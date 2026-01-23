from __future__ import annotations

import os
import httpx

DEFAULT_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")

def get_base_url() -> str:
    return os.getenv("OLLAMA_BASE_URL", DEFAULT_BASE_URL).rstrip("/")

def list_models(base_url: str | None = None) -> list[str]:
    base = (base_url or get_base_url()).rstrip("/")
    with httpx.Client(timeout=10.0) as client:
        r = client.get(f"{base}/api/tags")
        r.raise_for_status()
        data = r.json()
        return [m["name"] for m in data.get("models", [])]
