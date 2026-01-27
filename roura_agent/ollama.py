"""
Roura Agent Ollama Client - Local LLM integration via Ollama.

© Roura.io
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import httpx


def get_base_url() -> str:
    return os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")


def get_model() -> str:
    return os.getenv("OLLAMA_MODEL", "").strip()


def list_models(base_url: str | None = None) -> list[str]:
    base = (base_url or get_base_url()).rstrip("/")
    with httpx.Client(timeout=10.0) as client:
        r = client.get(f"{base}/api/tags")
        r.raise_for_status()
        data = r.json()
        return [m["name"] for m in data.get("models", [])]


def generate(prompt: str, model: str | None = None, base_url: str | None = None) -> str:
    """
    One-shot, non-streaming text generation via Ollama /api/generate.
    """
    base = (base_url or get_base_url()).rstrip("/")
    m = (model or get_model()).strip()
    if not m:
        raise RuntimeError("OLLAMA_MODEL is not set (or model not provided).")

    payload: Dict[str, Any] = {
        "model": m,
        "prompt": prompt,
        "stream": False,
    }

    with httpx.Client(timeout=60.0) as client:
        r = client.post(f"{base}/api/generate", json=payload)
        r.raise_for_status()
        data = r.json()
        return str(data.get("response", ""))


def chat(
    messages: List[Dict[str, str]],
    model: Optional[str] = None,
    base_url: Optional[str] = None,
) -> str:
    """
    Multi-turn chat via Ollama /api/chat (non-streaming).
    messages: [{"role": "system|user|assistant", "content": "..."}]
    """
    base = (base_url or get_base_url()).rstrip("/")
    m = (model or get_model()).strip()
    if not m:
        raise RuntimeError("OLLAMA_MODEL is not set (or model not provided).")

    payload: Dict[str, Any] = {
        "model": m,
        "messages": messages,
        "stream": False,
    }

    with httpx.Client(timeout=120.0) as client:
        r = client.post(f"{base}/api/chat", json=payload)
        r.raise_for_status()
        data = r.json()
        msg = data.get("message") or {}
        return str(msg.get("content", ""))
