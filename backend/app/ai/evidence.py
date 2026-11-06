"""Quote verification: an AI-cited quote is only stored as evidence if it actually appears in the source."""
import re
from difflib import SequenceMatcher


def _norm_with_map(s: str):
    out, idx = [], []
    prev_space = False
    for i, ch in enumerate(s):
        if ch.isalnum():
            out.append(ch.lower())
            idx.append(i)
            prev_space = False
        elif not prev_space:
            out.append(" ")
            idx.append(i)
            prev_space = True
    return "".join(out), idx


def locate_quote(quote: str, source_text: str, min_ratio: float = 0.9) -> tuple[str, int, int] | None:
    """Return (exact_source_excerpt, start, end) if the quote is found verbatim or near-verbatim."""
    quote = re.sub(r"^\W+|\W+$", "", quote or "").strip()
    if len(quote) < 8:
        return None
    nq, _ = _norm_with_map(quote)
    nq = nq.strip()
    ns, idx = _norm_with_map(source_text)
    if not nq or not ns:
        return None
    pos = ns.find(nq)
    if pos >= 0:
        start, end = idx[pos], idx[min(pos + len(nq) - 1, len(idx) - 1)] + 1
        return source_text[start:end].strip(), start, end
    # Near-verbatim (small transcription/punctuation differences). Slide a window of the quote's length.
    best, best_pos = 0.0, -1
    L = len(nq)
    if L > len(ns):
        return None
    step = max(1, L // 8)
    sm = SequenceMatcher(autojunk=False)
    sm.set_seq2(nq)
    for p in range(0, len(ns) - L + 1, step):
        sm.set_seq1(ns[p:p + L])
        if sm.quick_ratio() < min_ratio:
            continue
        r = sm.ratio()
        if r > best:
            best, best_pos = r, p
    if best >= min_ratio and best_pos >= 0:
        start, end = idx[best_pos], idx[min(best_pos + L - 1, len(idx) - 1)] + 1
        return source_text[start:end].strip(), start, end
    return None


TS_RE = re.compile(r"\[(\d+:\d{2}(?::\d{2})?)\]")


def timestamp_before(text: str, pos: int) -> str | None:
    last = None
    for m in TS_RE.finditer(text, 0, pos + 12):  # include a marker that starts at the quote itself
        last = m.group(1)
    return last
