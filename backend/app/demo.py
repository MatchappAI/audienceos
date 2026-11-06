"""Demonstration project built from clearly labeled synthetic fixtures (fixtures/demo)."""
import hashlib
import shutil

from fastapi import HTTPException

from . import cleanup, config, db, jobs
from .routers.core import r

DEMO_FILES = [
    ("comments_instagram_export.csv", "instagram", "audience", "Instagram comments export (DEMO)"),
    ("post_analytics.csv", "instagram", "creator", "Instagram post analytics (DEMO)"),
    ("newsletter_issue_42.md", "newsletter", "creator", "Newsletter issue 42 (DEMO)"),
    ("demo_starter_video.mp4", "instagram", "creator", "Reel: why starters collapse (DEMO)"),
]


@r.post("/demo")
def load_demo():
    if db.scalar("SELECT COUNT(*) FROM audiences WHERE is_demo=1"):
        raise HTTPException(409, "The demo project is already loaded.")
    folder = config.FIXTURES_DIR / "demo"
    if not folder.exists():
        raise HTTPException(500, "Demo fixtures are missing.")
    now = db.now()
    with db.tx() as c:
        org = db.insert(c, "organizations", {"id": db.new_id("org"), "workspace_id": "ws_default",
                                             "name": "Hearth & Crumb (DEMO)", "kind": "creator", "is_demo": 1,
                                             "description": "Fictional sourdough creator. All data is synthetic.",
                                             "created_at": now, "updated_at": now})
        aid = db.insert(c, "audiences", {"id": db.new_id("aud"), "organization_id": org, "is_demo": 1,
                                         "name": "Hearth & Crumb home bakers (DEMO)", "niche": "Sourdough home baking",
                                         "description": "Demonstration data — synthetic, not a real audience.",
                                         "created_at": now, "updated_at": now})
        for plat, handle, n in (("instagram", "@hearthandcrumb_demo", 182000), ("newsletter", "The Crumb Report", 24000)):
            db.insert(c, "channels", {"id": db.new_id("ch"), "audience_id": aid, "platform": plat, "handle": handle,
                                      "follower_count": n, "follower_count_source": "DEMO — synthetic", "created_at": now})
        dest_dir = config.UPLOADS_DIR / aid
        dest_dir.mkdir(parents=True, exist_ok=True)
        ids = []
        for name, plat, voice, title in DEMO_FILES:
            src = folder / name
            if not src.exists():
                continue
            sid = db.new_id("src")
            dest = dest_dir / f"{sid}_{name}"
            shutil.copy(src, dest)
            db.insert(c, "sources", {"id": sid, "audience_id": aid, "kind": "file", "platform": plat, "voice": voice,
                                     "title": title, "filename": name, "stored_path": str(dest),
                                     "size_bytes": dest.stat().st_size, "is_demo": 1,
                                     "sha256": hashlib.sha256(dest.read_bytes()).hexdigest(), "status": "pending",
                                     "created_at": now})
            ids.append(sid)
        db.log_activity(c, aid, "demo", "Loaded the demonstration project (synthetic data)")
    for sid in ids:
        jobs.enqueue("ingest_source", aid, sid)
    return {"audience_id": aid}


@r.delete("/demo")
def remove_demo():
    ids = [a["id"] for a in db.all_("SELECT id FROM audiences WHERE is_demo=1")]
    dirs = cleanup.audience_dirs(ids)
    with db.tx() as c:
        c.execute("DELETE FROM organizations WHERE is_demo=1")
    cleanup.purge(dirs)
    return {"removed": len(ids)}
