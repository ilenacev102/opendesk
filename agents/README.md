# Heartbeat агенти

Лесни колектори што го пријавуваат уредот на ServiceDesk
(`POST /api/v1/discovery/heartbeat`). Без тајни во скриптите —
сè преку environment-променливи.

## Конфигурација (двата система)

| Променлива | Опис | Пример |
|---|---|---|
| `SERVICEDESK_URL` | Базичен URL на серверот | `http://192.168.1.10:5000` |
| `SERVICEDESK_TOKEN` | API Bearer токен (magacioner опсег, од `/api-tokens`) | — |
| `SERVICEDESK_DRY_RUN=1` | Само испечати JSON, без POST (тестирање) | — |

## Linux (`heartbeat.sh`)

Потребно: `bash`, `curl`. Сериски број: `/sys/class/dmi/id/product_serial`,
па `dmidecode`, па `machine-id` fallback. Не бара root (освен за dmidecode).

```bash
export SERVICEDESK_URL=http://192.168.1.10:5000
export SERVICEDESK_TOKEN=вашиот-токен
./heartbeat.sh
```

Cron (секој работен ден 09:00):

```cron
0 9 * * 1-5 SERVICEDESK_URL=http://192.168.1.10:5000 SERVICEDESK_TOKEN=вашиот-токен /opt/servicedesk/heartbeat.sh
```

## Windows (`heartbeat.ps1`)

Потребно: PowerShell 5.1+, WMI пристап (читање). Тест:

```powershell
$env:SERVICEDESK_URL="http://192.168.1.10:5000"
$env:SERVICEDESK_TOKEN="вашиот-токен"
$env:SERVICEDESK_DRY_RUN="1"
.\heartbeat.ps1
```

Task Scheduler: задача што го стартува скриптот при најава, со
кориснички environment-променливи (никогаш тврдо-кодирани credentials).

## Одговор на серверот

JSON со `verdict`: `new` (креиран уред), `match` (ажуриран LastSeen),
`conflict` (задолжен или несовпаѓање — без автоматска измена).
Exit-кодови: `0` успех, `1` лоша конфигурација, `2` мрежна/серверска грешка.
