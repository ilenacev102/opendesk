"""SNMP printer sweep (read-only): map sysDescr/sysName/serial to rows.

Optional component: without the SNMP library or network the sweep reports a
clean skip instead of failing. Community strings never enter logs.
"""

from services.discovery_service import normalize_serial

OID_SYSDESCR = "1.3.6.1.2.1.1.1.0"
OID_SYSNAME = "1.3.6.1.2.1.1.5.0"
OID_PRT_SERIAL = "1.3.6.1.2.1.43.5.1.1.17.1"

PRINTER_OIDS = [OID_SYSDESCR, OID_SYSNAME, OID_PRT_SERIAL]

try:
    from pysnmp.hlapi import (  # noqa: F401
        CommunityData,
        ContextData,
        ObjectIdentity,
        ObjectType,
        SnmpEngine,
        UdpTransportTarget,
        getCmd,
    )

    _HAS_PYSNMP = True
except ImportError:
    _HAS_PYSNMP = False


class SnmpError(ValueError):
    """Friendly SNMP failure (missing lib, unreachable, bad data)."""


class _LiveSession:
    def __init__(self, host, community):
        self.host = host
        self.community = community

    def get_many(self, oids):
        from pysnmp.hlapi import (
            CommunityData,
            ContextData,
            ObjectIdentity,
            ObjectType,
            SnmpEngine,
            UdpTransportTarget,
            getCmd,
        )

        engine = SnmpEngine()
        objects = [ObjectType(ObjectIdentity(oid)) for oid in oids]
        try:
            error_ind, error_status, _, binds = next(
                getCmd(
                    engine,
                    CommunityData(self.host, self.community, mpModel=1),
                    UdpTransportTarget((self.host, 161), timeout=3, retries=1),
                    ContextData(),
                    *objects,
                )
            )
        except Exception as exc:
            raise TimeoutError(f"no response from {self.host}: {exc}")
        if error_ind:
            raise TimeoutError(f"no response from {self.host}: {error_ind}")
        if error_status:
            raise SnmpError(f"SNMP error from {self.host}: {error_status}")
        return {str(b[0]): str(b[1]) for b in binds}


def live_session(host, community):
    if not _HAS_PYSNMP:
        raise SnmpError("SNMP библиотеката недостасува: инсталирајте pysnmp за sweep.")
    if not (host or "").strip():
        raise SnmpError("Недостасува host за SNMP sweep.")
    return _LiveSession(host.strip(), community or "")


def _split_descr(descr: str):
    parts = (descr or "").strip().split(None, 1)
    if not parts:
        return "", ""
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], parts[1]


def sweep(hosts, community, session_factory=None):
    factory = session_factory or live_session
    rows, errors = [], []
    for host in hosts or []:
        host = (host or "").strip()
        if not host:
            continue
        try:
            session = factory(host, community)
            values = session.get_many(PRINTER_OIDS)
        except SnmpError:
            raise
        except Exception as exc:
            errors.append(f"{host}: {exc}")
            continue
        serial = normalize_serial(values.get(OID_PRT_SERIAL, ""))
        if not serial:
            errors.append(f"{host}: нема сериски број, прескокнато.")
            continue
        manufacturer, model = _split_descr(values.get(OID_SYSDESCR, ""))
        rows.append(
            {
                "Hostname": (values.get(OID_SYSNAME, "") or "").strip() or host,
                "SerialNumber": serial,
                "Manufacturer": manufacturer,
                "Model": model,
                "OS": "",
                "LastSeen": "",
                "Source": "snmp",
            }
        )
    return rows, errors
