#!/bin/zsh
# Runs 10_live_interruptions.js and restarts the scratch Ollama (port 11435) / app server (port 8761) when the test
# stops them. Only ever touches the PIDs recorded in $SCRATCH. Never point it at the live app.
S=${SCRATCH:?set SCRATCH to the scratch folder holding data/, logs/, ollama.pid and server.pid}
FLAG=$S/restart.flag; rm -f $FLAG
start_ollama() { cd ~/AudienceOS && OLLAMA_HOST=127.0.0.1:11435 OLLAMA_MODELS=$HOME/AudienceOS/runtime/models nohup runtime/ollama/ollama serve >> $S/logs/ollama.log 2>&1 & echo $! > $S/ollama.pid; }
start_server() { cd ~/AudienceOS/backend && AUDIENCEOS_DATA=$S/data AUDIENCEOS_PORT=8761 AUDIENCEOS_NO_KEYCHAIN=1 AUDIENCEOS_OLLAMA_URL=http://127.0.0.1:11435 nohup .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8761 >> $S/logs/server.log 2>&1 & echo $! > $S/server.pid; }
cd ~/AudienceOS/e2e
SHOTS=${SHOTS:-$S/shots} OLLAMA_PID=$(cat $S/ollama.pid) SERVER_PID=$(cat $S/server.pid) RESTART_FLAG=$FLAG node 10_live_interruptions.js &
NODE=$!
while kill -0 $NODE 2>/dev/null; do
  if [ -f $FLAG ]; then
    what=$(cat $FLAG); rm -f $FLAG
    if [ "$what" = "server" ]; then start_server; echo "restarted server $(cat $S/server.pid)"; else start_ollama; echo "restarted ollama $(cat $S/ollama.pid)"; fi
  fi
  sleep 1
done
wait $NODE; echo "exit $?"
