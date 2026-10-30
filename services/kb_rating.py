"""KB article ratings (F5): 1-5 votes, one row per user, ranking helpers."""

from utils.validators import ValidationError


def vote(store, article_id, username, score):
    """Record the user's 1-5 score for an article (upsert per user).

    Returns the stored row. Blank article/user and out-of-range scores raise
    ValidationError.
    """
    article_id = (article_id or "").strip()
    username = (username or "").strip()
    if not article_id:
        raise ValidationError("Написот е задолжителен.")
    if not username:
        raise ValidationError("Корисникот е задолжителен.")
    try:
        score = int(score)
    except (TypeError, ValueError):
        raise ValidationError(f"Невалидна оценка: {score}.")
    if not 1 <= score <= 5:
        raise ValidationError(f"Оцената мора да е од 1 до 5: {score}.")
    rows = store.records()
    for r in rows:
        if r.get("ArticleID") == article_id and r.get("UserName") == username:
            r["Score"] = str(score)
            store.replace_all(rows)
            return r
    row = {"ArticleID": article_id, "UserName": username, "Score": str(score)}
    store.append_row(row)
    return row


def average(store, article_id):
    """Mean score for the article rounded to 2 decimals; None when unrated."""
    total = 0
    count = 0
    for r in store.records():
        if r.get("ArticleID") != article_id:
            continue
        try:
            total += int(r.get("Score", ""))
        except (TypeError, ValueError):
            continue
        count += 1
    if not count:
        return None
    return round(total / count, 2)


def ranked(articles, store):
    """Stable sort: rated first (higher average first), unrated last."""
    sums = {}
    counts = {}
    for r in store.records():
        aid = r.get("ArticleID", "")
        try:
            s = int(r.get("Score", ""))
        except (TypeError, ValueError):
            continue
        sums[aid] = sums.get(aid, 0) + s
        counts[aid] = counts.get(aid, 0) + 1

    def key(article):
        aid = article.get("ArticleID", "")
        if not counts.get(aid):
            return (1, 0.0)
        return (0, -(sums[aid] / counts[aid]))

    return sorted(articles, key=key)
