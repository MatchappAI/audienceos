"""File importers. Each returns a dict of what was obtained and what is missing."""
import csv
import io
import json
import logging
from pathlib import Path

from bs4 import BeautifulSoup

from .. import config, db
from ..ai import providers
from . import media, ocr, store

log = logging.getLogger("audienceos.files")

METRIC_COLS = {"views": "views", "plays": "views", "impressions": "impressions", "reach": "reach",
               "likes": "likes", "comments": "comments", "shares": "shares", "saves": "saves",
               "watch_time": "watch_time", "opens": "opens", "open_rate": "open_rate", "clicks": "clicks",
               "click_rate": "click_rate", "subscribers": "subscribers", "followers": "followers"}


def html_to_text(html: str) -> tuple[str, str | None, dict]:
    soup = BeautifulSoup(html, "lxml")
    meta = {}
    title = soup.title.string.strip() if soup.title and soup.title.string else None
    for tag, key in (("og:title", "og_title"), ("description", "description"), ("og:description", "description"),
                     ("article:published_time", "published"), ("og:site_name", "site")):
        m = soup.find("meta", attrs={"property": tag}) or soup.find("meta", attrs={"name": tag})
        if m and m.get("content"):
            meta.setdefault(key, m["content"].strip()[:500])
    if not meta.get("published"):
        t = soup.find("time", attrs={"datetime": True})
        if t:
            meta["published"] = t["datetime"]
    feeds = [l.get("href") for l in soup.find_all("link", attrs={"type": ["application/rss+xml", "application/atom+xml"]})
             if l.get("href")]
    if feeds:
        meta["feeds"] = feeds[:3]
    for t in soup(["script", "style", "noscript", "svg", "nav", "footer", "header", "aside", "form", "iframe", "button"]):
        t.decompose()
    root = soup.find("article") or soup.find("main") or soup.body or soup
    blocks = []
    for el in root.find_all(["h1", "h2", "h3", "h4", "p", "li", "blockquote", "pre", "td"]):
        txt = " ".join(el.get_text(" ", strip=True).split())
        if txt and (len(txt) > 2):
            blocks.append(txt)
    text = "\n".join(dict.fromkeys(blocks))  # de-duplicate repeated blocks, keep order
    if len(text) < 200:
        text = " ".join(root.get_text(" ", strip=True).split())
    return text, title or meta.get("og_title"), meta


def import_text(c, source, path: Path, kind: str):
    raw = path.read_text(errors="replace")
    title = source.get("title") or path.stem
    if kind == "html":
        text, t2, meta = html_to_text(raw)
        title = t2 or title
    else:
        text, meta = raw, {}
    if not text.strip():
        return {"obtained": [], "missing": ["The file contains no readable text."], "status": "failed"}
    store.add_content_item(c, source, text=text, title=title, kind="newsletter" if source["platform"] in ("newsletter", "substack") else "document",
                           published_at=store.parse_date(meta.get("published")), metadata=meta)
    return {"obtained": [f"Text ({len(text.split()):,} words)"], "missing": [], "status": "ready"}


MIN_OCR_CONFIDENCE = 0.3


def _ocr_pages(path: Path, pages: list[int] | None) -> tuple[dict[int, str], str | None]:
    """Run on-device OCR. Returns ({page: text}, note-if-unavailable-or-failed)."""
    try:
        res = ocr.recognize(path, pages)
    except ocr.OCRUnavailable as e:
        return {}, str(e)
    except Exception as e:  # OCR is best-effort; never fail the whole import
        log.warning("OCR failed for %s: %s", path.name, e)
        return {}, f"Text recognition (OCR) failed: {e}"
    out = {}
    for r in res:
        t = str(r.get("text") or "").strip()
        if t and float(r.get("confidence") or 0) >= MIN_OCR_CONFIDENCE:
            out[int(r.get("page") or 1)] = t
    return out, None


