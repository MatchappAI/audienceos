"""API: audiences, channels, sources, analysis, intelligence, library, settings, jobs, dashboard."""
import hashlib
import json
import shutil
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from .. import cleanup, config, db, jobs, settings_store
from ..ai import providers
from ..ingest import media, ocr, platforms
from ..security import classify_file, safe_filename
from ..services import intel

r = APIRouter(prefix="/api")


def must(row, what="Item"):
    if not row:
        raise HTTPException(404, f"{what} not found")
    return row


# ---------- system & settings ----------

@r.get("/health")
def health():
    return {"ok": True}


@r.get("/system")
def system():
    return {"providers": providers.status_all(), "active_provider": settings_store.get("ai_provider"),
            "media": {**media.status(), "ocr": ocr.available()}, "settings": settings_store.get_all(),
            "data_dir": str(config.DATA_DIR),
            "version": "1.2.0"}


class SettingsIn(BaseModel):
    values: dict


@r.put("/settings")
def put_settings(body: SettingsIn):
    try:
        settings_store.set_many(body.values)
    except ValueError as e:
        raise HTTPException(400, str(e))
    if "rubric" in body.values:
        from ..services import scoring
        with db.tx() as c:
            for o in db.rows(c.execute("SELECT id, scores_json FROM opportunities").fetchall()):
                c.execute("UPDATE opportunities SET total_score=? WHERE id=?", (scoring.total(o["scores"] or {}), o["id"]))
    return settings_store.get_all()


class SecretIn(BaseModel):
    value: str | None = None


@r.put("/secrets/{name}")
def put_secret(name: str, body: SecretIn):
    if name not in settings_store.SECRET_NAMES:
        raise HTTPException(400, "Unknown key name")
    settings_store.set_secret(name, (body.value or "").strip() or None)
    return {"saved": bool(body.value), "name": name}


class PullIn(BaseModel):
    model: str = Field(pattern=r"^[\w.\-:/]+$", max_length=80)
    purpose: str | None = Field(default=None, pattern=r"^(analysis|vision|embedding)$")


# One-click optional local models. Sizes are the Ollama library's download sizes (approximate).
MODEL_PRESETS = [
    {"model": "qwen2.5vl:3b", "purpose": "vision", "size": "~3.2 GB",
     "title": "Vision model (recommended)", "detail": "Describes video frames and images on this Mac."},
    {"model": "qwen2.5vl:7b", "purpose": "vision", "size": "~6 GB",
     "title": "Vision model (higher quality)", "detail": "Better descriptions; slower and needs more memory."},
    {"model": "nomic-embed-text", "purpose": "embedding", "size": "~270 MB",
     "title": "Embedding model", "detail": "Groups large comment sets by meaning so quiet problems aren't missed."},
]


@r.get("/models/presets")
def model_presets():
    from ..ai import embeddings
    try:
        names = providers.OllamaProvider().installed_models()
        running = True
    except Exception:
        names, running = [], False
    active = {jobs.payload(j).get("model"): j["id"] for j in db.all_(
        "SELECT * FROM jobs WHERE kind='pull_model' AND status IN ('queued','running')")}
    out = []
    for p in MODEL_PRESETS:
        inst = embeddings.is_installed(p["model"], names)
        in_use = (settings_store.get("ollama_vision_model") == p["model"] if p["purpose"] == "vision"
                  else embeddings.is_installed(settings_store.get("embedding_model"), [p["model"]]))
        out.append({**p, "installed": inst, "in_use": inst and in_use, "job_id": active.get(p["model"])})
    return {"engine_running": running, "presets": out}


@r.post("/models/pull")
def pull_model(body: PullIn):
    existing = db.one("SELECT id FROM jobs WHERE kind='pull_model' AND status IN ('queued','running') AND "
                      "json_extract(payload_json,'$.model')=?", (body.model,))
    if existing:
        return {"job_id": existing["id"]}
    return {"job_id": jobs.enqueue("pull_model", payload={"model": body.model, "purpose": body.purpose}, max_attempts=1,
                                   message=f"Downloading {body.model}")}


def _use_pulled_model(model: str, purpose: str | None) -> str:
    """After a one-click download, switch the matching setting to it if nothing is configured yet."""
    if purpose == "vision" and not settings_store.get("ollama_vision_model"):
        settings_store.set_many({"ollama_vision_model": model})
        return " and set as the vision model"
    if purpose == "embedding":
        settings_store.set_many({"embedding_model": model, "use_embeddings": True})
        return " and turned on for large comment sets"
    return ""


