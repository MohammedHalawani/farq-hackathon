#!/usr/bin/env bash
# Start the scheduling console. Usage: ./serve.sh [port]   (default 8000)
set -euo pipefail

cd "$(dirname "$0")"
PORT="${1:-${PORT:-8000}}"
HOST_URL="${OLLAMA_HOST:-http://localhost:11434}"

# Which agent model to expect: .env wins, then .env.example, then the default.
MODEL="gpt-oss:120b-cloud"
for f in .env .env.example; do
  if [ -f "$f" ]; then
    found="$(sed -n 's/^OLLAMA_MODEL=//p' "$f" | head -1)"
    if [ -n "$found" ]; then
      MODEL="$found"
      break
    fi
  fi
done

if ! command -v uv >/dev/null; then
  echo "uv is not installed — see https://docs.astral.sh/uv/"
  exit 1
fi

echo "==> syncing dependencies"
uv sync --quiet

if [ -f .env ]; then
  echo "==> using .env"
else
  echo "==> no .env (copy .env.example to change the model; the default works)"
fi

# The console works without Ollama — only the Agent tab needs it. Warn, never block.
if ! curl -sf --max-time 3 "$HOST_URL/api/tags" >/dev/null 2>&1 && command -v ollama >/dev/null; then
  echo "==> starting ollama"
  ollama serve >/tmp/ollama.log 2>&1 &
  for _ in $(seq 20); do
    if curl -sf --max-time 1 "$HOST_URL/api/tags" >/dev/null 2>&1; then break; fi
    sleep 0.5
  done
fi

if curl -sf --max-time 3 "$HOST_URL/api/tags" 2>/dev/null | grep -q "$MODEL"; then
  echo "==> agent model ready: $MODEL"
else
  echo "!!  $MODEL is not available — every tab works except Agent."
  echo "    fix with:  ollama signin && ollama pull $MODEL"
fi

if lsof -ti "tcp:$PORT" >/dev/null 2>&1; then
  echo "!!  port $PORT is already in use — free it, or run: ./serve.sh 8001"
  exit 1
fi

echo "==> http://localhost:$PORT   (the first 'Run solver' takes ~35 s, then it is cached)"
exec uv run uvicorn api.main:app --port "$PORT"