def import_pdf(c, source, path: Path):
    from pypdf import PdfReader
    reader = PdfReader(str(path))
    n = len(reader.pages)
    by_page: dict[int, str] = {}
    for i, p in enumerate(reader.pages):
        t = (p.extract_text() or "").strip()
        if t:
            by_page[i + 1] = t
    no_layer = [i for i in range(1, n + 1) if i not in by_page]
    ocr_pages: dict[int, str] = {}
    note = None
    if no_layer:
        ocr_pages, note = _ocr_pages(path, None if len(no_layer) == n else no_layer)
        ocr_pages = {k: v for k, v in ocr_pages.items() if k in no_layer}
    parts = []
    for i in range(1, n + 1):
        if i in by_page:
            parts.append(f"[page {i}]\n{by_page[i]}")
        elif i in ocr_pages:
            parts.append(f"[page {i}, text recognized by OCR]\n{ocr_pages[i]}")
    text = "\n\n".join(parts)
    if not text.strip():
        missing = ["No text layer (this looks like a scanned PDF)."]
        missing.append(note or "Text recognition (OCR) found no readable text on any page.")
        return {"obtained": [f"{n} pages"], "missing": missing, "status": "failed"}
    store.add_content_item(c, source, text=text, title=source.get("title") or path.stem, kind="document",
                           metadata={"pages": n, "ocr_pages": sorted(ocr_pages)})
    obtained = [f"Text from {len(by_page)} of {n} pages"] if by_page else []
    if ocr_pages:
        obtained.append(f"Text recognized on this Mac (OCR) from {len(ocr_pages)} scanned page{'s' if len(ocr_pages) != 1 else ''} — "
                        "check quotes against the original")
    unread = len(no_layer) - len(ocr_pages)
    missing = []
    if unread:
        missing.append(f"{unread} page{'s' if unread != 1 else ''} had no text layer"
                       + (f" — {note}" if note else " and no readable text was recognized"))
    return {"obtained": obtained, "status": "ready", "missing": missing}


def import_docx(c, source, path: Path):
    import docx
    d = docx.Document(str(path))
    parts = [p.text for p in d.paragraphs if p.text.strip()]
    for t in d.tables:
        for r in t.rows:
            parts.append(" | ".join(cell.text.strip() for cell in r.cells))
    text = "\n".join(parts)
    if not text.strip():
        return {"obtained": [], "missing": ["The document contains no text."], "status": "failed"}
    store.add_content_item(c, source, text=text, title=source.get("title") or path.stem, kind="document")
    return {"obtained": [f"Text ({len(text.split()):,} words)"], "missing": [], "status": "ready"}


def _table_records(path: Path) -> list[dict]:
    raw = path.read_text(errors="replace")
    dialect = csv.excel_tab if path.suffix.lower() == ".tsv" else csv.excel
    try:
        sniffed = csv.Sniffer().sniff(raw[:5000], delimiters=",;\t")
        dialect = sniffed
    except csv.Error:
        pass
    return [dict(r) for r in csv.DictReader(io.StringIO(raw), dialect=dialect)][:50_000]


