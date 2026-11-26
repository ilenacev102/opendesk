#!/usr/bin/env python3
"""Aggregate JSON access log lines from ServiceDesk.

The in-process admin page shows one worker's counters; this script reads the
durable record instead, so it survives restarts and spans gunicorn workers:

    python3 scripts/log_report.py --log logs/app.log
    docker compose logs --no-log-prefix | python3 scripts/log_report.py --log -

Exit codes: 0 success, 2 unreadable log or invalid --since.
"""

import argparse
import json
import sys
from collections import Counter
from datetime import datetime
from math import ceil

CLASSES = ("2xx", "3xx", "4xx", "5xx")


def _parse_iso(value: str) -> float:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError as exc:
        raise ValueError(f"invalid --since value: {value}") from exc


def summarize(lines, top: int = 10, since: str | None = None) -> dict:
    """Aggregate access records; ignores blank, non-JSON and service lines."""
    since_ts = _parse_iso(since) if since else None
    classes: Counter = Counter()
    routes: dict = {}
    ids: set = set()
    skipped = service_lines = requests = rate_limited = 0

    for raw in lines:
        text = raw.strip()
        if not text:
            continue
        try:
            record = json.loads(text)
        except ValueError:
            skipped += 1
            continue
        if not isinstance(record, dict):
            skipped += 1
            continue
        if record.get("msg") != "request":
            service_lines += 1
            continue
        if since_ts is not None:
            ts = record.get("ts")
            if ts:
                try:
                    if _parse_iso(str(ts)) < since_ts:
                        continue
                except ValueError:
                    pass
        requests += 1
        status = int(record.get("status") or 0)
        classes[f"{status // 100}xx"] += 1
        if status == 429:
            rate_limited += 1
        request_id = str(record.get("request_id") or "")
        if request_id:
            ids.add(request_id)
        key = (
            str(record.get("method") or "?"),
            str(record.get("route") or "unmatched"),
        )
        row = routes.setdefault(
            key,
            {
                "method": key[0],
                "route": key[1],
                "count": 0,
                "errors": 0,
                "rate_limited": 0,
                "durations": [],
            },
        )
        row["count"] += 1
        if status >= 500:
            row["errors"] += 1
        if status == 429:
            row["rate_limited"] += 1
        try:
            row["durations"].append(float(record.get("duration_ms") or 0.0))
        except (TypeError, ValueError):
            row["durations"].append(0.0)

    for row in routes.values():
        durations = sorted(row.pop("durations"))
        row["p95_ms"] = (
            durations[ceil(0.95 * len(durations)) - 1] if durations else None
        )

    ordered = sorted(
        routes.values(), key=lambda r: (-r["errors"], -r["count"], r["route"])
    )
    return {
        "requests": requests,
        "classes": {name: classes.get(name, 0) for name in CLASSES},
        "rate_limited": rate_limited,
        "skipped": skipped,
        "service_lines": service_lines,
        "ids": len(ids),
        "routes": ordered[: max(1, top)],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Aggregate ServiceDesk JSON access logs."
    )
    parser.add_argument("--log", required=True, help="path to app.log, or - for stdin")
    parser.add_argument(
        "--top", type=int, default=10, help="route rows to show (default 10)"
    )
    parser.add_argument(
        "--since", default=None, help="only requests at/after this ISO time"
    )
    args = parser.parse_args(argv)

    try:
        if args.log == "-":
            report = summarize(sys.stdin, top=args.top, since=args.since)
        else:
            with open(args.log, encoding="utf-8") as fh:
                report = summarize(fh, top=args.top, since=args.since)
    except OSError as exc:
        print(f"cannot read {args.log}: {exc}", file=sys.stderr)
        return 2
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    classes = report["classes"]
    print(
        f"Requests: {report['requests']} "
        f"(2xx {classes['2xx']}, 3xx {classes['3xx']}, "
        f"4xx {classes['4xx']}, 5xx {classes['5xx']})"
    )
    print(f"Rate limited (429): {report['rate_limited']}")
    print(f"Distinct request_id: {report['ids']}")
    print(f"Skipped non-JSON lines: {report['skipped']}")
    print(f"Service lines ignored: {report['service_lines']}")
    print()
    print(f"{'METHOD':<7}{'ROUTE':<34}{'COUNT':>6}{'5XX':>6}{'429':>6}{'P95':>9}")
    for row in report["routes"]:
        p95 = "—" if row["p95_ms"] is None else f"{row['p95_ms']:.0f} ms"
        print(
            f"{row['method']:<7}{row['route'][:33]:<34}"
            f"{row['count']:>6}{row['errors']:>6}{row['rate_limited']:>6}{p95:>9}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
