"""Normalizes retrieved material into content items, comments and metrics, with dedup and spam checks."""
import hashlib
import re
from datetime import datetime, timezone

from .. import config, db

TEXT_KEYS = ("comment", "text", "body", "message", "content", "comment_text", "reply", "value", "review")
DATE_KEYS = ("date", "timestamp", "time", "created_at", "published_at", "created", "posted_at", "published")
LIKE_KEYS = ("likes", "like_count", "likecount", "reactions", "upvotes", "score", "hearts")
REPLY_KEYS = ("replies", "reply_count", "replycount", "num_replies")
AUTHOR_KEYS = ("author", "username", "user", "commenter", "name", "handle", "author_name", "author_id", "user_id")
PARENT_KEYS = ("parent", "post", "video", "post_url", "video_url", "parent_id", "media", "post_id", "video_id", "url", "permalink")

SPAM_PATTERNS = [
    (re.compile(r"\b(dm|message) me\b|\bcheck (out )?my (profile|page|bio)\b|\bfollow (me|back)\b", re.I), "self-promotion"),
    (re.compile(r"\b(crypto|bitcoin|forex|nft|giveaway winner|whatsapp \+?\d)", re.I), "scam keywords"),
    (re.compile(r"(https?://\S+.*){2,}", re.I), "multiple links"),
    (re.compile(r"(.)\1{9,}"), "repeated characters"),
]


def norm_text(t: str) -> str:
    t = t.lower()
    t = re.sub(r"https?://\S+", " ", t)
    t = re.sub(r"[^\w\s]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def text_hash(t: str) -> str:
    return hashlib.sha256(norm_text(t).encode()).hexdigest()[:32]


def author_ref(platform: str, author: str | None) -> str | None:
    if not author:
        return None
    return "a_" + hashlib.sha256(f"{platform}:{author.strip().lower()}".encode()).hexdigest()[:12]


def parse_date(v) -> str | None:
    if v in (None, ""):
        return None
    if isinstance(v, (int, float)) or (isinstance(v, str) and re.fullmatch(r"\d{9,13}", v.strip())):
        n = float(v)
        if n > 1e12:
            n /= 1000
        try:
            return datetime.fromtimestamp(n, tz=timezone.utc).date().isoformat()
        except (OverflowError, ValueError, OSError):
            return None
    s = str(v).strip()
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d",
                "%m/%d/%Y", "%m/%d/%y", "%d/%m/%Y", "%b %d, %Y", "%B %d, %Y", "%a, %d %b %Y %H:%M:%S %z",
                "%a, %d %b %Y %H:%M:%S %Z"):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        return None


def to_int(v) -> int | None:
    if v in (None, ""):
        return None
    try:
        s = str(v).replace(",", "").strip().lower()
        mult = 1
        if s.endswith("k"):
            mult, s = 1000, s[:-1]
        elif s.endswith("m"):
            mult, s = 1_000_000, s[:-1]
        n = int(float(s) * mult)
        return n if n >= 0 else None
    except ValueError:
        return None


def pick(d: dict, keys) -> object:
    lower = {str(k).strip().lower().replace(" ", "_"): v for k, v in d.items()}
    for k in keys:
        if k in lower and lower[k] not in (None, ""):
            return lower[k]
    return None


def has_text_key(d: dict) -> bool:
    return pick(d, TEXT_KEYS) is not None


def spam_reason(text: str) -> str | None:
    for pat, reason in SPAM_PATTERNS:
        if pat.search(text):
            return reason
    if len(norm_text(text)) == 0:
        return "no words (emoji/links only)"
    return None


def add_content_item(c, source: dict, *, text: str, title: str | None = None, kind: str = "document",
                     url: str | None = None, author: str | None = None, published_at: str | None = None,
                     metadata: dict | None = None) -> tuple[str, bool]:
    """Returns (content_item_id, created). Duplicate text within the audience is not stored twice."""
    text = (text or "")[: config.MAX_TEXT_CHARS_PER_ITEM]
    h = text_hash(text) if text.strip() else None
    if h:
        existing = c.execute("SELECT id FROM content_items WHERE audience_id=? AND content_hash=?",
                             (source["audience_id"], h)).fetchone()
        if existing:
            return existing[0], False
    cid = db.new_id("ci")
    db.insert(c, "content_items", {
        "id": cid, "source_id": source["id"], "audience_id": source["audience_id"],
        "platform": source.get("platform") or "other", "kind": kind, "title": title, "url": url,
        "author": author, "published_at": published_at, "text": text,
        "word_count": len(text.split()), "content_hash": h, "metadata_json": metadata or {}, "created_at": db.now()})
    return cid, True


