"""AudienceOS local server. Binds to 127.0.0.1 only."""
import logging
import logging.handlers
import os
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
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
for _noisy in ("httpx", "httpcore"):  # httpx logs full request URLs at INFO, and some APIs take keys in the query string
    logging.getLogger(_noisy).setLevel(logging.WARNING)
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


@app.exception_handler(RequestValidationError)
async def invalid_request(request: Request, exc: RequestValidationError):
    # FastAPI's default 422 echoes the rejected input back; an input like Infinity can't be written as JSON, so the
    # refusal itself crashed into a 500. Send only where and why (all the page shows), never the value.
    return JSONResponse({"detail": [{"loc": list(e.get("loc", [])), "msg": str(e.get("msg", "")), "type": e.get("type")}
                                    for e in exc.errors()]}, status_code=422)


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
        if path == "api" or path.startswith("api/"):
            return JSONResponse({"detail": "Not found"}, status_code=404)  # unknown API routes aren't app pages
        f = (config.FRONTEND_DIST / path).resolve()
        if path and f.is_file() and f.is_relative_to(config.FRONTEND_DIST.resolve()):
            return FileResponse(f)
        return FileResponse(config.FRONTEND_DIST / "index.html")
