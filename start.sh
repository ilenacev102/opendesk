#!/bin/bash
# Start IT ServiceDesk - run from anywhere:  bash /path/to/servicedesk/start.sh
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR" || exit 1
if [ -f "$DIR/.pid" ] && kill -0 "$(cat "$DIR/.pid")" 2>/dev/null; then
  echo "Already running (pid $(cat "$DIR/.pid"))."
  exit 0
fi
PY="python3"
if [ -d "$DIR/.venv/bin" ]; then
  PY="$DIR/.venv/bin/python3"
fi
$PY -c "import flask, pandas, docx" 2>/dev/null || $PY -m pip install -r requirements.txt
PORT="${SERVICEDESK_PORT:-5000}"
setsid nohup "$PY" app.py > logs/server.log 2>&1 < /dev/null &
echo $! > .pid
sleep 4
curl -s -o /dev/null -w "ServiceDesk: %{http_code}\n" "http://127.0.0.1:${PORT}/"
