#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p "$HOME/.cache/declic"
if ! command -v ollama >/dev/null; then
  installer="$(mktemp)"
  curl -fsSL --retry 2 https://ollama.com/install.sh -o "$installer"
  sh "$installer"
  rm -f "$installer"
fi
export OLLAMA_HOST=127.0.0.1:11434 OLLAMA_NO_CLOUD=1
if ! curl -fsS http://127.0.0.1:11434/api/version >/dev/null; then
  nohup ollama serve >"$HOME/.cache/declic/ollama.log" 2>&1 </dev/null &
  for i in $(seq 1 60); do curl -fsS http://127.0.0.1:11434/api/version >/dev/null && break; sleep 1; done
fi
ollama pull qwen2.5:3b-instruct
touch "$HOME/.cache/declic/ollama-enabled"
if [[ -f "$HOME/.cache/declic/server.pid" ]]; then
  pid="$(cat "$HOME/.cache/declic/server.pid")"
  if [[ "$pid" =~ ^[0-9]+$ ]] && ps -p "$pid" -o args= | grep -q 'uvicorn app.main:app'; then
    kill "$pid"
    for i in $(seq 1 30); do kill -0 "$pid" 2>/dev/null || break; sleep 1; done
  fi
fi
bash .devcontainer/start.sh
