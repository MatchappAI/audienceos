"""AudienceOS local server. Binds to 127.0.0.1 only."""
import logging
import logging.handlers
import os
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import config, db, demo, jobs  # noqa: F401  (demo registers routes)
from .ai import pipeline  # noqa: F401  (registers job handlers)
from .ingest import runner  # noqa: F401
from .routers import core, money, monetize
from .services import assets, competitors  # noqa: F401

handler = logging.handlers.RotatingFileHandler(config.LOGS_DIR / "audienceos.log", maxBytes=5_000_000, backupCount=3)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s",
                    handlers=[handler, logging.StreamHandler()])
log = logging.getLogger("audienceos")


@asynccontextmanager
async def lifespan(app):
    applied = db.migrate()
    if applied:
        log.info("Applied migrations: %s", applied)
    jobs.start_worker()
    yield
    jobs.stop_worker()


app = FastAPI(title="AudienceOS", lifespan=lifespan, docs_url=None, redoc_url=None)
ALLOWED_HOSTS = {f"127.0.0.1:{config.PORT}", f"localhost:{config.PORT}"}
if os.environ.get("AUDIENCEOS_TESTING") == "1":
    ALLOWED_HOSTS.add("testserver")  # FastAPI TestClient's Host header; never allowed in the real app


@app.middleware("http")
async def guard(request: Request, call_next):
    # DNS-rebinding protection: only answer requests addressed to this machine.
    if request.headers.get("host") not in ALLOWED_HOSTS:
        return JSONResponse({"detail": "Host not allowed"}, status_code=403)
    # CSRF protection: state-changing API calls must carry a custom header (web pages can't add it cross-site).
    if request.url.path.startswith("/api") and request.method not in ("GET", "HEAD", "OPTIONS") \
            and request.headers.get("x-audienceos") != "1":
        return JSONResponse({"detail": "Missing request header"}, status_code=403)
    resp = await call_next(request)
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("Referrer-Policy", "no-referrer")
    if not request.url.path.startswith("/api/assets") and not request.url.path.startswith("/api/reports"):
        resp.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    return resp


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    error_id = uuid.uuid4().hex[:8]
    log.exception("Unhandled error %s on %s", error_id, request.url.path)
    # Never send raw exception text to the client (it can include paths or SQL); the log has the detail.
    return JSONResponse({"detail": f"Something went wrong (error id {error_id}). Details are in the log."},
                        status_code=500)


app.include_router(core.r)
app.include_router(monetize.r)
app.include_router(money.r)

if (config.FRONTEND_DIST / "index.html").exists():
    app.mount("/assets", StaticFiles(directory=config.FRONTEND_DIST / "assets"), name="static")

    @app.get("/{path:path}")
    def spa(path: str):
        f = (config.FRONTEND_DIST / path).resolve()
        if path and f.is_file() and str(f).startswith(str(config.FRONTEND_DIST.resolve())):
            return FileResponse(f)
        return FileResponse(config.FRONTEND_DIST / "index.html")