def import_records(c, source, records: list[dict], label: str):
    if not records:
        return {"obtained": [], "missing": [f"No rows found in the {label}."], "status": "failed"}
    keys = {str(k).strip().lower().replace(" ", "_") for k in records[0]}
    if any(store.has_text_key(r) for r in records[:50]):
        counts = store.add_comments(c, source, records)
        store_link_comments(c, source["audience_id"])
        obtained = [f"{counts['added']:,} comments/messages"]
        if counts["duplicates"]:
            obtained.append(f"{counts['duplicates']:,} flagged as duplicates (not counted as independent people)")
        if counts["spam"]:
            obtained.append(f"{counts['spam']:,} flagged as likely spam")
        missing = []
        if not any(store.pick(r, store.DATE_KEYS) for r in records[:50]):
            missing.append("Comment dates (no date column found) — recency cannot be measured")
        if not any(store.pick(r, store.LIKE_KEYS) for r in records[:50]):
            missing.append("Likes per comment")
        if counts["skipped"]:
            missing.append(f"{counts['skipped']:,} rows had no text and were skipped")
        return {"obtained": obtained, "missing": missing, "status": "ready" if counts["added"] else "failed"}
    metric_keys = [k for k in keys if k in METRIC_COLS]
    if metric_keys and (keys & {"title", "url", "post", "video", "name", "content", "permalink", "link", "post_title"}):
        n = 0
        for r in records:
            title = store.pick(r, ("title", "post_title", "name", "post", "video"))
            url = store.pick(r, ("url", "permalink", "link"))
            text = str(title or url or "")
            cid, _ = store.add_content_item(c, source, text=f"{text}", title=str(title or url)[:200], kind="post",
                                            url=str(url) if url else None,
                                            published_at=store.parse_date(store.pick(r, store.DATE_KEYS)),
                                            metadata={"from": "analytics export"})
            low = {str(k).strip().lower().replace(" ", "_"): v for k, v in r.items()}
            for k in metric_keys:
                store.add_metric(c, cid, METRIC_COLS[k], store.to_int(low.get(k)), f"Imported from {source.get('filename')}")
            n += 1
        return {"obtained": [f"Engagement metrics for {n:,} content items ({', '.join(sorted(metric_keys))})"],
                "missing": ["Comment text (this file holds metrics only)"], "status": "ready"}
    # Generic table: keep as a readable document.
    lines = [" | ".join(f"{k}: {v}" for k, v in r.items() if v not in (None, "")) for r in records[:3000]]
    store.add_content_item(c, source, text="\n".join(lines), title=source.get("title") or source.get("filename"),
                           kind="document", metadata={"rows": len(records)})
    return {"obtained": [f"Table with {len(records):,} rows (stored as text)"],
            "missing": ["No comment-text or recognizable metric columns were found"], "status": "partial"}


def store_link_comments(c, audience_id: str):
    c.execute("""UPDATE comments SET content_item_id = (
                   SELECT ci.id FROM content_items ci WHERE ci.audience_id = comments.audience_id
                   AND ci.url IS NOT NULL AND ci.url = comments.parent_ref LIMIT 1)
                 WHERE audience_id=? AND content_item_id IS NULL AND parent_ref IS NOT NULL""", (audience_id,))


def import_csv(c, source, path: Path):
    return import_records(c, source, _table_records(path), "CSV file")


def import_json(c, source, path: Path):
    try:
        data = json.loads(path.read_text(errors="replace"))
    except ValueError as e:
        return {"obtained": [], "missing": [f"The JSON file is malformed ({e})."], "status": "failed"}
    recs = store.find_records(data)
    if recs:
        return import_records(c, source, recs, "JSON file")
    text = json.dumps(data, indent=1)[:200_000]
    store.add_content_item(c, source, text=text, title=source.get("title") or path.stem, kind="document")
    return {"obtained": ["JSON stored as text"], "missing": ["No list of comments/messages was found"], "status": "partial"}


def describe_frames(c, content_item_id: str, frames) -> tuple[int, str | None]:
    vp = providers.vision_provider()
    if not vp:
        return 0, None
    n = 0
    for fid, t, path in frames:
        try:
            desc = vp._chat("Describe this image in one or two factual sentences: what is shown, any on-screen "
                            "text, any products visible. No speculation. " + providers.UNTRUSTED_NOTICE,
                            "Describe this frame.", None, [path], 200)
        except Exception as e:  # vision is best-effort
            log.warning("frame description failed: %s", e)
            continue
        c.execute("UPDATE media_frames SET description=?, described_by=? WHERE id=?", (desc.strip()[:600], vp.label, fid))
        n += 1
    return n, vp.label


