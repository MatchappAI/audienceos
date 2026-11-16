"""Local background jobs, persisted in SQLite. Survives restarts: interrupted jobs are re-queued and retried."""
import json
import logging
import sqlite3
import threading
import time
import traceback

from . import db

log = logging.getLogger("audienceos.jobs")
HANDLERS: dict = {}
_stop = threading.Event()
_thread: threading.Thread | None = None


class JobCancelled(Exception):
    pass


def handler(kind: str):
    def deco(fn):
        HANDLERS[kind] = fn
        return fn
    return deco


def enqueue(kind: str, audience_id: str | None = None, ref_id: str | None = None, payload: dict | None = None,
            max_attempts: int = 2, message: str = "Waiting to start") -> str:
    jid = db.new_id("job")
    with db.tx() as c:
        db.insert(c, "jobs", {"id": jid, "kind": kind, "audience_id": audience_id, "ref_id": ref_id,
                              "payload_json": payload or {}, "status": "queued", "message": message,
                              "max_attempts": max_attempts, "created_at": db.now()})
    return jid


class Progress:
    def __init__(self, job_id: str):
        self.job_id = job_id
        self._last = 0.0
        self._msg: str | None = None

    def __call__(self, fraction: float, message: str | None = None):
        # Throttle repeated updates, but never drop a new stage message (the UI would show the old stage for the
        # whole of the next one).
        if time.time() - self._last < 0.4 and fraction < 1 and message == self._msg:
            return
        self._last, self._msg = time.time(), message
        c = db.connect()
        try:
            c.execute("PRAGMA busy_timeout = 1500")
            st = c.execute("SELECT status FROM jobs WHERE id=?", (self.job_id,)).fetchone()
            if st and st[0] == "cancelled":
                raise JobCancelled()
            c.execute("UPDATE jobs SET progress=?, message=COALESCE(?, message) WHERE id=?",
                      (round(fraction, 3), message, self.job_id))
            c.commit()
        except sqlite3.OperationalError:
            pass  # progress is best-effort; never block real work on it
        finally:
            c.close()


def recover_interrupted() -> int:
    """Jobs left 'running' by a crash or quit are re-queued (or failed if out of attempts)."""
    with db.tx() as c:
        n = c.execute("UPDATE jobs SET status='queued', message='Resuming after restart' "
                      "WHERE status='running' AND attempts < max_attempts").rowcount
        c.execute("UPDATE jobs SET status='failed', error='Interrupted too many times', finished_at=? "
                  "WHERE status='running'", (db.now(),))
    return n


def run_one() -> bool:
    with db.tx() as c:
        r = c.execute("SELECT * FROM jobs WHERE status='queued' ORDER BY created_at LIMIT 1").fetchone()
        if not r:
            return False
        job = db.row(r)
        c.execute("UPDATE jobs SET status='running', attempts=attempts+1, started_at=?, message=? WHERE id=?",
                  (db.now(), "Starting", job["id"]))
    fn = HANDLERS.get(job["kind"])
    try:
        if not fn:
            raise RuntimeError(f"No handler for job kind {job['kind']}")
        result = fn(job, Progress(job["id"])) or {}
        with db.tx() as c:
            c.execute("UPDATE jobs SET status='done', progress=1, message=?, finished_at=? WHERE id=? AND status='running'",
                      (result.get("message", "Done"), db.now(), job["id"]))
    except JobCancelled:
        log.info("job %s cancelled", job["id"])
    except Exception as e:
        log.error("job %s failed: %s\n%s", job["id"], e, traceback.format_exc())
        with db.tx() as c:
            cancelled = (c.execute("SELECT status FROM jobs WHERE id=?", (job["id"],)).fetchone() or ["cancelled"])[0] == "cancelled"
            retry = not cancelled and job["attempts"] + 1 < job["max_attempts"] and getattr(e, "retryable", False)
            # A job the user cancelled stays cancelled, even if the work then errors out.
            c.execute("UPDATE jobs SET status=?, error=?, message=?, finished_at=? WHERE id=? AND status != 'cancelled'",
                      ("queued" if retry else "failed", str(e)[:1000],
                       "Retrying" if retry else "Failed", None if retry else db.now(), job["id"]))
        fail = HANDLERS.get(job["kind"] + ":failed")
        if fail and not retry:
            try:
                fail(job, e)
            except Exception:
                log.exception("failure hook error")
    return True


def _loop():
    while not _stop.is_set():
        try:
            if not run_one():
                _stop.wait(0.7)
        except Exception:
            log.exception("worker loop error")
            _stop.wait(2)


def start_worker():
    global _thread
    if _thread and _thread.is_alive():
        return
    recover_interrupted()
    _stop.clear()
    _thread = threading.Thread(target=_loop, name="audienceos-worker", daemon=True)
    _thread.start()


def stop_worker():
    _stop.set()


def cancel(job_id: str) -> None:
    with db.tx() as c:
        j = c.execute("SELECT kind, status, ref_id FROM jobs WHERE id=?", (job_id,)).fetchone()
        c.execute("UPDATE jobs SET status='cancelled', message='Cancelled', finished_at=? "
                  "WHERE id=? AND status IN ('queued','running')", (db.now(), job_id))
        if j and j[0] == "analyze_audience" and j[1] in ("queued", "running"):
            # Close the analysis honestly, so the audience doesn't show "analysis running" forever.
            aud = c.execute("SELECT audience_id FROM jobs WHERE id=?", (job_id,)).fetchone()[0]
            c.execute("UPDATE ai_runs SET status='failed', finished_at=?, error='Cancelled' WHERE status='running' AND "
                      "analysis_id IN (SELECT id FROM analyses WHERE audience_id=? AND status='running')", (db.now(), aud))
            c.execute("UPDATE analyses SET status='failed', finished_at=?, unknowns_json=? WHERE audience_id=? AND status='running'",
                      (db.now(), '["Cancelled before it finished"]', aud))
        if j and j[0] == "ingest_source" and j[1] in ("queued", "running") and j[2]:
            # Don't leave the source stuck on "Waiting"; it can be reprocessed.
            c.execute("UPDATE sources SET status='failed', status_detail='Cancelled — reprocess to try again' "
                      "WHERE id=? AND status IN ('pending','processing')", (j[2],))


def payload(job: dict) -> dict:
    p = job.get("payload")
    return p if isinstance(p, dict) else json.loads(job.get("payload_json") or "{}")
