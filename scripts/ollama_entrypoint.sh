#!/bin/bash
# Start Ollama server in the background, then pre-load models via CLI.
# The CLI load is not subject to HTTP client timeouts, so it will complete
# even if the model takes many minutes to load from disk (Windows Docker).

set -e

ollama serve &
SERVER_PID=$!

echo "Waiting for Ollama server to be ready..."
until ollama list > /dev/null 2>&1; do
  sleep 3
done
echo "Ollama ready."

IFS=',' read -ra MODELS <<< "${OLLAMA_WARMUP_MODELS:-nomic-embed-text}"
for MODEL in "${MODELS[@]}"; do
  MODEL="${MODEL// /}"  # trim whitespace
  echo "Pre-loading ${MODEL} ..."
  # 'ollama run' with a one-shot prompt loads the model and exits
  echo "warmup" | ollama run "${MODEL}" 2>&1 || echo "WARNING: failed to pre-load ${MODEL}"
  echo "${MODEL} ready."
done

echo "All models loaded. Ollama is ready to serve."
wait "${SERVER_PID}"
