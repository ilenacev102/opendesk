"""Duplicate detection at triage: token-overlap (Jaccard) similarity over titles."""

import re

_TOKEN_RE = re.compile(r"[a-zа-шѓќжѕџч0-9]+", re.IGNORECASE)

_ACTIVE_STATUSES = ("open", "in-progress")


def tokenize(title):
    """Lowercase word tokens from a title (cyrillic + latin + digits)."""
    return set(_TOKEN_RE.findall(str(title or "").lower()))


def similarity(a, b):
    """Jaccard similarity between two titles' token sets.

    Empty input has no tokens → 0.0, never a division by zero.
    """
    ta, tb = tokenize(a), tokenize(b)
    if not ta or not tb:
        return 0.0
    union = ta | tb
    return len(ta & tb) / len(union)


def detect(incidents, title, exclude_id=None, threshold=0.5, limit=5):
    """Active incidents whose titles resemble the given title.

    Scans open/in-progress incidents without an existing duplicate link
    (LinkedTo empty). Returns at most ``limit`` rows sorted by score desc,
    each as IncidentID, Title, Status, Score (rounded to 2 decimals).
    """
    title = str(title or "").strip()
    if not title:
        return []
    exclude_id = (exclude_id or "").strip()
    tokens = tokenize(title)
    if not tokens:
        return []
    matches = []
    for row in incidents.records():
        iid = (row.get("IncidentID") or "").strip()
        if not iid or iid == exclude_id:
            continue
        if row.get("Status") not in _ACTIVE_STATUSES:
            continue
        if (row.get("LinkedTo") or "").strip():
            continue
        score = similarity(title, row.get("Title", ""))
        if score >= threshold:
            matches.append(
                {
                    "IncidentID": iid,
                    "Title": row.get("Title", ""),
                    "Status": row.get("Status", ""),
                    "Score": round(score, 2),
                }
            )
    matches.sort(key=lambda m: (-m["Score"], m["IncidentID"]))
    return matches[: max(1, limit)]
