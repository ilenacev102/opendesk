# OpenDesk Heartbeat Agents

Lightweight discovery and telemetry agents that report hardware inventory and system uptime to OpenDesk (`POST /api/v1/discovery/heartbeat`).

- **Zero Secrets in Code:** Strictly authenticated via API Bearer token.
- **Cross-Platform:** Native support for Linux, macOS, and Windows.
- **Preview & Reconcile:** Reports match existing devices, detect changes, or stage new assets without overwriting assigned hardware.

---

## 🐧 Linux & 🍏 macOS (`heartbeat.sh`)

### Requirements
- `bash`, `curl`

### Running the Agent

You can pass configuration via command-line flags or environment variables:

```bash
# Option A: Command-line arguments
./heartbeat.sh --url http://your-opendesk-host:5000 --token YOUR_BEARER_TOKEN

# Option B: Environment variables (supports OPENDESK_TOKEN and SERVICEDESK_TOKEN)
export OPENDESK_URL=http://your-opendesk-host:5000
export OPENDESK_TOKEN=YOUR_BEARER_TOKEN
export SERVICEDESK_TOKEN=YOUR_BEARER_TOKEN
./heartbeat.sh
```

### Dry-Run Test
To inspect collected JSON hardware payload without sending HTTP requests:
```bash
./heartbeat.sh --dry-run
```

### Automated Scheduling (Cron)
Run every weekday at 09:00:
```cron
0 9 * * 1-5 OPENDESK_URL=http://your-opendesk-host:5000 OPENDESK_TOKEN=your-token /usr/local/bin/heartbeat.sh
```

---

## 🪟 Windows (`heartbeat.ps1`)

### Requirements
- PowerShell 5.1+ (Windows 10/11, Windows Server 2016+)

### Running the Agent
```powershell
$env:OPENDESK_URL="http://your-opendesk-host:5000"
$env:OPENDESK_TOKEN="YOUR_BEARER_TOKEN"
.\heartbeat.ps1
```

### Scheduled Task Deployment
Deploy via Windows Task Scheduler to run on user logon or daily at startup.

---

## Server Response & Statuses

The OpenDesk server processes heartbeats and returns a JSON response with a `verdict`:
- `new`: Asset newly created in catalog as Available.
- `match`: Matched existing hardware, refreshed `LastSeen` timestamp and OS version.
- `conflict`: Hardware discrepancy detected (e.g. Serial match with different hostname); flagged for administrator review without destructive overwrite.