def add_metric(c, content_item_id: str, metric: str, value, note: str, measured_at: str | None = None):
    if value is None:
        return
    db.insert(c, "engagement_metrics", {"id": db.new_id("em"), "content_item_id": content_item_id, "metric": metric,
                                         "value": float(value), "measured_at": measured_at or db.now(),
                                         "source_note": note, "created_at": db.now()})


def add_comments(c, source: dict, records: list[dict], content_item_id: str | None = None) -> dict:
    """Store comment records. Returns counts: added, duplicates, spam, skipped."""
    platform = source.get("platform") or "other"
    counts = {"added": 0, "duplicates": 0, "spam": 0, "skipped": 0}
    seen_in_batch: dict[str, str] = {}
    for r in records:
        text = pick(r, TEXT_KEYS)
        if not isinstance(text, str) or not text.strip():
            counts["skipped"] += 1
            continue
        text = text.strip()[:5000]
        h = text_hash(text)
        dup_of = seen_in_batch.get(h)
        if not dup_of:
            ex = c.execute("SELECT id FROM comments WHERE audience_id=? AND norm_hash=? AND is_duplicate=0 LIMIT 1",
                           (source["audience_id"], h)).fetchone()
            dup_of = ex[0] if ex else None
        sr = spam_reason(text)
        parent = pick(r, PARENT_KEYS)
        cid = db.new_id("cm")
        db.insert(c, "comments", {
            "id": cid, "audience_id": source["audience_id"], "source_id": source["id"],
            "content_item_id": content_item_id, "parent_ref": str(parent)[:300] if parent else None,
            "platform": platform, "author_ref": author_ref(platform, str(pick(r, AUTHOR_KEYS) or "") or None),
            "text": text, "norm_hash": h, "published_at": parse_date(pick(r, DATE_KEYS)),
            "likes": to_int(pick(r, LIKE_KEYS)), "replies": to_int(pick(r, REPLY_KEYS)),
            "is_duplicate": 1 if dup_of else 0, "duplicate_of": dup_of,
            "is_spam": 1 if sr else 0, "spam_reason": sr, "created_at": db.now()})
        if dup_of:
            counts["duplicates"] += 1
        else:
            seen_in_batch[h] = cid
        if sr:
            counts["spam"] += 1
        counts["added"] += 1
    return counts


def flatten_record(d: dict) -> dict:
    """Flatten Meta-style export records: {'string_map_data': {'Comment': {'value': ..}, 'Time': {'timestamp': ..}}}."""
    out = {}
    for k, v in d.items():
        if k == "string_map_data" and isinstance(v, dict):
            for kk, vv in v.items():
                if isinstance(vv, dict):
                    out[kk] = vv.get("value") or vv.get("timestamp") or vv.get("href")
        elif isinstance(v, (str, int, float)) or v is None:
            out[k] = v
        elif isinstance(v, dict) and k in ("author", "user", "snippet"):
            for kk, vv in v.items():
                if isinstance(vv, (str, int, float)):
                    out.setdefault(kk if kk not in out else f"{k}_{kk}", vv)
            name = v.get("username") or v.get("name") or v.get("authorDisplayName")
            if name:
                out["author"] = name
    return out


def find_records(obj, depth: int = 0) -> list[dict]:
    """Find the largest list of dict records that contain a text field anywhere in a JSON document."""
    best: list[dict] = []
    if depth > 6:
        return best
    if isinstance(obj, list) and obj and all(isinstance(x, dict) for x in obj[:50]):
        flat = [flatten_record(x) for x in obj]
        if sum(1 for x in flat[:50] if has_text_key(x)) >= max(1, len(flat[:50]) // 2):
            best = flat
    children = obj.values() if isinstance(obj, dict) else (obj if isinstance(obj, list) else [])
    for ch in children:
        if isinstance(ch, (dict, list)):
            cand = find_records(ch, depth + 1)
            if len(cand) > len(best):
                best = cand
    return best