@jobs.handler("pull_model")
def _pull(job, progress):
    import httpx
    p = jobs.payload(job)
    model = p["model"]
    layers: dict[str, tuple[int, int]] = {}  # digest → (completed, total); Ollama reports each layer separately
    try:
        with httpx.stream("POST", f"{config.OLLAMA_URL}/api/pull", json={"model": model}, timeout=None) as resp:
            if resp.status_code >= 400:
                resp.read()
                raise RuntimeError(f"Download failed ({resp.status_code}): {resp.text[:200]}")
            done = False
            for line in resp.iter_lines():
                if not line:
                    continue
                d = json.loads(line)
                if d.get("error"):
                    raise RuntimeError(d["error"])
                if d.get("total") and d.get("digest"):
                    layers[d["digest"]] = (int(d.get("completed") or 0), int(d["total"]))
                    got, tot = sum(c for c, _ in layers.values()), sum(t for _, t in layers.values())
                    progress(min(0.99, got / tot) if tot else 0, f"Downloading {model} ({got / 1e9:.1f} of {tot / 1e9:.1f} GB)")
                elif d.get("status"):
                    if d["status"] == "success":
                        done = True
                    progress(0.99 if layers else 0, f"{model}: {d['status']}")
    except httpx.ConnectError as e:
        raise RuntimeError("The local AI engine (Ollama) is not running. Restart AudienceOS with the launcher.") from e
    if not done:
        raise RuntimeError(f"The download of {model} ended before it finished. Try again.")
    return {"message": f"{model} downloaded{_use_pulled_model(model, p.get('purpose'))}"}


@r.get("/platforms")
def get_platforms():
    return {"platforms": platforms.PLATFORMS, "upload_platforms": platforms.UPLOAD_PLATFORMS}


class DetectIn(BaseModel):
    url: str


@r.post("/detect")
def detect(body: DetectIn):
    p = platforms.detect(body.url.strip())
    return {"platform": p, "policy": platforms.policy(p)}


# ---------- dashboard ----------

@r.get("/dashboard")
def dashboard():
    q = db.scalar
    real = "(SELECT id FROM audiences WHERE is_demo=0)"
    stats = {
        "audiences": q("SELECT COUNT(*) FROM audiences WHERE status='active'"),
        "audiences_analyzed": q("SELECT COUNT(*) FROM audiences WHERE last_analyzed_at IS NOT NULL"),
        "active_projects": q("SELECT COUNT(DISTINCT audience_id) FROM sources WHERE created_at > datetime('now','-30 days')"),
        "opportunities": q("SELECT COUNT(*) FROM opportunities WHERE status != 'rejected'"),
        "awaiting_validation": q("SELECT COUNT(*) FROM opportunities WHERE status IN ('proposed','approved')"),
        "validated": q("SELECT COUNT(*) FROM opportunities WHERE status='validated'"),
        "active_experiments": q("SELECT COUNT(*) FROM experiments WHERE status='running'"),
        "sales": None, "revenue": None,
    }
    from ..services import experiments as ex
    sales = revenue = 0.0
    demo_sales = 0
    for x in db.all_("SELECT * FROM experiments"):
        m = ex.compute(x, db.all_("SELECT * FROM experiment_events WHERE experiment_id=?", (x["id"],)),
                       db.all_("SELECT * FROM orders WHERE experiment_id=?", (x["id"],)))
        v = m["values"]
        if v["purchases"] is not None:
            if x["is_demo"]:
                demo_sales += v["purchases"]
            else:
                sales += v["purchases"]
                revenue += v["net_sales"] or 0
    stats["sales"], stats["revenue"], stats["demo_sales"] = int(sales), round(revenue, 2), demo_sales
    # Launched products (agency): real recorded sales, excluding demo data.
    from ..services import agency
    prod_net = prod_orders = 0.0
    for p in db.all_("SELECT * FROM products WHERE is_demo=0"):
        pnl = agency.product_pnl(p)
        prod_net += pnl["net_sales"]
        prod_orders += pnl["orders"]
    owed = 0.0
    for o in db.all_("SELECT id FROM organizations WHERE is_demo=0"):
        b = agency.statement(o["id"])["balance_owed"]
        owed += b or 0
    stats.update({"product_orders": int(prod_orders), "product_net_sales": round(prod_net, 2),
                  "creator_balance_owed": round(owed, 2),
                  "launched_products": q("SELECT COUNT(*) FROM products WHERE status='launched' AND is_demo=0")})
    stats["has_demo"] = bool(q("SELECT COUNT(*) FROM audiences WHERE is_demo=1"))
    activity = db.all_("SELECT a.*, au.name AS audience_name FROM activity a LEFT JOIN audiences au ON au.id=a.audience_id "
                       "ORDER BY a.created_at DESC LIMIT 15")
    return {"stats": stats, "activity": activity, "next_actions": next_actions(),
            "active_jobs": db.all_("SELECT j.*, a.name AS audience_name FROM jobs j LEFT JOIN audiences a ON a.id=j.audience_id "
                                   "WHERE j.status IN ('queued','running') ORDER BY j.created_at")}


