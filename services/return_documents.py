"""Return document payload builders (single + bulk offboarding)."""

from utils.helpers import stamp


def today_datum():
    """Return today's date as DD.MM.YYYY for document templates."""
    today = stamp().split(" ")[0]
    parts = today.split("-")
    return f"{parts[2]}.{parts[1]}.{parts[0]}"


def single_return_doc(emp, dev, asset_id, condition, datum):
    """Build fill_zadolzenie payload for a single return."""
    return {
        "name": f"{emp['FirstName']} {emp['LastName']}",
        "email": emp.get("Email", ""),
        "company": emp.get("Organization", ""),
        "department": emp.get("Department", ""),
        "manufacturer": dev.get("Manufacturer", ""),
        "model": dev.get("Model", ""),
        "serial": dev.get("SerialNumber", ""),
        "asset": asset_id,
        "date_z": "",
        "date_v": datum,
        "da_ne": "ДА" if condition == "Good" else "НЕ",
    }


def multi_return_items(devs):
    """Build fill_zadolzenie_multi items list from device records."""
    return [
        {
            "asset": d.get("AssetID", ""),
            "type": d.get("Type", ""),
            "model": d.get("Model", ""),
            "serial": d.get("SerialNumber", ""),
            "manufacturer": d.get("Manufacturer", ""),
        }
        for d in devs
    ]
