#!/bin/zsh
# Starts AudienceOS (local AI engine + app server) and opens it. Safe to run twice.
ROOT="$HOME/AudienceOS"
LOGS="$ROOT/data/logs"; mkdir -p "$LOGS"
PORT=8760
export OLLAMA_HOST=127.0.0.1:11434 OLLAMA_MODELS="$ROOT/runtime/models"

if ! curl -s -m 2 http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
  if [ -x "$ROOT/runtime/ollama/ollama" ]; then
    echo "Starting local AI engine…"
    nohup "$ROOT/runtime/ollama/ollama" serve >> "$LOGS/ollama.log" 2>&1 &
  else
    echo "Local AI engine not found — AudienceOS will run with the rules engine only."
  fi
fi

if ! curl -s -m 2 http://127.0.0.1:$PORT/api/health >/dev/null 2>&1; then
  echo "Starting AudienceOS…"
  cd "$ROOT/backend"
  nohup ./.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port $PORT >> "$LOGS/server.log" 2>&1 &
  echo $! > "$ROOT/data/server.pid"
  for i in {1..60}; do curl -s -m 1 http://127.0.0.1:$PORT/api/health >/dev/null 2>&1 && break; sleep 0.5; done
fi

if curl -s -m 2 http://127.0.0.1:$PORT/api/health >/dev/null 2>&1; then
  URL="http://127.0.0.1:$PORT"
  if [ -d "/Applications/Google Chrome.app" ]; then
    open -na "Google Chrome" --args --app="$URL" --window-size=1440,900
  else
    open "$URL"
  fi
  echo "AudienceOS is running at $URL"
else
  echo "AudienceOS did not start. See $LOGS/server.log"
  exit 1
fi