def next_actions() -> list[dict]:
    out = []
    p = providers.get_provider()
    ok, why = p.available()
    if not ok:
        out.append({"kind": "setup", "text": f"AI provider not ready: {why}", "link": "/settings"})
    for a in db.all_("""SELECT a.id, a.name, a.last_analyzed_at,
                          (SELECT COUNT(*) FROM sources s WHERE s.audience_id=a.id AND s.status IN ('ready','partial')) AS ready,
                          (SELECT MAX(created_at) FROM sources s WHERE s.audience_id=a.id) AS last_source,
                          (SELECT COUNT(*) FROM comments c WHERE c.audience_id=a.id) AS comments,
                          (SELECT COUNT(*) FROM jobs j WHERE j.audience_id=a.id AND j.kind='analyze_audience'
                             AND j.status IN ('queued','running')) AS analyzing
                        FROM audiences a WHERE a.status='active' ORDER BY a.updated_at DESC LIMIT 20"""):
        if a["analyzing"]:
            out.append({"kind": "analyze", "text": f"Analysis running for {a['name']} — you can keep working; results appear here when it finishes",
                        "link": f"/audiences/{a['id']}"})
        elif a["ready"] == 0:
            out.append({"kind": "import", "text": f"Add content or comments to {a['name']}", "link": f"/audiences/{a['id']}/sources"})
        elif not a["last_analyzed_at"]:
            out.append({"kind": "analyze", "text": f"Run the first analysis for {a['name']}", "link": f"/audiences/{a['id']}"})
        elif a["last_source"] and a["last_source"] > a["last_analyzed_at"]:
            out.append({"kind": "analyze", "text": f"New material in {a['name']} — reanalyze", "link": f"/audiences/{a['id']}"})
        elif a["comments"] == 0:
            out.append({"kind": "import", "text": f"Import audience comments for {a['name']} (stronger evidence)",
                        "link": f"/audiences/{a['id']}/sources"})
    for o in db.all_("SELECT o.id, o.name, o.audience_id FROM opportunities o WHERE o.status='approved' AND NOT EXISTS "
                     "(SELECT 1 FROM experiments e WHERE e.opportunity_id=o.id) LIMIT 5"):
        out.append({"kind": "experiment", "text": f"Design a validation test for '{o['name']}'", "link": f"/opportunities/{o['id']}"})
    for x in db.all_("SELECT id, name FROM experiments WHERE status='running' AND end_date IS NOT NULL AND end_date < date('now') "
                     "AND decision IS NULL"):
        out.append({"kind": "decide", "text": f"'{x['name']}' has ended — record a decision", "link": f"/validation/{x['id']}"})
    # After an analysis: review what it proposed.
    for a in db.all_("SELECT a.id, a.name, COUNT(*) AS n FROM opportunities o JOIN audiences a ON a.id=o.audience_id "
                     "WHERE o.status='proposed' AND a.status='active' GROUP BY a.id ORDER BY MAX(o.created_at) DESC LIMIT 3"):
        out.append({"kind": "experiment", "text": f"Review {a['n']} proposed opportunit{'y' if a['n'] == 1 else 'ies'} for {a['name']} — approve the best for testing",
                    "link": f"/audiences/{a['id']}/opportunities"})
    for x in db.all_("SELECT x.id, x.name FROM experiments x WHERE x.decision IS NULL AND (EXISTS (SELECT 1 FROM experiment_events e "
                     "WHERE e.experiment_id=x.id) OR EXISTS (SELECT 1 FROM orders r WHERE r.experiment_id=x.id)) "
                     "AND NOT (x.status='running' AND x.end_date IS NOT NULL AND x.end_date < date('now')) LIMIT 3"):
        out.append({"kind": "decide", "text": f"'{x['name']}' has results — review and record go / revise / stop", "link": f"/validation/{x['id']}"})
    for o in db.all_("SELECT o.id, o.name FROM opportunities o WHERE o.status='validated' AND NOT EXISTS "
                     "(SELECT 1 FROM products p WHERE p.opportunity_id=o.id) LIMIT 3"):
        out.append({"kind": "experiment", "text": f"'{o['name']}' is validated — create the product and its launch checklist", "link": f"/opportunities/{o['id']}"})
    for pr in db.all_("SELECT p.id, p.name, p.status, p.launched_at, (SELECT COUNT(*) FROM product_sales s WHERE s.product_id=p.id) AS n "
                      "FROM products p WHERE p.status IN ('draft','approved','launched') ORDER BY p.updated_at DESC LIMIT 6"):
        if pr["status"] == "draft" and (pr["launched_at"] or pr["n"]):
            out.append({"kind": "decide", "text": f"'{pr['name']}' changed after launch — re-approve it", "link": f"/products/{pr['id']}"})
        elif pr["status"] == "approved":
            out.append({"kind": "decide", "text": f"'{pr['name']}' is approved — mark it launched once it's live on the storefront", "link": f"/products/{pr['id']}"})
        elif pr["status"] == "launched" and not pr["n"]:
            out.append({"kind": "import", "text": f"'{pr['name']}' is live — import its first orders from the checkout", "link": f"/products/{pr['id']}"})
    return out[:8]


# ---------- audiences ----------

class ChannelIn(BaseModel):
    platform: str = "other"
    handle: str | None = None
    url: str | None = None
    follower_count: int | None = Field(default=None, ge=0)


class AudienceIn(BaseModel):
    org_name: str = Field(min_length=1, max_length=200)
    org_kind: str = "creator"
    name: str | None = None
    niche: str | None = None
    description: str | None = None
    channels: list[ChannelIn] = []


