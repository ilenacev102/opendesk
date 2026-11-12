"""Canned response macros: validated CRUD over the macros store."""

from utils.helpers import next_id, stamp
from utils.validators import ValidationError


def create(macros, title, body, category=""):
    """Create a canned response macro.

    Raises:
        ValidationError: empty title or body.
    """
    title = (title or "").strip()
    body = (body or "").strip()
    if not title:
        raise ValidationError("Насловот на макрото е задолжителен.")
    if not body:
        raise ValidationError("Текстот на макрото е задолжителен.")
    row = {
        "MacroID": next_id(macros, "MacroID", "MAC"),
        "Title": title,
        "Category": (category or "").strip(),
        "BodyText": body,
        "Created": stamp(),
    }
    macros.append_row(row)
    return row


def delete(macros, macro_id):
    """Delete a macro; unknown IDs raise ValidationError."""
    row = macros.find("MacroID", macro_id)
    if row is None:
        raise ValidationError("Макрото не постои.")
    macros.delete_where("MacroID", macro_id)
    return row


def for_picker(macros):
    """Macros sorted by category then title, ready for the comment picker."""
    return sorted(
        macros.records(),
        key=lambda m: (m.get("Category", ""), m.get("Title", "")),
    )
