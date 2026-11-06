"""Assembles the audience intelligence view from stored data only."""
from .. import db
from . import scoring

TYPE_GROUPS = {
    "questions": ("question",),
    "complaints": ("frustration", "dislikes_existing_solution"),
    "requests": ("resource_request", "unmet_need"),
    "outcomes": ("desired_outcome", "repetitive_task"),
}


def latest_analysis(audience_id: str, done_only: bool = True) -> dict | None:
    q = "SELECT * FROM analyses WHERE audience_id=? " + ("AND status='done' " if done_only else "") + \
        "ORDER BY started_at DESC LIMIT 1"
    return db.one(q, (audience_id,))


def signal_rows(analysis_id: str, where: str = "", params=(), limit: int = 500) -> list[dict]:
    return db.all_(f"""
        SELECT s.id, s.signal_type, s.intent_level, s.summary, s.cluster_id, s.author_ref,
               e.id AS evidence_id, e.quote, e.locator, e.comment_id, e.content_item_id,
               src.id AS source_id, src.title AS source_title, src.platform, src.original_url,
               cm.published_at AS comment_date, cm.likes, ci.title AS item_title, ci.url AS item_url
        FROM signals s JOIN evidence e ON e.id=s.evidence_id
        LEFT JOIN sources src ON src.id=e.source_id
        LEFT JOIN comments cm ON cm.id=e.comment_id
        LEFT JOIN content_items ci ON ci.id=e.content_item_id
        WHERE s.analysis_id=? {where}
        ORDER BY COALESCE(cm.likes,0) DESC LIMIT {int(limit)}""", (analysis_id, *params))


def intelligence(audience_id: str) -> dict:
    last_any = latest_analysis(audience_id, done_only=False)
    an = latest_analysis(audience_id)
    out = {"analysis": an, "last_attempt": last_any, "clusters": [], "groups": {}, "purchasing": [],
           "performance": [], "runs": []}
    out["performance"] = db.all_("""
        SELECT ci.id, ci.title, ci.url, ci.platform, ci.published_at, em.metric, MAX(em.value) AS value, em.source_note
        FROM engagement_metrics em JOIN content_items ci ON ci.id=em.content_item_id
        WHERE ci.audience_id=? AND em.metric IN ('views','impressions','reach','plays','likes','comments','opens','score')
        GROUP BY ci.id, em.metric ORDER BY value DESC LIMIT 30""", (audience_id,))
    if not an:
        return out
    clusters = db.all_("SELECT * FROM clusters WHERE analysis_id=?", (an["id"],))
    for cl in clusters:
        cl["quotes"] = signal_rows(an["id"], "AND s.cluster_id=?", (cl["id"],), limit=40)
        cl["quotes"].sort(key=lambda q: -scoring.INTENT_WEIGHTS[q["intent_level"]])
    clusters.sort(key=lambda c: (-(c["intent_score"] * c["unique_authors"]), -c["signal_count"]))
    out["clusters"] = clusters
    for g, types in TYPE_GROUPS.items():
        marks = ",".join("?" for _ in types)
        out["groups"][g] = signal_rows(an["id"], f"AND s.signal_type IN ({marks})", types, limit=60)
    strong = tuple(scoring.STRONG_INTENTS)
    out["purchasing"] = signal_rows(an["id"], f"AND s.intent_level IN ({','.join('?' for _ in strong)})", strong, 100)
    out["purchasing"].sort(key=lambda q: -scoring.INTENT_WEIGHTS[q["intent_level"]])
    counts = db.all_("SELECT intent_level, COUNT(*) AS n FROM signals WHERE analysis_id=? GROUP BY intent_level", (an["id"],))
    out["intent_counts"] = {r["intent_level"]: r["n"] for r in counts}
    out["runs"] = db.all_("SELECT id, stage, provider, model, external, status, error, notes, input_chars, started_at, "
                          "finished_at FROM ai_runs WHERE analysis_id=? ORDER BY started_at", (an["id"],))
    return out


def evidence_detail(evidence_id: str) -> dict | None:
    e = db.one("SELECT * FROM evidence WHERE id=?", (evidence_id,))
    if not e:
        return None
    e["source"] = db.one("SELECT id, title, kind, platform, original_url, filename, retrieved_at, retrieval_method, voice "
                         "FROM sources WHERE id=?", (e["source_id"],))
    if e.get("comment_id"):
        e["comment"] = db.one("SELECT text, published_at, likes, replies, platform, parent_ref, is_spam, is_duplicate "
                              "FROM comments WHERE id=?", (e["comment_id"],))
    if e.get("content_item_id"):
        ci = db.one("SELECT id, title, url, kind, published_at, text FROM content_items WHERE id=?", (e["content_item_id"],))
        if ci:
            pos = ci["text"].find(e["quote"][:60])
            start = max(0, pos - 500) if pos >= 0 else 0
            ci["context"] = ci["text"][start:start + 1400]
            ci["context_start"] = start
            del ci["text"]
        e["content_item"] = ci
    e["signals"] = db.all_("SELECT s.signal_type, s.intent_level, s.summary, cl.label AS cluster FROM signals s "
                           "LEFT JOIN clusters cl ON cl.id=s.cluster_id WHERE s.evidence_id=?", (evidence_id,))
    return e
