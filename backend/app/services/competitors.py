"""Competitor research.

- Entered: the user adds a competitor name/URL. If a URL is given, the page is retrieved and visible prices
  are extracted with the retrieval date ('retrieved').
- Automated search (optional): only when web research is enabled AND a Brave Search API key is saved.
- Offline: only previously stored competitors are used and research is marked incomplete.
"""
import json
import re

from .. import db, jobs, settings_store
from ..ingest.files import html_to_text
from ..security import FetchError, safe_get

PRICE_RE = re.compile(r"(?:US)?\$\s?(\d{1,5}(?:,\d{3})*(?:\.\d{2})?)(?:\s?(?:/|per)\s?(mo|month|yr|year|week))?", re.I)


def extract_prices(text: str) -> list[str]:
    found = []
    for m in PRICE_RE.finditer(text):
        s = m.group(0).strip()
        if s not in found:
            found.append(s)
        if len(found) >= 8:
            break
    return found


def retrieve(url: str) -> dict:
    r = safe_get(url)
    if r.status >= 400:
        raise FetchError(f"HTTP {r.status}")
    text, title, meta = html_to_text(r.text)
    return {"title": title, "description": meta.get("description") or text[:300], "prices": extract_prices(text),
            "final_url": r.final_url}


def add(audience_id: str, name: str, url: str | None, price_text: str | None, opportunity_id: str | None) -> dict:
    rec = {"id": db.new_id("cp"), "audience_id": audience_id, "opportunity_id": opportunity_id, "name": name.strip()[:200],
           "url": url, "price_text": price_text, "provenance": "entered", "created_at": db.now()}
    note = None
    if url:
        try:
            info = retrieve(url)
            rec.update({"provenance": "retrieved", "retrieved_at": db.now(), "url": info["final_url"],
                        "prices_found_json": info["prices"], "description": (info["description"] or "")[:500]})
            if not price_text and info["prices"]:
                rec["price_text"] = ", ".join(info["prices"][:3])
            if not info["prices"]:
                note = "Page retrieved, but no prices were visible on it."
        except FetchError as e:
            note = f"Could not retrieve the page ({e}). Saved as entered."
    with db.tx() as c:
        db.insert(c, "competitors", rec)
        db.log_activity(c, audience_id, "competitor", f"Added competitor '{rec['name']}'")
    return {"competitor": db.one("SELECT * FROM competitors WHERE id=?", (rec["id"],)), "note": note}


@jobs.handler("competitor_search")
def competitor_search(job, progress):
    """Automated search via Brave Search API (optional key). Results are stored with URLs and dates."""
    if not settings_store.get("allow_web_research"):
        raise RuntimeError("Automated web research is off. Turn it on in Settings (requires internet).")
    key = settings_store.get_secret("brave_api_key")
    if not key:
        raise RuntimeError("Automated competitor search needs a Brave Search API key (free tier available) in Settings. "
                           "You can still add competitors manually by URL.")
    p = jobs.payload(job)
    opp = db.one("SELECT * FROM opportunities WHERE id=?", (p["opportunity_id"],))
    query = p.get("query") or f"{opp['name']} {opp['product_type']} price"
    progress(0.2, f"Searching: {query}")
    r = safe_get("https://api.search.brave.com/res/v1/web/search", params={"q": query, "count": 8}, check_robots=False,
                 headers={"X-Subscription-Token": key, "Accept": "application/json"})
    if r.status != 200:
        raise RuntimeError(f"Search API error (HTTP {r.status})")
    results = json.loads(r.text).get("web", {}).get("results", [])[:6]
    added = 0
    for i, res in enumerate(results):
        progress(0.3 + 0.6 * i / max(1, len(results)), f"Checking {res.get('url', '')[:50]}")
        try:
            info = retrieve(res["url"])
        except (FetchError, KeyError):
            continue
        with db.tx() as c:
            db.insert(c, "competitors", {
                "id": db.new_id("cp"), "audience_id": opp["audience_id"], "opportunity_id": opp["id"],
                "name": (res.get("title") or info["title"] or res["url"])[:200], "url": info["final_url"],
                "price_text": ", ".join(info["prices"][:3]) or None, "prices_found_json": info["prices"],
                "description": (res.get("description") or info["description"] or "")[:500], "provenance": "retrieved",
                "retrieved_at": db.now(), "created_at": db.now()})
        added += 1
    with db.tx() as c:
        db.log_activity(c, opp["audience_id"], "competitor", f"Web research for '{opp['name']}': {added} pages stored")
    return {"message": f"{added} competitor pages retrieved"}
