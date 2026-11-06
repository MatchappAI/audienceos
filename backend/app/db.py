"""SQLite access: connections, migrations, small helpers. All queries are parameterized."""
import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from . import config

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


def connect(path: Path | None = None) -> sqlite3.Connection:
    c = sqlite3.connect(str(path or config.DB_PATH), timeout=30, check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys = ON")
    c.execute("PRAGMA journal_mode = WAL")
    c.execute("PRAGMA busy_timeout = 30000")
    return c


@contextmanager
def tx():
    c = connect()
    try:
        yield c
        c.commit()
    except Exception:
        c.rollback()
        raise
    finally:
        c.close()


def migrate(path: Path | None = None) -> list[str]:
    c = connect(path)
    applied = []
    try:
        c.execute("CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY, applied_at TEXT NOT NULL)")
        done = {r[0] for r in c.execute("SELECT version FROM schema_migrations")}
        for f in sorted(MIGRATIONS_DIR.glob("*.sql")):
            if f.stem in done:
                continue
            c.executescript("BEGIN;\n" + f.read_text() + "\nCOMMIT;")
            c.execute("INSERT INTO schema_migrations VALUES (?, ?)", (f.stem, now()))
            c.commit()
            applied.append(f.stem)
        if not c.execute("SELECT 1 FROM workspaces").fetchone():
            c.execute("INSERT INTO workspaces VALUES (?,?,?)", ("ws_default", "My workspace", now()))
            c.commit()
    finally:
        c.close()
    return applied


def row(r) -> dict | None:
    if r is None:
        return None
    d = dict(r)
    for k in list(d):
        if k.endswith("_json") and isinstance(d[k], str):
            try:
                d[k[:-5]] = json.loads(d[k])
            except ValueError:
                d[k[:-5]] = None
            del d[k]
    return d


def rows(rs) -> list[dict]:
    return [row(r) for r in rs]


def one(sql: str, params=()) -> dict | None:
    c = connect()
    try:
        return row(c.execute(sql, params).fetchone())
    finally:
        c.close()


def all_(sql: str, params=()) -> list[dict]:
    c = connect()
    try:
        return rows(c.execute(sql, params).fetchall())
    finally:
        c.close()


def scalar(sql: str, params=()):
    c = connect()
    try:
        r = c.execute(sql, params).fetchone()
        return r[0] if r else None
    finally:
        c.close()


def insert(c: sqlite3.Connection, table: str, data: dict) -> str:
    data = {k: (json.dumps(v) if k.endswith("_json") and not isinstance(v, str) else v) for k, v in data.items()}
    cols = ",".join(data)
    marks = ",".join("?" for _ in data)
    c.execute(f"INSERT INTO {table} ({cols}) VALUES ({marks})", tuple(data.values()))
    return data.get("id")


def update(c: sqlite3.Connection, table: str, id_: str, data: dict) -> None:
    if not data:
        return
    data = {k: (json.dumps(v) if k.endswith("_json") and not isinstance(v, str) else v) for k, v in data.items()}
    sets = ",".join(f"{k}=?" for k in data)
    c.execute(f"UPDATE {table} SET {sets} WHERE id=?", (*data.values(), id_))


def log_activity(c: sqlite3.Connection, audience_id: str | None, kind: str, message: str) -> None:
    insert(c, "activity", {"id": new_id("act"), "audience_id": audience_id, "kind": kind,
                           "message": message, "created_at": now()})


def backup(dest: Path) -> Path:
    src = connect()
    dst = sqlite3.connect(str(dest))
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    return dest
