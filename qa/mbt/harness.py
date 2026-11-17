"""Start/stop a scratch AudienceOS server and the stand-in AI engine, and talk to them over HTTP.

Only processes started here are ever stopped (by PID). Never port 8760, never ~/AudienceOS/data.
"""
import json
import os
import shutil
import signal
import socket
import sqlite3
import subprocess
import tempfile
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
PY = ROOT / "backend" / ".venv" / "bin" / "python"
LIVE_DATA = (ROOT / "data").resolve()


def free_port(start: int) -> int:
    # Parallel runs: start at a PID-dependent offset so two runs don't race for the same port.
    off = (os.getpid() * 7) % 150
    for p in list(range(start + off, start + 200)) + list(range(start, start + off)):
        if p == 8760:
            continue
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", p))
                return p
            except OSError:
                continue
    raise RuntimeError("no free port")


class Engine:
    """The stand-in Ollama (fake_ollama.py) or the real bundled one."""

    def __init__(self, port: int, real: bool = False, logdir: Path | None = None):
        self.port, self.real, self.proc = port, real, None
        self.url = f"http://127.0.0.1:{port}"
        self.logdir = logdir

    def start(self):
        if self.proc and self.proc.poll() is None:
            return
        log = open((self.logdir or Path(tempfile.gettempdir())) / "engine.log", "a")
        if self.real:
            env = {**os.environ, "OLLAMA_HOST": f"127.0.0.1:{self.port}", "OLLAMA_MODELS": str(ROOT / "runtime" / "models")}
            self.proc = subprocess.Popen([str(ROOT / "runtime" / "ollama" / "ollama"), "serve"], env=env, stdout=log, stderr=log)
        else:
            self.proc = subprocess.Popen([str(PY), "-I", str(Path(__file__).with_name("fake_ollama.py")), "--port", str(self.port)],
                                         stdout=log, stderr=log)
        for _ in range(150):
            if self.proc.poll() is not None:
                raise RuntimeError(f"engine exited (port {self.port} taken?)")
            try:
                if httpx.get(self.url + "/api/tags", timeout=1).status_code == 200:
                    time.sleep(0.2)
                    if self.proc.poll() is not None:
                        raise RuntimeError(f"engine on port {self.port} is not ours")
                    return
            except httpx.HTTPError:
                pass
            time.sleep(0.1)
        raise RuntimeError("engine did not start")

    def stop(self):
        if self.proc and self.proc.poll() is None:
            self.proc.send_signal(signal.SIGTERM)
            try:
                self.proc.wait(5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        self.proc = None

    @property
    def up(self):
        return bool(self.proc and self.proc.poll() is None)

    def mode(self, mode: str, **kw):
        if self.real or not self.up:
            return
        httpx.post(self.url + "/__mode", json={"mode": mode, **kw}, timeout=3)


class Server:
    def __init__(self, port: int, engine_url: str, data: Path | None = None):
        self.port, self.engine_url = port, engine_url
        self.data = Path(data or tempfile.mkdtemp(prefix="aos-mbt-"))
        assert self.data.resolve() != LIVE_DATA and port != 8760
        self.proc = None
        self.base = f"http://127.0.0.1:{port}"
        self.c = httpx.Client(base_url=self.base, headers={"x-audienceos": "1"}, timeout=60)
        self.calls = 0
        self.five_xx: list[str] = []

    def start(self):
        env = {**os.environ, "AUDIENCEOS_DATA": str(self.data), "AUDIENCEOS_PORT": str(self.port),
               "AUDIENCEOS_NO_KEYCHAIN": "1", "AUDIENCEOS_OLLAMA_URL": self.engine_url}
        log = open(self.data / "server.out", "a")
        self.proc = subprocess.Popen([str(PY), str(Path(__file__).with_name("serve.py"))], cwd=str(ROOT / "backend"), env=env,
                                     stdout=log, stderr=log)
        for _ in range(300):
            if self.proc.poll() is not None:
                raise RuntimeError("server exited: " + (self.data / "server.out").read_text()[-2000:])
            try:
                if self.c.get("/api/health", timeout=1).status_code == 200:
                    time.sleep(0.2)
                    if self.proc.poll() is None:
                        return
            except httpx.HTTPError:
                pass
            if self.proc.poll() is not None:
                raise RuntimeError("server exited: " + (self.data / "server.out").read_text()[-2000:])
            time.sleep(0.1)
        raise RuntimeError("server did not start")

    def stop(self, hard: bool = False):
        if self.proc and self.proc.poll() is None:
            self.proc.send_signal(signal.SIGKILL if hard else signal.SIGTERM)
            try:
                self.proc.wait(10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(5)
        self.proc = None

    def restart(self, hard: bool = False):
        self.stop(hard)
        self.start()

    def wipe(self):
        self.stop()
        shutil.rmtree(self.data, ignore_errors=True)
        self.data.mkdir(parents=True)

    # --- HTTP ---
    def req(self, method: str, path: str, **kw) -> httpx.Response:
        self.calls += 1
        try:
            r = self.c.request(method, path, **kw)
        except (httpx.ReadError, httpx.RemoteProtocolError):
            # uvicorn closes a keep-alive connection after an unhandled error; the next request on the pooled
            # connection then fails before reaching the server. Retry once on a fresh connection.
            self.c.close()
            self.c = httpx.Client(base_url=self.base, headers={"x-audienceos": "1"}, timeout=60)
            r = self.c.request(method, path, **kw)
        if r.status_code >= 500:
            self.five_xx.append(f"{method} {path} -> {r.status_code} {r.text[:200]}")
        return r

    def get(self, path, **kw):
        return self.req("GET", path, **kw)

    def post(self, path, json_=None, **kw):
        return self.req("POST", path, json=json_, **kw) if json_ is not None else self.req("POST", path, **kw)

    def patch(self, path, json_):
        return self.req("PATCH", path, json=json_)

    def put(self, path, json_):
        return self.req("PUT", path, json=json_)

    def delete(self, path):
        return self.req("DELETE", path)

    def j(self, method, path, **kw):
        r = self.req(method, path, **kw)
        r.raise_for_status()
        return r.json()

    def db(self):
        return sqlite3.connect(f"file:{self.data / 'audienceos.db'}?mode=ro", uri=True, timeout=5)

    def wait_idle(self, timeout: float = 120) -> bool:
        t0 = time.time()
        while time.time() - t0 < timeout:
            active = self.get("/api/jobs", params={"active": True}).json()
            if not active:
                return True
            time.sleep(0.25)
        return False