@r.get("/audiences")
def list_audiences():
    return db.all_("""SELECT a.*, o.name AS org_name, o.kind AS org_kind,
        (SELECT COUNT(*) FROM sources s WHERE s.audience_id=a.id) AS source_count,
        (SELECT COUNT(*) FROM comments c WHERE c.audience_id=a.id AND c.is_duplicate=0) AS comment_count,
        (SELECT COUNT(*) FROM opportunities op WHERE op.audience_id=a.id AND op.status!='rejected') AS opportunity_count,
        (SELECT COUNT(*) FROM experiments e WHERE e.audience_id=a.id) AS experiment_count,
        (SELECT SUM(follower_count) FROM channels ch WHERE ch.audience_id=a.id) AS audience_size,
        (SELECT GROUP_CONCAT(DISTINCT platform) FROM channels ch WHERE ch.audience_id=a.id) AS platforms
        FROM audiences a JOIN organizations o ON o.id=a.organization_id ORDER BY a.updated_at DESC""")


@r.post("/audiences")
def create_audience(body: AudienceIn):
    now = db.now()
    with db.tx() as c:
        org = c.execute("SELECT id FROM organizations WHERE lower(name)=lower(?) AND is_demo=0", (body.org_name.strip(),)).fetchone()
        org_id = org[0] if org else db.insert(c, "organizations", {
            "id": db.new_id("org"), "workspace_id": "ws_default", "name": body.org_name.strip(),
            "kind": body.org_kind if body.org_kind in ("creator", "business", "publisher", "community", "other") else "other",
            "description": body.description, "created_at": now, "updated_at": now})
        aid = db.insert(c, "audiences", {"id": db.new_id("aud"), "organization_id": org_id,
                                         "name": (body.name or f"{body.org_name.strip()} audience").strip(),
                                         "niche": body.niche, "description": body.description,
                                         "created_at": now, "updated_at": now})
        for ch in body.channels:
            db.insert(c, "channels", {"id": db.new_id("ch"), "audience_id": aid, "platform": ch.platform,
                                      "handle": ch.handle, "url": ch.url, "follower_count": ch.follower_count,
                                      "follower_count_source": "entered by you" if ch.follower_count is not None else None,
                                      "created_at": now})
        db.log_activity(c, aid, "audience", f"Created audience '{body.org_name}'")
    return get_audience(aid)


@r.get("/audiences/{aid}")
def get_audience(aid: str):
    a = must(db.one("SELECT a.*, o.name AS org_name, o.kind AS org_kind, o.id AS org_id FROM audiences a "
                    "JOIN organizations o ON o.id=a.organization_id WHERE a.id=?", (aid,)), "Audience")
    a["channels"] = db.all_("SELECT * FROM channels WHERE audience_id=? ORDER BY created_at", (aid,))
    a["counts"] = {
        "sources": db.scalar("SELECT COUNT(*) FROM sources WHERE audience_id=?", (aid,)),
        "content_items": db.scalar("SELECT COUNT(*) FROM content_items WHERE audience_id=?", (aid,)),
        "words": db.scalar("SELECT COALESCE(SUM(word_count),0) FROM content_items WHERE audience_id=?", (aid,)),
        "comments": db.scalar("SELECT COUNT(*) FROM comments WHERE audience_id=? AND is_duplicate=0 AND is_spam=0", (aid,)),
        "transcripts": db.scalar("SELECT COUNT(*) FROM transcripts t JOIN content_items ci ON ci.id=t.content_item_id WHERE ci.audience_id=?", (aid,)),
        "opportunities": db.scalar("SELECT COUNT(*) FROM opportunities WHERE audience_id=? AND status!='rejected'", (aid,)),
        "experiments": db.scalar("SELECT COUNT(*) FROM experiments WHERE audience_id=?", (aid,)),
        "reports": db.scalar("SELECT COUNT(*) FROM reports WHERE audience_id=?", (aid,)),
    }
    a["audience_size"] = db.scalar("SELECT SUM(follower_count) FROM channels WHERE audience_id=?", (aid,))
    a["jobs"] = db.all_("SELECT * FROM jobs WHERE audience_id=? ORDER BY created_at DESC LIMIT 20", (aid,))
    a["latest_analysis"] = intel.latest_analysis(aid, done_only=False)
    return a


class AudiencePatch(BaseModel):
    name: str | None = None
    niche: str | None = None
    description: str | None = None
    status: str | None = None
    org_name: str | None = None


@r.patch("/audiences/{aid}")
def patch_audience(aid: str, body: AudiencePatch):
    a = must(db.one("SELECT * FROM audiences WHERE id=?", (aid,)), "Audience")
    d = body.model_dump(exclude_none=True)
    org_name = d.pop("org_name", None)
    with db.tx() as c:
        db.update(c, "audiences", aid, {**d, "updated_at": db.now()})
        if org_name:
            c.execute("UPDATE organizations SET name=?, updated_at=? WHERE id=?", (org_name, db.now(), a["organization_id"]))
    return get_audience(aid)


@r.delete("/audiences/{aid}")
def delete_audience(aid: str):
    a = must(db.one("SELECT * FROM audiences WHERE id=?", (aid,)), "Audience")
    dirs = cleanup.audience_dirs([aid])
    with db.tx() as c:
        c.execute("DELETE FROM audiences WHERE id=?", (aid,))
        if not c.execute("SELECT 1 FROM audiences WHERE organization_id=?", (a["organization_id"],)).fetchone():
            c.execute("DELETE FROM organizations WHERE id=?", (a["organization_id"],))
    cleanup.purge(dirs)
    return {"deleted": True}


