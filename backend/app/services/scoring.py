"""Transparent opportunity scoring and cluster statistics.

The total is a relative attractiveness index (0-100) for deciding what to TEST next.
It is not a probability of success and is never shown as one.
"""
import statistics
from datetime import date

from .. import settings_store

INTENT_WEIGHTS = {"engagement": 0, "curiosity": 0.5, "free_info_request": 1, "existing_spending": 3,
                  "buying_question": 3, "paid_solution_request": 4, "verified_purchase": 5}
STRONG_INTENTS = {"existing_spending", "buying_question", "paid_solution_request", "verified_purchase"}


def cluster_stats(sigs: list[dict]) -> dict:
    """sigs: [{intent_level, author_ref, source_id, platform, date, voice}]"""
    authors = {s["author_ref"] for s in sigs if s.get("author_ref")}
    anonymous = sum(1 for s in sigs if not s.get("author_ref"))
    voices = len(authors) + anonymous
    breakdown: dict[str, int] = {}
    for s in sigs:
        breakdown[s["intent_level"]] = breakdown.get(s["intent_level"], 0) + 1
    ages = []
    today = date.today()
    for s in sigs:
        if s.get("date"):
            try:
                ages.append((today - date.fromisoformat(s["date"][:10])).days)
            except ValueError:
                pass
    strong_voices = len({s.get("author_ref") or id(s) for s in sigs if s["intent_level"] in STRONG_INTENTS})
    audience_voice = sum(1 for s in sigs if s.get("voice") == "audience")
    sources = {s["source_id"] for s in sigs}
    # Intent score 0-5: mean weight per distinct voice, so one person repeating themselves doesn't inflate it.
    per_voice: dict = {}
    for s in sigs:
        k = s.get("author_ref") or id(s)
        per_voice[k] = max(per_voice.get(k, 0), INTENT_WEIGHTS[s["intent_level"]])
    intent_score = round(sum(per_voice.values()) / max(1, len(per_voice)), 2)
    if audience_voice == 0:
        quality = "Creator content only"
    elif strong_voices >= 3 and len(sources) >= 2:
        quality = "Strong"
    elif voices >= 5 or strong_voices >= 1:
        quality = "Moderate"
    else:
        quality = "Weak"
    return {"signal_count": len(sigs), "unique_authors": voices, "source_count": len(sources),
            "platform_count": len({s.get("platform") for s in sigs}),
            "median_age_days": statistics.median(ages) if ages else None,
            "intent_score": intent_score, "evidence_quality": quality, "intent_breakdown": breakdown,
            "audience_voice": audience_voice, "strong_voices": strong_voices}


def data_scores(clusters: list[dict], total_voices: int) -> dict:
    """Map linked clusters' stats onto 1-5 for the data-derived rubric criteria."""
    if not clusters:
        return {"problem_frequency": 1, "commercial_intent": 1, "evidence_quality": 1}
    voices = sum(c["unique_authors"] for c in clusters)
    share = voices / max(1, total_voices)
    freq = 1 + min(4, round(share * 10))  # 40%+ of all voices -> 5
    intent = max(c["intent_score"] for c in clusters)
    intent_s = 1 + min(4, round(intent))
    q = {"Strong": 5, "Moderate": 3, "Weak": 2, "Creator content only": 1}
    evq = max(q.get(c["evidence_quality"], 1) for c in clusters)
    return {"problem_frequency": freq, "commercial_intent": intent_s, "evidence_quality": evq}


def total(scores: dict, rubric: dict | None = None) -> float:
    rubric = rubric or settings_store.get("rubric")
    num = den = 0.0
    for key, spec in rubric.items():
        w = float(spec.get("weight", 0))
        if key in scores and w > 0:
            num += w * (scores[key] - 1) / 4
            den += w
    return round(100 * num / den, 1) if den else 0.0


def explain(scores: dict, rubric: dict | None = None) -> list[dict]:
    rubric = rubric or settings_store.get("rubric")
    return [{"key": k, "label": v["label"], "weight": v["weight"], "source": v["source"], "score": scores.get(k)}
            for k, v in rubric.items()]
