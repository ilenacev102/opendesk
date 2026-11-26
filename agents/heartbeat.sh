#!/usr/bin/env bash
# OpenDesk Heartbeat Agent (Linux & macOS)
# Collects hardware inventory and submits heartbeat to OpenDesk.
#
# Config via environment variables or command-line arguments:
#   OPENDESK_URL / SERVICEDESK_URL        base URL, e.g. http://192.168.1.10:5000
#   OPENDESK_TOKEN / SERVICEDESK_TOKEN    API Bearer token (magacioner scope)
#   DRY_RUN=1                             prints JSON without POSTing
#
# Usage:
#   export OPENDESK_URL=http://192.168.1.10:5000
#   export OPENDESK_TOKEN=your-bearer-token
#   ./heartbeat.sh
#
# Or one-liner:
#   ./heartbeat.sh --url http://192.168.1.10:5000 --token your-bearer-token

set -u

ENDPOINT="/api/v1/discovery/heartbeat"

# CLI flag parsing
while [ $# -gt 0 ]; do
  case "$1" in
    --url)
      OPENDESK_URL="$2"
      shift 2
      ;;
    --token)
      OPENDESK_TOKEN="$2"
      shift 2
      ;;
    --dry-run)
      DRY_RUN="1"
      shift 1
      ;;
    *)
      shift 1
      ;;
  esac
done

BASE_URL="${OPENDESK_URL:-${SERVICEDESK_URL:-}}"
AUTH_TOKEN="${OPENDESK_TOKEN:-${SERVICEDESK_TOKEN:-}}"

if [ "${DRY_RUN:-${SERVICEDESK_DRY_RUN:-}}" != "1" ]; then
  if [ -z "$BASE_URL" ] || [ -z "$AUTH_TOKEN" ]; then
    echo "heartbeat: Error - OpenDesk URL and Token must be provided (via env or --url / --token)" >&2
    exit 1
  fi
fi

# Detect Hostname
HOSTNAME_VAL="${HOSTNAME_OVERRIDE:-$(hostname 2>/dev/null || uname -n)}"

# Detect Serial Number (Linux DMI or macOS system_profiler)
SERIAL_VAL="${SERIAL_OVERRIDE:-}"
if [ -z "$SERIAL_VAL" ]; then
  if [ -r /sys/class/dmi/id/product_serial ]; then
    SERIAL_VAL="$(tr -d ' \t\n' < /sys/class/dmi/id/product_serial 2>/dev/null)"
  fi
fi
if [ -z "$SERIAL_VAL" ] && command -v dmidecode >/dev/null 2>&1; then
  SERIAL_VAL="$(dmidecode -s system-serial-number 2>/dev/null | head -n 1 | tr -d ' \t\n')"
fi
if [ -z "$SERIAL_VAL" ] && [ "$(uname -s)" = "Darwin" ]; then
  SERIAL_VAL="$(system_profiler SPHardwareDataType 2>/dev/null | awk '/Serial/ {print $NF}')"
fi
if [ -z "$SERIAL_VAL" ] && [ -r /etc/machine-id ]; then
  SERIAL_VAL="MID-$(cut -c1-12 < /etc/machine-id 2>/dev/null)"
fi

# Detect Manufacturer and Model
MANUFACTURER_VAL=""
MODEL_VAL=""
if [ "$(uname -s)" = "Darwin" ]; then
  MANUFACTURER_VAL="Apple"
  MODEL_VAL="$(sysctl -n hw.model 2>/dev/null)"
else
  if [ -r /sys/class/dmi/id/sys_vendor ]; then
    MANUFACTURER_VAL="$(head -n 1 < /sys/class/dmi/id/sys_vendor 2>/dev/null | tr -d '\n')"
  fi
  if [ -r /sys/class/dmi/id/product_name ]; then
    MODEL_VAL="$(head -n 1 < /sys/class/dmi/id/product_name 2>/dev/null | tr -d '\n')"
  fi
fi

# Detect Operating System
OS_VAL=""
if [ "$(uname -s)" = "Darwin" ]; then
  OS_VAL="macOS $(sw_vers -productVersion 2>/dev/null)"
else
  if command -v hostnamectl >/dev/null 2>&1; then
    OS_VAL="$(hostnamectl 2>/dev/null | grep -i 'operating system' | cut -d: -f2 | sed 's/^ *//')"
  fi
  if [ -z "$OS_VAL" ] && [ -r /etc/os-release ]; then
    OS_VAL="$(grep '^PRETTY_NAME=' /etc/os-release 2>/dev/null | cut -d= -f2 | tr -d '"')"
  fi
  if [ -z "$OS_VAL" ]; then
    OS_VAL="$(uname -srm 2>/dev/null)"
  fi
fi

json_escape() {
  printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g' | tr -d '\n'
}

BODY=$(printf '{"hostname":"%s","serial":"%s","manufacturer":"%s","model":"%s","os":"%s"}' \
  "$(json_escape "$HOSTNAME_VAL")" \
  "$(json_escape "$SERIAL_VAL")" \
  "$(json_escape "$MANUFACTURER_VAL")" \
  "$(json_escape "$MODEL_VAL")" \
  "$(json_escape "$OS_VAL")")

if [ "${DRY_RUN:-${SERVICEDESK_DRY_RUN:-}}" = "1" ]; then
  printf '%s\n' "$BODY"
  exit 0
fi

if ! command -v curl >/dev/null 2>&1; then
  echo "heartbeat: curl is required to transmit heartbeat" >&2
  exit 1
fi

RESP="$(curl -sS -m 20 -w '\n%{http_code}' -X POST \
  "${BASE_URL}${ENDPOINT}" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${AUTH_TOKEN}" \
  -d "$BODY" 2>&1)"
CODE="$(printf '%s' "$RESP" | tail -n 1)"
PAYLOAD="$(printf '%s' "$RESP" | head -n -1)"
printf '%s\n' "$PAYLOAD"
case "$CODE" in
  200) exit 0 ;;
  429) echo "heartbeat: rate limited, retry later" >&2; exit 2 ;;
  *) echo "heartbeat: server returned $CODE" >&2; exit 2 ;;
esac