@r.post("/audiences/{aid}/channels")
def add_channel(aid: str, body: ChannelIn):
    must(db.one("SELECT id FROM audiences WHERE id=?", (aid,)), "Audience")
    with db.tx() as c:
        db.insert(c, "channels", {"id": db.new_id("ch"), "audience_id": aid, "platform": body.platform,
                                  "handle": body.handle, "url": body.url, "follower_count": body.follower_count,
                                  "follower_count_source": "entered by you" if body.follower_count is not None else None,
                                  "created_at": db.now()})
    return get_audience(aid)


@r.patch("/channels/{cid}")
def patch_channel(cid: str, body: ChannelIn):
    ch = must(db.one("SELECT * FROM channels WHERE id=?", (cid,)), "Channel")
    d = body.model_dump()
    if body.follower_count is not None:
        d["follower_count_source"] = "entered by you"
    with db.tx() as c:
        db.update(c, "channels", cid, d)
    return get_audience(ch["audience_id"])


@r.delete("/channels/{cid}")
def delete_channel(cid: str):
    ch = must(db.one("SELECT * FROM channels WHERE id=?", (cid,)), "Channel")
    with db.tx() as c:
        c.execute("DELETE FROM channels WHERE id=?", (cid,))
    return get_audience(ch["audience_id"])


# ---------- sources ----------

@r.get("/audiences/{aid}/sources")
def list_sources(aid: str):
    return db.all_("""SELECT s.*, (SELECT COUNT(*) FROM content_items ci WHERE ci.source_id=s.id) AS items,
        (SELECT COUNT(*) FROM comments cm WHERE cm.source_id=s.id) AS comments,
        (SELECT status FROM jobs j WHERE j.ref_id=s.id ORDER BY created_at DESC LIMIT 1) AS job_status,
        (SELECT progress FROM jobs j WHERE j.ref_id=s.id ORDER BY created_at DESC LIMIT 1) AS job_progress,
        (SELECT message FROM jobs j WHERE j.ref_id=s.id ORDER BY created_at DESC LIMIT 1) AS job_message,
        (SELECT error FROM jobs j WHERE j.ref_id=s.id ORDER BY created_at DESC LIMIT 1) AS job_error
        FROM sources s WHERE s.audience_id=? ORDER BY s.created_at DESC""", (aid,))


def _new_source(c, aid, **kw) -> str:
    sid = db.new_id("src")
    db.insert(c, "sources", {"id": sid, "audience_id": aid, "status": "pending", "created_at": db.now(), **kw})
    return sid


class UrlsIn(BaseModel):
    urls: list[str]
    platform: str | None = None
    channel_id: str | None = None
    voice: str = "creator"
    transcribe_episodes: int = Field(default=0, ge=0, le=10)


@r.post("/audiences/{aid}/sources/urls")
def add_urls(aid: str, body: UrlsIn):
    must(db.one("SELECT id FROM audiences WHERE id=?", (aid,)), "Audience")
    created = []
    for raw in body.urls[:50]:
        url = raw.strip()
        if not url:
            continue
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        plat = body.platform or platforms.detect(url)
        h = hashlib.sha256(url.encode()).hexdigest()
        with db.tx() as c:
            ex = c.execute("SELECT id FROM sources WHERE audience_id=? AND sha256=?", (aid, h)).fetchone()
            if ex:
                created.append({"id": ex[0], "duplicate": True, "url": url})
                continue
            sid = _new_source(c, aid, kind="url", platform=plat, original_url=url, sha256=h,
                              channel_id=body.channel_id, voice="audience" if body.voice == "audience" else "creator")
        jobs.enqueue("ingest_source", aid, sid, {"transcribe_episodes": body.transcribe_episodes},
                     message="Waiting to retrieve")
        created.append({"id": sid, "duplicate": False, "url": url, "platform": plat})
    return {"sources": created}


class TextIn(BaseModel):
    title: str | None = None
    text: str = Field(min_length=1, max_length=2_000_000)
    platform: str = "other"
    voice: str = "creator"
    as_comments: bool = False
    channel_id: str | None = None


@r.post("/audiences/{aid}/sources/text")
def add_text(aid: str, body: TextIn):
    must(db.one("SELECT id FROM audiences WHERE id=?", (aid,)), "Audience")
    h = hashlib.sha256(body.text.encode()).hexdigest()
    with db.tx() as c:
        ex = c.execute("SELECT id FROM sources WHERE audience_id=? AND sha256=?", (aid, h)).fetchone()
        if ex:
            return {"id": ex[0], "duplicate": True}
        voice = "audience" if body.as_comments or body.voice == "audience" else "creator"
        sid = _new_source(c, aid, kind="text", platform=body.platform, title=body.title or "Pasted text", sha256=h,
                          voice=voice, channel_id=body.channel_id, size_bytes=len(body.text.encode()))
    jobs.enqueue("ingest_source", aid, sid, {"text": body.text, "as_comments": body.as_comments})
    return {"id": sid, "duplicate": False}


