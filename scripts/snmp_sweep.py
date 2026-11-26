"""Manual read-only SNMP printer sweep (optional; requires ``pysnmp``).

Usage:
    python3 scripts/snmp_sweep.py --hosts 10.0.0.10,10.0.0.11

Prints JSON rows ready for the discovery import flow. Without the optional
``pysnmp`` package the script exits 2 with a friendly message; nothing is
written to the database and community strings are never logged.
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.snmp_service import SnmpError, sweep  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--hosts",
        required=True,
        help="comma-separated IP addresses or hostnames",
    )
    parser.add_argument("--community", default="public", help="SNMP read community")
    args = parser.parse_args(argv)
    hosts = [h.strip() for h in args.hosts.split(",") if h.strip()]
    try:
        rows, errors = sweep(hosts, args.community)
    except SnmpError as exc:
        print(f"SNMP: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({"rows": rows, "errors": errors}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
