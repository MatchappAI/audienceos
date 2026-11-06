#!/bin/zsh
# Stops the AudienceOS server and the bundled local AI engine (never a system-wide Ollama install).
ROOT="$(cd "$(dirname "$0")" && pwd)"
pkill -f "uvicorn app.main:app --host 127.0.0.1 --port 8760" && echo "AudienceOS stopped."
# Match the engine by its executable path, not its command line: it may have been started as
# "./ollama/ollama serve" from inside runtime/, which a command-line match on the full path misses.
stopped=0
for pid in $(pgrep -f "ollama serve") $(pgrep -f "runtime/ollama/llama-server"); do
  exe=$(lsof -a -p "$pid" -d txt -Fn 2>/dev/null | sed -n 's/^n//p' | head -1)
  case "$exe" in
    "$ROOT"/runtime/*) kill "$pid" 2>/dev/null && stopped=1 ;;
  esac
done
[ $stopped = 1 ] && echo "Local AI engine stopped."
exit 0