@r.post("/audiences/{aid}/sources/upload")
async def upload(aid: str, files: list[UploadFile] = File(...), platform: str = Form("other"),
                 voice: str = Form("creator"), channel_id: str | None = Form(None)):
    must(db.one("SELECT id FROM audiences WHERE id=?", (aid,)), "Audience")
    folder = config.UPLOADS_DIR / aid
    folder.mkdir(parents=True, exist_ok=True)
    out = []
    for f in files:
        name = safe_filename(f.filename or "file")
        tmp = folder / f".incoming_{db.new_id('u')}"
        h = hashlib.sha256()
        size = 0
        head = b""
        with open(tmp, "wb") as fh:
            while chunk := await f.read(1024 * 1024):
                if not head:
                    head = chunk[:8192]
                size += len(chunk)
                if size > config.MAX_UPLOAD_BYTES:
                    break
                h.update(chunk)
                fh.write(chunk)
        if size > config.MAX_UPLOAD_BYTES:
            tmp.unlink(missing_ok=True)
            out.append({"filename": name, "error": "File is larger than the 1 GB limit."})
            continue
        if size == 0:
            tmp.unlink(missing_ok=True)
            out.append({"filename": name, "error": "File is empty."})
            continue
        kind = classify_file(name, head)
        if not kind:
            tmp.unlink(missing_ok=True)
            out.append({"filename": name, "error": "Unsupported or unsafe file type. Supported: text, Markdown, HTML, "
                                                   "PDF, CSV, JSON, DOCX, audio, video and images."})
            continue
        digest = h.hexdigest()
        with db.tx() as c:
            ex = c.execute("SELECT id FROM sources WHERE audience_id=? AND sha256=?", (aid, digest)).fetchone()
            if ex:
                tmp.unlink(missing_ok=True)
                out.append({"filename": name, "id": ex[0], "duplicate": True})
                continue
            sid = db.new_id("src")
            dest = folder / f"{sid}_{name}"
            tmp.rename(dest)
            db.insert(c, "sources", {"id": sid, "audience_id": aid, "kind": "file", "platform": platform,
                                     "voice": "audience" if voice == "audience" else "creator",
                                     "channel_id": channel_id or None, "filename": name, "stored_path": str(dest),
                                     "mime": f.content_type, "size_bytes": size, "sha256": digest, "status": "pending",
                                     "created_at": db.now()})
        jobs.enqueue("ingest_source", aid, sid, message="Waiting to process" if kind not in ("audio", "video")
                     else "Waiting to transcribe")
        out.append({"filename": name, "id": sid, "kind": kind, "duplicate": False})
    return {"files": out}


@r.get("/sources/{sid}")
def get_source(sid: str):
    s = must(db.one("SELECT * FROM sources WHERE id=?", (sid,)), "Source")
    s["items"] = db.all_("SELECT id, kind, title, url, author, published_at, word_count, substr(text,1,600) AS preview, "
                         "metadata_json FROM content_items WHERE source_id=? ORDER BY published_at DESC, created_at LIMIT 200", (sid,))
    s["comments"] = db.all_("SELECT id, text, published_at, likes, replies, is_duplicate, is_spam, spam_reason FROM comments "
                            "WHERE source_id=? ORDER BY COALESCE(likes,0) DESC LIMIT 300", (sid,))
    s["comment_stats"] = db.one("SELECT COUNT(*) AS total, SUM(is_duplicate) AS duplicates, SUM(is_spam) AS spam, "
                                "COUNT(DISTINCT author_ref) AS authors FROM comments WHERE source_id=?", (sid,))
    s["jobs"] = db.all_("SELECT * FROM jobs WHERE ref_id=? ORDER BY created_at DESC LIMIT 5", (sid,))
    return s


@r.post("/sources/{sid}/reprocess")
def reprocess(sid: str):
    s = must(db.one("SELECT * FROM sources WHERE id=?", (sid,)), "Source")
    if s["kind"] == "text":
        raise HTTPException(400, "Pasted text can't be reprocessed — paste it again instead.")
    with db.tx() as c:
        c.execute("UPDATE sources SET status='pending' WHERE id=?", (sid,))
    return {"job_id": jobs.enqueue("ingest_source", s["audience_id"], sid, message="Waiting to reprocess")}


@r.delete("/sources/{sid}")
def delete_source(sid: str):
    s = must(db.one("SELECT * FROM sources WHERE id=?", (sid,)), "Source")
    with db.tx() as c:
        c.execute("DELETE FROM sources WHERE id=?", (sid,))
    if s.get("stored_path"):
        Path(s["stored_path"]).unlink(missing_ok=True)
    shutil.rmtree(config.MEDIA_DIR / sid, ignore_errors=True)
    return {"deleted": True}


@r.get("/content/{cid}")
def get_content(cid: str):
    ci = must(db.one("SELECT * FROM content_items WHERE id=?", (cid,)), "Content")
    ci["transcripts"] = db.all_("SELECT * FROM transcripts WHERE content_item_id=?", (cid,))
    ci["frames"] = db.all_("SELECT id, timestamp_s, description, described_by FROM media_frames WHERE content_item_id=? "
                           "ORDER BY timestamp_s", (cid,))
    ci["metrics"] = db.all_("SELECT metric, value, measured_at, source_note FROM engagement_metrics WHERE content_item_id=?", (cid,))
    ci["source"] = db.one("SELECT id, title, platform, original_url, retrieval_method, retrieved_at FROM sources WHERE id=?",
                          (ci["source_id"],))
    return ci


