"""Rules engine: deterministic keyword/pattern analysis. Used when no AI model is available, and as a
second opinion on commercial intent. It is labeled 'Rules engine (no AI model)' everywhere."""
import re

INTENT_PATTERNS = [
    ("verified_purchase", r"\b(i|we) (just )?(bought|purchased|ordered|paid for|signed up for|enrolled in)\b|\bmy order\b|\bi own (the|your)\b"),
    ("paid_solution_request", r"\b(i'?d|i would|would) (happily |gladly |definitely )?pay\b|take my money|\bdo you sell\b|\bis (it|this) for sale\b|\bplease (sell|make) (a |an |your )?(course|kit|class|workshop|product|membership|program|starter kit)\b|\bwould buy\b|\bi'?d buy\b|\bsell (this|these|them|it)\b"),
    ("buying_question", r"\bwhere (can|do|did) (i|you) (buy|get|order|find)\b|\bhow much (is|does|do|for)\b|\bwhat brand\b|\bwhich (one|brand|model) should i (buy|get)\b|\b(price|cost) of\b|\blink to (buy|it|the)\b|\bdiscount code\b|\bworth (it|the money)\b"),
    ("existing_spending", r"\b(i|we) (spent|spend|pay|paid)\b|\bsubscription\b|\$\s?\d+|\bmembership\b|\bhired a\b"),
    ("free_info_request", r"\b(do you have|can you (make|share|post|do)|could you (make|share|post|do)|please (share|post|do)|would love) (a |an |some )?(guide|template|tutorial|video|checklist|list|recipe|pdf|breakdown|step|part 2|follow.?up)\b|\bplease explain\b"),
]
TYPE_PATTERNS = [
    ("resource_request", r"\b(do you have|can you (make|share)|could you (make|share)|would love|please (make|share|post)) (a |an |some )?\w+"),
    ("dislikes_existing_solution", r"\b(tried|bought|used) .{0,60}\b(didn'?t|doesn'?t|did not|never) (work|help)\b|\bwaste of (money|time)\b|\boverpriced\b|\btoo expensive\b|\bclunky\b|\bdoesn'?t work\b"),
    ("frustration", r"\bfrustrat\w*|\bstruggl\w*|\bannoy\w*|\bconfus\w*|\boverwhelm\w*|\btired of\b|\bstuck\b|\bkeeps? (failing|happening)\b|\bcan'?t (figure|get|seem)\b|\bnever works\b|\bhate (it|when|that)\b|\bugh\b"),
    ("repetitive_task", r"\bevery (single )?(day|week|month|time)\b|\bmanually\b|\bspreadsheet\b|\bkeep having to\b"),
    ("desired_outcome", r"\bi (want|wish|hope|need) to\b|\bmy goal\b|\bdream of\b|\bhoping to\b"),
    ("unmet_need", r"\bno one (talks|explains|covers)\b|\bcan'?t find (a|any)\b|\bwish there (was|were)\b|\bnothing (out there|works)\b"),
]
QUESTION_START = re.compile(r"^(how|what|where|why|when|which|can|could|does|do|is|are|should|would|any|has|have)\b", re.I)
SENT_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")

_INTENT = [(k, re.compile(p, re.I)) for k, p in INTENT_PATTERNS]
_TYPE = [(k, re.compile(p, re.I)) for k, p in TYPE_PATTERNS]


def intent_of(text: str) -> str | None:
    for k, rx in _INTENT:
        if rx.search(text):
            return k
    return None


def analyze_unit(text: str, voice: str) -> list[dict]:
    """Return signals for one unit: [{signal_type, intent_level, summary, quote}]."""
    out = []
    for sent in SENT_SPLIT.split(text):
        s = sent.strip()
        if len(s) < 12 or len(s) > 400:
            continue
        stype = next((k for k, rx in _TYPE if rx.search(s)), None)
        is_q = s.endswith("?") or bool(QUESTION_START.match(s))
        if not stype and is_q:
            stype = "question"
        intent = intent_of(s)
        if not stype and intent in ("verified_purchase", "paid_solution_request", "buying_question", "existing_spending"):
            stype = "desired_outcome" if intent != "buying_question" else "question"
        if not stype:
            continue
        if voice == "creator" and stype == "question" and not intent:
            continue  # rhetorical questions in the creator's own content are weak signals
        if not intent:
            intent = "free_info_request" if stype == "resource_request" else ("curiosity" if is_q else "engagement")
        out.append({"signal_type": stype, "intent_level": intent, "summary": s[:140], "quote": s[:300]})
        if len(out) >= 3:
            break
    return out