def import_media(c, source, path: Path, kind: str, progress):
    obtained, missing = [], []
    work = config.MEDIA_DIR / source["id"]
    work.mkdir(parents=True, exist_ok=True)
    duration = media.probe_duration(path)
    meta = {"duration_s": duration, "filename": source.get("filename")}
    transcript = None
    if media.has_audio_stream(path):
        progress(0.1, "Extracting audio")
        wav = media.extract_audio(path, work / "audio.wav")
        progress(0.2, "Transcribing speech on this Mac")
        transcript = media.transcribe(wav, lambda f: progress(0.2 + 0.6 * f, "Transcribing speech on this Mac"))
        wav.unlink(missing_ok=True)
        if transcript["text"]:
            obtained.append(f"Transcript ({len(transcript['text'].split()):,} words, {transcript['language'] or 'unknown'} language, timestamps kept)")
        else:
            missing.append("No speech detected in the audio")
    else:
        missing.append("No audio track")
    text = media.transcript_with_timestamps(transcript["segments"]) if transcript and transcript["text"] else ""
    cid, created = store.add_content_item(c, source, text=text, title=source.get("title") or path.stem,
                                          kind="video" if kind == "video" else "audio", metadata=meta)
    if not created:
        return {"obtained": ["Identical transcript already imported for this audience"], "missing": [], "status": "ready"}
    if transcript and transcript["text"]:
        db.insert(c, "transcripts", {"id": db.new_id("tr"), "content_item_id": cid, "engine": transcript["engine"],
                                     "language": transcript["language"], "text": transcript["text"],
                                     "segments_json": transcript["segments"], "created_at": db.now()})
    c.commit()
    if kind == "video":
        progress(0.85, "Sampling video frames")
        frames = media.sample_frames(path, work / "frames", duration)
        recs = []
        for t, p in frames:
            fid = db.new_id("fr")
            db.insert(c, "media_frames", {"id": fid, "content_item_id": cid, "timestamp_s": t, "path": str(p),
                                          "created_at": db.now()})
            recs.append((fid, t, p))
        obtained.append(f"{len(frames)} sample frames")
        n, by = describe_frames(c, cid, recs)
        if n:
            obtained.append(f"Visual descriptions for {n} frames ({by})")
        else:
            missing.append("Visual analysis (no vision-capable model configured — optional, see Settings)")
    status = "ready" if text else ("partial" if kind == "video" else "failed")
    return {"obtained": obtained, "missing": missing, "status": status}


def import_image(c, source, path: Path):
    texts, note = _ocr_pages(path, None)
    text = texts.get(1, "")
    cid, _ = store.add_content_item(c, source, text=text, title=source.get("title") or path.stem, kind="image",
                                    metadata={"filename": source.get("filename"), "ocr": bool(text)})
    fid = db.new_id("fr")
    db.insert(c, "media_frames", {"id": fid, "content_item_id": cid, "timestamp_s": 0, "path": str(path),
                                  "created_at": db.now()})
    n, by = describe_frames(c, cid, [(fid, 0, path)])
    obtained, missing = [], []
    if text:
        obtained.append(f"Text recognized on this Mac (OCR, {len(text.split()):,} words) — check quotes against the image")
    else:
        missing.append(note or "No readable text in the image (OCR)")
    if n:
        obtained.append(f"Image description ({by})")
    else:
        missing.append("Visual description — no vision-capable model configured (optional, see Settings)")
    if not obtained:
        obtained.append("Image stored")
    return {"obtained": obtained, "missing": missing, "status": "ready" if (text or n) else "partial"}


def import_file(c, source, path: Path, kind: str, progress):
    if kind in ("text", "html"):
        return import_text(c, source, path, kind)
    if kind == "pdf":
        return import_pdf(c, source, path)
    if kind == "docx":
        return import_docx(c, source, path)
    if kind == "csv":
        return import_csv(c, source, path)
    if kind == "json":
        return import_json(c, source, path)
    if kind in ("audio", "video"):
        return import_media(c, source, path, kind, progress)
    if kind == "image":
        return import_image(c, source, path)
    return {"obtained": [], "missing": ["Unsupported file type"], "status": "unsupported"}
