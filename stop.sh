#!/bin/bash
# Stop IT ServiceDesk:  bash /path/to/servicedesk/stop.sh
DIR="$(cd "$(dirname "$0")" && pwd)"
if [ -f "$DIR/.pid" ]; then
  kill "$(cat "$DIR/.pid")" 2>/dev/null && echo "Stopped."
  rm -f "$DIR/.pid"
else
  pkill -f "servicedesk/app.py" 2>/dev/null && echo "Stopped." || echo "Not running."
fi
