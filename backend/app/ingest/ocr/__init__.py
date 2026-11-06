"""On-device OCR via Apple's Vision framework.

A small Swift helper (``ocr.swift``) is compiled on first use with ``/usr/bin/swiftc`` into ``data/bin/``. On a Mac
without the Swift toolchain, or on Linux, OCR is reported as unavailable instead of failing the import.
"""
import hashlib
import json
import logging
import os
import platform
import shutil
import subprocess
import threading
from pathlib import Path

from ... import config

log = logging.getLogger("audienceos.ocr")
SOURCE = Path(__file__).with_name("ocr.swift")
_lock = threading.Lock()
UNAVAILABLE_NOTE = ("Text recognition (OCR) is unavailable on this computer — it needs macOS with Apple's "
                    "command-line tools (run `xcode-select --install`).")


class OCRUnavailable(RuntimeError):
    pass


def _swiftc() -> str | None:
    if os.environ.get("AUDIENCEOS_NO_OCR") == "1" or platform.system() != "Darwin":
        return None
    return shutil.which("swiftc") or ("/usr/bin/swiftc" if Path("/usr/bin/swiftc").exists() else None)


def binary_path() -> Path:
    digest = hashlib.sha256(SOURCE.read_bytes()).hexdigest()[:12]
    return config.DATA_DIR / "bin" / f"ocr-{digest}"


def ensure_binary() -> Path:
    """Compile the helper if needed (once per source version). Raises OCRUnavailable."""
    out = binary_path()
    if out.exists():
        return out
    swiftc = _swiftc()
    if not swiftc:
        raise OCRUnavailable(UNAVAILABLE_NOTE)
    with _lock:
        if out.exists():
            return out
        out.parent.mkdir(parents=True, exist_ok=True)
        tmp = out.with_name(out.name + ".tmp")
        try:
            r = subprocess.run([swiftc, "-O", str(SOURCE), "-o", str(tmp)], capture_output=True, text=True, timeout=300)
        except (OSError, subprocess.TimeoutExpired) as e:
            raise OCRUnavailable(f"{UNAVAILABLE_NOTE} ({e})") from e
        if r.returncode != 0 or not tmp.exists():
            log.warning("OCR helper failed to compile: %s", (r.stderr or "")[-1000:])
            raise OCRUnavailable(UNAVAILABLE_NOTE)
        tmp.replace(out)
    return out


def available() -> bool:
    if os.environ.get("AUDIENCEOS_NO_OCR") == "1":
        return False
    return binary_path().exists() or bool(_swiftc())


def recognize(path: Path, pages: list[int] | None = None, timeout: int = 600) -> list[dict]:
    """Return [{"page": n, "text": str, "confidence": float}]. Raises OCRUnavailable or RuntimeError."""
    exe = ensure_binary()
    cmd = [str(exe), str(path)]
    if pages:
        cmd.append(",".join(str(p) for p in pages))
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as e:
        raise RuntimeError("Text recognition timed out") from e
    try:
        data = json.loads(r.stdout or "{}")
    except ValueError as e:
        raise RuntimeError("Text recognition returned unreadable output") from e
    if r.returncode != 0 or "error" in data:
        raise RuntimeError(f"Text recognition failed: {data.get('error', (r.stderr or '')[-300:])}")
    return [p for p in data.get("pages", []) if isinstance(p, dict)]
