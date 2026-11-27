#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p "$HOME/.cache/declic" data
export DECLIC_PILOT_LIMITS=1
export DECLIC_DB_PATH="$PWD/data/declic.sqlite3"
# Never expose Ollama port or log credentials. Cloud keys come from Codespaces secrets.
if command -v ollama >/dev/null && [[ -f "$HOME/.cache/declic/ollama-enabled" ]]; then
  export OLLAMA_HOST=127.0.0.1:11434 OLLAMA_NO_CLOUD=1
  if ! curl -fsS http://127.0.0.1:11434/api/version >/dev/null; then
    nohup ollama serve >"$HOME/.cache/declic/ollama.log" 2>&1 </dev/null &
    for i in $(seq 1 30); do curl -fsS http://127.0.0.1:11434/api/version >/dev/null && break; sleep 1; done
  fi
  export DECLIC_OLLAMA_MODEL=qwen2.5:3b-instruct DECLIC_OLLAMA_TIMEOUT=240
fi
if curl -fsS http://127.0.0.1:8000/api/health >/dev/null 2>&1; then
  echo "DÉCLIC already running. Open port 8000 in the Ports tab."
  exit 0
fi
if [[ ! -x .venv/bin/python ]] || ! .venv/bin/python -c 'import fastapi, uvicorn, fitz, httpx, multipart, email_validator' >/dev/null 2>&1; then
  echo "Python environment missing or incomplete; installing core dependencies..."
  bash .devcontainer/setup.sh --core-only
fi
nohup .venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1 >"$HOME/.cache/declic/server.log" 2>&1 </dev/null &
echo "$!" > "$HOME/.cache/declic/server.pid"
for i in $(seq 1 30); do
  if curl -fsS http://127.0.0.1:8000/api/health >/dev/null 2>&1; then
    echo "DÉCLIC ready. Open the PRIVATE forwarded port 8000 in the Ports tab."
    exit 0
  fi
  sleep 1
done
echo "Server did not start. Inspect ~/.cache/declic/server.log" >&2
tail -n 30 "$HOME/.cache/declic/server.log" >&2 || true
exit 1
