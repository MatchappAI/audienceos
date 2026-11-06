"""Job handler that processes one source (file, URL, pasted text)."""
from pathlib import Path

from .. import db, jobs
from ..security import classify_file
from . import files, store, urls


def _head(path: Path) -> bytes:
    with open(path, "rb") as f:
        return f.read(8192)


@jobs.handler("ingest_source")
def ingest_source(job, progress):
    p = jobs.payload(job)
    source = db.one("SELECT * FROM sources WHERE id=?", (job["ref_id"],))
    if not source:
        return {"message": "Source was deleted"}
    with db.tx() as c:
        c.execute("UPDATE sources SET status='processing', status_detail=NULL WHERE id=?", (source["id"],))
    progress(0.05, "Reading source")
    c = db.connect()
    try:
        # Re-processing replaces earlier extracted material from this source.
        c.execute("DELETE FROM content_items WHERE source_id=?", (source["id"],))
        c.execute("DELETE FROM comments WHERE source_id=?", (source["id"],))
        c.commit()  # never hold a write lock during slow work (downloads, transcription)
        if source["kind"] == "file":
            path = Path(source["stored_path"])
            kind = classify_file(path.name, _head(path)) if path.exists() else None
            if not kind:
                out = {"obtained": [], "missing": ["File type not supported or the file is damaged."], "status": "unsupported"}
            else:
                out = files.import_file(c, source, path, kind, progress)
            method = f"local file import ({kind or 'unknown'})"
        elif source["kind"] == "text":
            text = p.get("text", "")
            if p.get("as_comments"):
                recs = [{"text": line} for line in text.splitlines() if line.strip()]
                out = files.import_records(c, source, recs, "pasted text")
                out["missing"] = ["Dates, likes and authors (not provided with pasted text)"]
            else:
                store.add_content_item(c, source, text=text, title=source.get("title") or "Pasted text",
                                       kind=p.get("content_kind") or "document")
                out = {"obtained": [f"Text ({len(text.split()):,} words)"], "missing": [], "status": "ready" if text.strip() else "failed"}
            method = "pasted text"
        else:
            out = urls.fetch_url(c, source, source["original_url"], int(p.get("transcribe_episodes", 0)), progress)
            method = out.get("method", "web")
        n_items = c.execute("SELECT COUNT(*) FROM content_items WHERE source_id=?", (source["id"],)).fetchone()[0]
        n_comments = c.execute("SELECT COUNT(*) FROM comments WHERE source_id=?", (source["id"],)).fetchone()[0]
        title = source.get("title")
        if not title:
            t = c.execute("SELECT title FROM content_items WHERE source_id=? AND title IS NOT NULL LIMIT 1",
                          (source["id"],)).fetchone()
            title = t[0] if t else (source.get("filename") or source.get("original_url"))
        db.update(c, "sources", source["id"], {
            "status": out["status"], "retrieval_method": method, "retrieved_at": db.now(), "title": title,
            "obtained_json": out.get("obtained", []), "missing_json": out.get("missing", []),
            "alternatives_json": out.get("alternatives", []),
            "status_detail": f"{n_items} content items, {n_comments} comments"})
        db.log_activity(c, source["audience_id"], "source",
                        f"Imported '{(title or '')[:60]}' — {out['status']}")
        c.commit()
    except Exception as e:
        c.rollback()
        with db.tx() as c2:
            c2.execute("UPDATE sources SET status='failed', status_detail=? WHERE id=?", (str(e)[:500], source["id"]))
        raise
    finally:
        c.close()
    return {"message": f"Source {out['status']}"}
