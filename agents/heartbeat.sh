#!/usr/bin/env bash
# Heartbeat agent (Linux): collect inventory and POST it to ServiceDesk.
# Config via environment only - no secrets in this file:
#   SERVICEDESK_URL    base URL, e.g. http://192.168.1.10:5000
#   SERVICEDESK_TOKEN  API Bearer token (magacioner scope)
#   SERVICEDESK_DRY_RUN=1 prints JSON without POSTing (testing)
#   HOSTNAME_OVERRIDE / SERIAL_OVERRIDE for testing
set -u

ENDPOINT="/api/v1/discovery/heartbeat"

if [ -z "${SERVICEDESK_URL:-}" ] || [ -z "${SERVICEDESK_TOKEN:-}" ]; then
  echo "heartbeat: SERVICEDESK_URL and SERVICEDESK_TOKEN must be set" >&2
  exit 1
fi

HOSTNAME_VAL="${HOSTNAME_OVERRIDE:-$(hostname 2>/dev/null || uname -n)}"
SERIAL_VAL="${SERIAL_OVERRIDE:-}"
if [ -z "$SERIAL_VAL" ]; then
  if [ -r /sys/class/dmi/id/product_serial ]; then
    SERIAL_VAL="$(tr -d ' \t\n' < /sys/class/dmi/id/product_serial 2>/dev/null)"
  fi
fi
if [ -z "$SERIAL_VAL" ] && command -v dmidecode >/dev/null 2>&1; then
  SERIAL_VAL="$(dmidecode -s system-serial-number 2>/dev/null | head -n 1 | tr -d ' \t\n')"
fi
if [ -z "$SERIAL_VAL" ] && [ -r /etc/machine-id ]; then
  SERIAL_VAL="MID-$(cut -c1-12 < /etc/machine-id 2>/dev/null)"
fi

MANUFACTURER_VAL=""
MODEL_VAL=""
if [ -r /sys/class/dmi/id/sys_vendor ]; then
  MANUFACTURER_VAL="$(head -n 1 < /sys/class/dmi/id/sys_vendor 2>/dev/null | tr -d '\n')"
fi
if [ -r /sys/class/dmi/id/product_name ]; then
  MODEL_VAL="$(head -n 1 < /sys/class/dmi/id/product_name 2>/dev/null | tr -d '\n')"
fi
OS_VAL=""
if command -v hostnamectl >/dev/null 2>&1; then
  OS_VAL="$(hostnamectl 2>/dev/null | grep -i 'operating system' | cut -d: -f2 | sed 's/^ *//')"
fi
if [ -z "$OS_VAL" ] && [ -r /etc/os-release ]; then
  # shellcheck disable=SC1091
  OS_VAL="$(grep '^PRETTY_NAME=' /etc/os-release 2>/dev/null | cut -d= -f2 | tr -d '"')"
fi
if [ -z "$OS_VAL" ]; then
  OS_VAL="$(uname -srm 2>/dev/null)"
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

if [ "${SERVICEDESK_DRY_RUN:-}" = "1" ]; then
  printf '%s\n' "$BODY"
  exit 0
fi

if ! command -v curl >/dev/null 2>&1; then
  echo "heartbeat: curl is required" >&2
  exit 1
fi

RESP="$(curl -sS -m 20 -w '\n%{http_code}' -X POST \
  "${SERVICEDESK_URL}${ENDPOINT}" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${SERVICEDESK_TOKEN}" \
  -d "$BODY" 2>&1)"
CODE="$(printf '%s' "$RESP" | tail -n 1)"
PAYLOAD="$(printf '%s' "$RESP" | head -n -1)"
printf '%s\n' "$PAYLOAD"
case "$CODE" in
  200) exit 0 ;;
  429) echo "heartbeat: rate limited, retry later" >&2; exit 2 ;;
  *) echo "heartbeat: server returned $CODE" >&2; exit 2 ;;
esac