def cluster_signals(signals: list[dict], max_clusters: int = 10) -> list[dict]:
    """Group signal summaries with TF-IDF + agglomerative clustering. Labels are top keywords (not AI-written)."""
    if not signals:
        return []
    texts = [s["summary"] for s in signals]
    if len(texts) < 3:
        return [{"label": "All signals", "description": "Too few signals to group.", "signal_ids": list(range(len(texts)))}]
    from sklearn.cluster import AgglomerativeClustering
    from sklearn.feature_extraction.text import TfidfVectorizer
    vec = TfidfVectorizer(stop_words="english", max_features=3000, ngram_range=(1, 2), min_df=1)
    X = vec.fit_transform(texts)
    if X.shape[1] == 0:
        return [{"label": "All signals", "description": "No distinctive keywords.", "signal_ids": list(range(len(texts)))}]
    n = max(2, min(max_clusters, len(texts) // 4 or 2))
    labels = AgglomerativeClustering(n_clusters=n, metric="cosine", linkage="average").fit_predict(X.toarray())
    terms = vec.get_feature_names_out()
    out = []
    for k in sorted(set(labels)):
        ids = [i for i, l in enumerate(labels) if l == k]
        centroid = X[ids].mean(axis=0).A1
        top = [terms[i] for i in centroid.argsort()[::-1][:3] if centroid[i] > 0]
        out.append({"label": ", ".join(top) or "misc", "description": "Keyword grouping (rules engine, not AI-written).",
                    "signal_ids": ids})
    return sorted(out, key=lambda c: -len(c["signal_ids"]))


# Lexical support required before a model-assigned STRONG intent is accepted. A local model will
# otherwise label ordinary frustration as "spending". Accuracy beats recall here.
STRONG_SUPPORT = {
    "verified_purchase": re.compile(r"\b(bought|purchased|ordered|paid|signed up|enrolled|subscribed|own (the|your)|my order)\b", re.I),
    "existing_spending": re.compile(r"\$\s?\d|\b(spent|spend|paid|pay for|cost me|subscription|membership|bought|purchased|class|course|book|ebook|hired)\b", re.I),
    "buying_question": re.compile(r"\b(buy|purchase|order|price|cost|how much|link|brand|where (can|do|did) (i|you) (get|find)|worth (it|the money)|recommend|which (one|brand|model))\b", re.I),
    "paid_solution_request": re.compile(r"\b(pay|buy|sell|take my money|purchase|sign up|offer|course|workshop|coaching|kit|membership|class)\b", re.I),
}


def check_intent(intent: str, quote: str) -> str:
    """Downgrade a strong intent label that the quote's own words don't support."""
    rx = STRONG_SUPPORT.get(intent)
    if rx is None or rx.search(quote):
        return intent
    return "curiosity" if "?" in quote or QUESTION_START.match(quote.strip()) else "engagement"


STRONG_INTENTS = ("verified_purchase", "existing_spending", "buying_question", "paid_solution_request")


def guard_intent(intent: str, quote: str) -> str:
    """Final gate before a signal is stored, whatever produced it (model, rules engine or a later stage):
    a strong intent survives only if the quote's own words support it — either the lexical support list
    or the rules engine independently reaching the same label."""
    if intent not in STRONG_INTENTS:
        return intent
    ri = intent_of(quote)
    if ri in STRONG_INTENTS:
        # Explicit buying language decides the label (e.g. "where can I buy" is a buying question, not a paid request).
        return ri
    return check_intent(intent, quote)


# Internal reference numbers the opportunity prompt uses (T3 = theme 3, E12 = evidence 12). They must not
# leak into stored prose that people read (problem statements, hypotheses, rationales).
_REF_LIST = re.compile(r"\s*[\(\[]\s*(?:(?:themes?|evidence)\s*)?[TE]\d+(?:\s*(?:,|/|&|and|-|–)\s*[TE]?\d+)*\s*[\)\]]", re.I)
_REF_PHRASE = re.compile(r"\s*\b(?:as )?(?:see|per|cf\.?|from|in|according to|based on|cited in|citing)?\s*(?:themes?|evidence)?\s*"
                         r"\b[TE]\d+\b(?:\s*(?:,|/|&|and|-|–)\s*\b[TE]?\d+\b)*", re.I)


def strip_refs(text):
    """Remove T#/E# reference numbers (and lists of them) from free text, tidying leftover punctuation."""
    if not isinstance(text, str) or not re.search(r"\b[TE]\d+\b", text):
        return text
    t = _REF_LIST.sub("", text)
    t = _REF_PHRASE.sub("", t)
    t = re.sub(r"\(\s*\)|\[\s*\]", "", t)
    t = re.sub(r"\s+([,.;:!?])", r"\1", t)
    t = re.sub(r"([,;:])\s*([,.;:])", r"\2", t)
    t = re.sub(r"^[\s,;:.\-–]+", "", t)
    t = re.sub(r"\s{2,}", " ", t).strip()
    return t[:1].upper() + t[1:] if t else t


def strip_refs_deep(v):
    if isinstance(v, str):
        return strip_refs(v)
    if isinstance(v, list):
        return [strip_refs_deep(x) for x in v]
    if isinstance(v, dict):
        return {k: strip_refs_deep(x) for k, x in v.items()}
    return v