@r.get("/frames/{fid}/image")
def frame_image(fid: str):
    f = must(db.one("SELECT path FROM media_frames WHERE id=?", (fid,)), "Frame")
    p = Path(f["path"]).resolve()
    if not (str(p).startswith(str(config.DATA_DIR.resolve()))) or not p.exists():
        raise HTTPException(404, "Image not available")
    return FileResponse(p)


# ---------- analysis & intelligence ----------

class AnalyzeIn(BaseModel):
    provider: str | None = None
    confirm_external: bool = False


@r.post("/audiences/{aid}/analyze")
def analyze(aid: str, body: AnalyzeIn):
    must(db.one("SELECT id FROM audiences WHERE id=?", (aid,)), "Audience")
    p = providers.get_provider(body.provider)
    ok, why = p.available()
    if not ok:
        raise HTTPException(400, why)
    if p.external and not body.confirm_external:
        raise HTTPException(409, f"This analysis would send the audience material to {p.display}. Confirm to continue.")
    busy = db.one("SELECT id FROM jobs WHERE audience_id=? AND kind='analyze_audience' AND status IN ('queued','running')", (aid,))
    if busy:
        return {"job_id": busy["id"], "already_running": True}
    pending = db.scalar("SELECT COUNT(*) FROM jobs WHERE audience_id=? AND kind='ingest_source' AND status IN ('queued','running')", (aid,))
    jid = jobs.enqueue("analyze_audience", aid, payload={"provider": p.name}, max_attempts=2,
                       message="Waiting for imports to finish" if pending else "Starting analysis")
    return {"job_id": jid, "provider": p.label, "external": p.external}


@r.get("/audiences/{aid}/intelligence")
def intelligence(aid: str):
    must(db.one("SELECT id FROM audiences WHERE id=?", (aid,)), "Audience")
    return intel.intelligence(aid)


@r.get("/audiences/{aid}/analyses")
def analyses(aid: str):
    return db.all_("SELECT id, provider, model, external, status, stats_json, started_at, finished_at FROM analyses "
                   "WHERE audience_id=? ORDER BY started_at DESC", (aid,))


@r.get("/evidence/{eid}")
def evidence(eid: str):
    return must(intel.evidence_detail(eid), "Evidence")


# ---------- jobs ----------

@r.get("/jobs")
def list_jobs(audience_id: str | None = None, active: bool = False):
    where, params = [], []
    if audience_id:
        where.append("audience_id=?")
        params.append(audience_id)
    if active:
        where.append("status IN ('queued','running')")
    sql = "SELECT * FROM jobs" + (" WHERE " + " AND ".join(where) if where else "") + " ORDER BY created_at DESC LIMIT 50"
    return db.all_(sql, tuple(params))


@r.get("/jobs/{jid}")
def get_job(jid: str):
    return must(db.one("SELECT * FROM jobs WHERE id=?", (jid,)), "Job")


@r.post("/jobs/{jid}/cancel")
def cancel_job(jid: str):
    jobs.cancel(jid)
    return get_job(jid)


@r.post("/jobs/{jid}/retry")
def retry_job(jid: str):
    j = must(db.one("SELECT * FROM jobs WHERE id=?", (jid,)), "Job")
    if j["status"] not in ("failed", "cancelled"):
        raise HTTPException(400, "Only failed or cancelled jobs can be retried")
    with db.tx() as c:
        c.execute("UPDATE jobs SET status='queued', attempts=0, error=NULL, message='Retrying', progress=0, finished_at=NULL "
                  "WHERE id=?", (jid,))
    return get_job(jid)


# ---------- library ----------

