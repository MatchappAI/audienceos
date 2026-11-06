"""Local sentence embeddings (Ollama ``nomic-embed-text``) for large comment sets.

Used in two places, always as an optional improvement with a deterministic fallback:
  * Sampling: when an audience has more comments than one analysis can read, comments are grouped by meaning and
    the sample is drawn from every group (most-liked first within each), so a quiet but distinct problem isn't
    crowded out by the most-liked topic. Without embeddings, the top comments by likes/recency are used.
  * Clustering: signals the model's clustering never saw (it reads at most 250) are attached to the nearest theme
    by meaning, and the rules engine groups by meaning instead of shared keywords.
Embeddings run on this Mac; nothing is sent anywhere.
"""
import logging

import httpx
import numpy as np

from .. import config, settings_store

log = logging.getLogger("audienceos.embeddings")
BATCH = 64
MAX_TEXTS = 8000
MAX_CHARS = 1500
ASSIGN_MIN_SIM = 0.55   # below this, a signal stays in "Other signals" rather than forced into a theme


def model_name() -> str:
    return settings_store.get("embedding_model") or "nomic-embed-text"


def is_installed(want: str, names: list[str]) -> bool:
    """Ollama lists 'nomic-embed-text:latest' for a model pulled as 'nomic-embed-text'."""
    return any(n == want or (":" not in want and n.split(":")[0] == want) for n in names)


def installed() -> bool:
    if not settings_store.get("use_embeddings"):
        return False
    try:
        r = httpx.get(f"{config.OLLAMA_URL}/api/tags", timeout=3)
        names = [m.get("name", "") for m in r.json().get("models", [])]
    except Exception:
        return False
    return is_installed(model_name(), names)


def embed(texts: list[str]) -> np.ndarray | None:
    """Unit-normalized embeddings (n × d), or None if the local embedding model is unavailable."""
    if not texts or not installed():
        return None
    texts = [(t or " ")[:MAX_CHARS] for t in texts[:MAX_TEXTS]]
    vecs: list[list[float]] = []
    try:
        for k in range(0, len(texts), BATCH):
            r = httpx.post(f"{config.OLLAMA_URL}/api/embed", json={"model": model_name(), "input": texts[k:k + BATCH]},
                           timeout=300)
            r.raise_for_status()
            got = r.json().get("embeddings") or []
            if len(got) != len(texts[k:k + BATCH]):
                raise ValueError("embedding count mismatch")
            vecs.extend(got)
    except Exception as e:
        log.warning("embedding failed, falling back: %s", e)
        return None
    X = np.asarray(vecs, dtype=np.float32)
    if X.ndim != 2 or X.shape[0] != len(texts):
        return None
    n = np.linalg.norm(X, axis=1, keepdims=True)
    n[n == 0] = 1
    return X / n


def _kmeans(X: np.ndarray, k: int, seed: int = 0) -> np.ndarray:
    from sklearn.cluster import KMeans
    return KMeans(n_clusters=k, n_init=4, random_state=seed).fit_predict(X)


def stratified_sample(items: list[dict], limit: int, text_key: str = "text") -> tuple[list[dict], dict] | None:
    """Pick ``limit`` items covering every meaning-group. ``items`` must already be ordered by priority
    (likes, then recency); that order is kept within each group. Returns (sample, info) or None (no embeddings)."""
    if len(items) <= limit:
        return None
    pool = items[:MAX_TEXTS]
    X = embed([str(i.get(text_key) or "") for i in pool])
    if X is None:
        return None
    k = int(max(4, min(40, round(len(pool) / 60))))
    labels = _kmeans(X, k)
    groups: dict[int, list[int]] = {}
    for idx, lab in enumerate(labels):
        groups.setdefault(int(lab), []).append(idx)  # pool order = priority order
    # Proportional quota per group, at least 3 each, then round-robin any remainder by priority.
    quota = {g: max(3, int(limit * len(ix) / len(pool))) for g, ix in groups.items()}
    chosen: list[int] = []
    for g, ix in groups.items():
        chosen.extend(ix[:quota[g]])
    if len(chosen) > limit:
        chosen = _trim(chosen, groups, limit)
    elif len(chosen) < limit:
        taken = set(chosen)
        chosen.extend([i for i in range(len(pool)) if i not in taken][:limit - len(chosen)])
    chosen = sorted(set(chosen))
    return [pool[i] for i in chosen], {"method": "embedding", "groups": len(groups), "model": model_name()}


def _trim(chosen: list[int], groups: dict[int, list[int]], limit: int) -> list[int]:
    """Drop the lowest-priority picks from the largest groups until the sample fits, keeping >=3 per group."""
    by_group = {g: [i for i in ix if i in set(chosen)] for g, ix in groups.items()}
    total = sum(len(v) for v in by_group.values())
    while total > limit:
        g = max(by_group, key=lambda x: len(by_group[x]))
        if len(by_group[g]) <= 3:
            break
        by_group[g].pop()
        total -= 1
    return [i for v in by_group.values() for i in v][:limit]


def cluster(texts: list[str], max_clusters: int = 10) -> list[list[int]] | None:
    """Group texts by meaning. Returns lists of indices, largest first, or None (no embeddings)."""
    if len(texts) < 3:
        return None
    X = embed(texts)
    if X is None:
        return None
    from sklearn.cluster import AgglomerativeClustering
    n = max(2, min(max_clusters, len(texts) // 4 or 2))
    labels = AgglomerativeClustering(n_clusters=n, metric="cosine", linkage="average").fit_predict(X)
    out: dict[int, list[int]] = {}
    for i, lab in enumerate(labels):
        out.setdefault(int(lab), []).append(i)
    return sorted(out.values(), key=len, reverse=True)


def assign(themes: list[dict], texts: list[str], unassigned: list[int]) -> dict[int, int] | None:
    """Map each unassigned signal index → theme position, by cosine similarity to the theme centroid.
    Signals below ASSIGN_MIN_SIM are left out. Returns None if embeddings are unavailable."""
    if not unassigned or not themes:
        return {}
    X = embed(texts)
    if X is None:
        return None
    cents = []
    for t in themes:
        ids = [i for i in t["signal_ids"] if 0 <= i < len(texts)]
        c = X[ids].mean(axis=0) if ids else np.zeros(X.shape[1], dtype=np.float32)
        nrm = np.linalg.norm(c)
        cents.append(c / nrm if nrm else c)
    C = np.stack(cents)
    out = {}
    for i in unassigned:
        sims = C @ X[i]
        j = int(np.argmax(sims))
        if float(sims[j]) >= ASSIGN_MIN_SIM:
            out[i] = j
    return out
