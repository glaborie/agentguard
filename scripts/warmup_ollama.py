"""
Pre-loads Ollama models into memory at container start.

Sends a generate/embed request for each model listed in OLLAMA_MODELS so they
are resident when the first real request arrives. Uses a long timeout because
loading from a Docker virtual disk on Windows can take 2–3 minutes.

Environment variables:
  OLLAMA_URL     Base URL of the Ollama service (default: http://localhost:11434)
  OLLAMA_MODELS  Comma-separated model names to warm up (default: nomic-embed-text)
"""

import os
import sys
import time

import requests

BASE_URL = os.getenv("OLLAMA_URL", "http://localhost:11434").rstrip("/")
MODELS = [m.strip() for m in os.getenv("OLLAMA_MODELS", "nomic-embed-text").split(",") if m.strip()]
LOAD_TIMEOUT = int(os.getenv("OLLAMA_WARMUP_TIMEOUT", "300"))


def wait_for_ollama(timeout: int = 120) -> None:
    deadline = time.time() + timeout
    print(f"Waiting for Ollama at {BASE_URL} ...", flush=True)
    while time.time() < deadline:
        try:
            r = requests.get(f"{BASE_URL}/api/tags", timeout=5)
            if r.status_code == 200:
                print("Ollama is up.", flush=True)
                return
        except requests.exceptions.ConnectionError:
            pass
        time.sleep(3)
    print("ERROR: Ollama did not become healthy in time.", file=sys.stderr)
    sys.exit(1)


def is_embedding_model(model: str) -> bool:
    return "embed" in model.lower()


def warmup_model(model: str) -> None:
    print(f"  Loading {model} ...", flush=True)
    start = time.time()
    try:
        if is_embedding_model(model):
            r = requests.post(
                f"{BASE_URL}/api/embed",
                json={"model": model, "input": "warmup"},
                timeout=LOAD_TIMEOUT,
            )
        else:
            r = requests.post(
                f"{BASE_URL}/api/generate",
                json={"model": model, "prompt": "Hi", "stream": False},
                timeout=LOAD_TIMEOUT,
            )
        elapsed = time.time() - start
        if r.status_code == 200:
            print(f"  {model} loaded in {elapsed:.1f}s", flush=True)
        else:
            print(f"  WARNING: {model} returned HTTP {r.status_code} ({elapsed:.1f}s)", flush=True)
    except requests.exceptions.Timeout:
        print(f"  WARNING: {model} warmup timed out after {LOAD_TIMEOUT}s — model may still be loading", flush=True)
    except Exception as e:
        print(f"  WARNING: {model} warmup failed: {e}", flush=True)


def main() -> None:
    wait_for_ollama()
    print(f"Warming up models: {', '.join(MODELS)}", flush=True)
    for model in MODELS:
        warmup_model(model)
    print("Warmup done.", flush=True)


if __name__ == "__main__":
    main()