@r.get("/library")
def library(q: str = "", kind: str = "all", audience_id: str | None = None, platform: str | None = None, limit: int = 100):
    like = f"%{q.strip()}%"
    res: dict[str, list] = {}
    af = " AND {t}.audience_id=?" if audience_id else ""
    ap = (audience_id,) if audience_id else ()
    pf = " AND {t}.platform=?" if platform else ""
    pp = (platform,) if platform else ()
    lim = max(1, min(500, limit))
    if kind in ("all", "sources"):
        res["sources"] = db.all_(f"SELECT s.id, s.audience_id, s.kind, s.platform, s.title, s.original_url, s.filename, s.status, "
                                 f"s.retrieved_at, s.created_at, a.name AS audience_name FROM sources s JOIN audiences a ON a.id=s.audience_id "
                                 f"WHERE (s.title LIKE ? OR s.original_url LIKE ? OR s.filename LIKE ?){af.format(t='s')}{pf.format(t='s')} "
                                 f"ORDER BY s.created_at DESC LIMIT {lim}", (like, like, like, *ap, *pp))
    if kind in ("all", "content", "transcripts"):
        extra = " AND EXISTS (SELECT 1 FROM transcripts t WHERE t.content_item_id=ci.id)" if kind == "transcripts" else ""
        res["content"] = db.all_(f"SELECT ci.id, ci.source_id, ci.audience_id, ci.kind, ci.platform, ci.title, ci.url, ci.published_at, ci.word_count, "
                                 f"substr(ci.text, max(1, instr(lower(ci.text), lower(?)) - 80), 260) AS snippet, a.name AS audience_name "
                                 f"FROM content_items ci JOIN audiences a ON a.id=ci.audience_id "
                                 f"WHERE (ci.text LIKE ? OR ci.title LIKE ?){extra}{af.format(t='ci')}{pf.format(t='ci')} "
                                 f"ORDER BY ci.created_at DESC LIMIT {lim}", (q.strip(), like, like, *ap, *pp))
    if kind in ("all", "comments"):
        res["comments"] = db.all_(f"SELECT cm.id, cm.source_id, cm.audience_id, cm.platform, cm.text, cm.published_at, cm.likes, cm.is_spam, "
                                  f"cm.is_duplicate, a.name AS audience_name FROM comments cm JOIN audiences a ON a.id=cm.audience_id "
                                  f"WHERE cm.text LIKE ?{af.format(t='cm')}{pf.format(t='cm')} ORDER BY COALESCE(cm.likes,0) DESC LIMIT {lim}",
                                  (like, *ap, *pp))
    if kind in ("all", "evidence"):
        res["evidence"] = db.all_(f"SELECT e.id, e.source_id, e.audience_id, e.quote, e.locator, s.platform, s.title AS source_title, "
                                  f"a.name AS audience_name FROM evidence e JOIN audiences a ON a.id=e.audience_id "
                                  f"LEFT JOIN sources s ON s.id=e.source_id WHERE e.quote LIKE ?{af.format(t='e')} "
                                  f"ORDER BY e.created_at DESC LIMIT {lim}", (like, *ap))
    if kind in ("all", "opportunities"):
        res["opportunities"] = db.all_(f"SELECT o.id, o.audience_id, o.name, o.product_type, o.price, o.status, o.total_score, "
                                       f"o.created_at, a.name AS audience_name FROM opportunities o JOIN audiences a ON a.id=o.audience_id "
                                       f"WHERE (o.name LIKE ? OR o.problem LIKE ? OR o.buyer LIKE ?){af.format(t='o')} "
                                       f"ORDER BY o.created_at DESC LIMIT {lim}", (like, like, like, *ap))
    if kind in ("all", "competitors"):
        res["competitors"] = db.all_(f"SELECT cp.*, a.name AS audience_name FROM competitors cp JOIN audiences a ON a.id=cp.audience_id "
                                     f"WHERE (cp.name LIKE ? OR cp.url LIKE ? OR cp.description LIKE ?){af.format(t='cp')} "
                                     f"ORDER BY cp.created_at DESC LIMIT {lim}", (like, like, like, *ap))
    if kind in ("all", "experiments"):
        res["experiments"] = db.all_(f"SELECT x.id, x.audience_id, x.name, x.status, x.decision, x.created_at, a.name AS audience_name "
                                     f"FROM experiments x JOIN audiences a ON a.id=x.audience_id WHERE (x.name LIKE ? OR x.hypothesis LIKE ? "
                                     f"OR x.findings LIKE ?){af.format(t='x')} ORDER BY x.created_at DESC LIMIT {lim}", (like, like, like, *ap))
    if kind in ("all", "reports"):
        res["reports"] = db.all_(f"SELECT rp.*, a.name AS audience_name FROM reports rp JOIN audiences a ON a.id=rp.audience_id "
                                 f"WHERE rp.title LIKE ?{af.format(t='rp')} ORDER BY rp.created_at DESC LIMIT {lim}", (like, *ap))
    if kind in ("all", "assets"):
        res["assets"] = db.all_(f"SELECT s.id, s.audience_id, s.kind, s.title, s.status, s.opportunity_id, s.created_at, "
                                f"a.name AS audience_name FROM assets s JOIN audiences a ON a.id=s.audience_id "
                                f"WHERE (s.title LIKE ? OR s.content LIKE ?){af.format(t='s')} ORDER BY s.created_at DESC LIMIT {lim}",
                                (like, like, *ap))
    if kind in ("all", "analyses"):
        res["analyses"] = db.all_(f"SELECT an.id, an.audience_id, an.provider, an.model, an.status, an.started_at, an.stats_json, "
                                  f"a.name AS audience_name FROM analyses an JOIN audiences a ON a.id=an.audience_id "
                                  f"WHERE 1=1{af.format(t='an')} ORDER BY an.started_at DESC LIMIT {lim}", ap)
    return res


@r.post("/backup")
def backup():
    from datetime import datetime
    dest = config.BACKUPS_DIR / f"audienceos_{datetime.now().strftime('%Y-%m-%d_%H%M%S')}.db"  # local time, as people read it
    db.backup(dest)
    return {"path": str(dest), "size_bytes": dest.stat().st_size}


@r.get("/audiences/{aid}/export")
def export_audience(aid: str):
    from ..services import reports
    d = reports.gather(aid)
    path = config.EXPORTS_DIR / f"{aid}_export.json"
    path.write_text(json.dumps(d, indent=2, default=str))
    return FileResponse(path, filename=f"{d['audience']['name']}.json".replace("/", "_"), media_type="application/json")
