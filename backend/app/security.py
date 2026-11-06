"""Network and file safety: SSRF-safe fetching, redirect checks, size caps, file-type sniffing."""
import ipaddress
import re
import socket
import urllib.robotparser
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx

from . import config

USER_AGENT = "AudienceOS/1.0 (personal research tool; respects robots.txt)"


class FetchError(Exception):
    def __init__(self, message: str, code: str = "fetch_error"):
        super().__init__(message)
        self.code = code


@dataclass
class FetchResult:
    url: str
    final_url: str
    status: int
    content_type: str
    body: bytes
    headers: dict = field(default_factory=dict)

    @property
    def text(self) -> str:
        enc = "utf-8"
        m = re.search(r"charset=([\w-]+)", self.content_type or "")
        if m:
            enc = m.group(1)
        try:
            return self.body.decode(enc, errors="replace")
        except LookupError:
            return self.body.decode("utf-8", errors="replace")


def _is_public_ip(ip: str) -> bool:
    a = ipaddress.ip_address(ip)
    if a.version == 6 and a.ipv4_mapped:
        a = a.ipv4_mapped
    return not (a.is_private or a.is_loopback or a.is_link_local or a.is_multicast
                or a.is_reserved or a.is_unspecified or (a.version == 4 and a in ipaddress.ip_network("100.64.0.0/10")))


def check_url(url: str) -> None:
    """Reject non-http(s), credentials in URL, odd ports and any host resolving to a private address."""
    p = urlparse(url)
    if p.scheme not in ("http", "https"):
        raise FetchError("Only http and https links are supported.", "bad_scheme")
    if p.username or p.password:
        raise FetchError("Links containing credentials are not allowed.", "bad_url")
    if not p.hostname:
        raise FetchError("That link has no host name.", "bad_url")
    if p.port not in (None, 80, 443):
        raise FetchError("Only standard web ports (80/443) are allowed.", "bad_port")
    host = p.hostname
    if host in ("localhost",) or host.endswith(".local") or host.endswith(".internal"):
        raise FetchError("Local network addresses are blocked for safety.", "private_address")
    try:
        infos = socket.getaddrinfo(host, p.port or (443 if p.scheme == "https" else 80), proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        raise FetchError(f"Could not find the website '{host}'. Check the link or your internet connection.", "dns")
    for info in infos:
        if not _is_public_ip(info[4][0]):
            raise FetchError("This link points to a private or local network address, which is blocked for safety.",
                             "private_address")


_robots_cache: dict[str, urllib.robotparser.RobotFileParser | None] = {}


def robots_allowed(url: str) -> bool:
    p = urlparse(url)
    base = f"{p.scheme}://{p.netloc}"
    if base not in _robots_cache:
        rp = urllib.robotparser.RobotFileParser()
        try:
            r = safe_get(base + "/robots.txt", max_bytes=512 * 1024, check_robots=False)
            if r.status == 200:
                rp.parse(r.text.splitlines())
            else:
                rp = None  # no robots.txt => allowed
        except FetchError:
            rp = None
        _robots_cache[base] = rp
    rp = _robots_cache[base]
    return True if rp is None else rp.can_fetch(USER_AGENT, url)


def safe_get(url: str, *, max_bytes: int = config.MAX_PAGE_BYTES, check_robots: bool = True,
             headers: dict | None = None, params: dict | None = None, accept: str | None = None) -> FetchResult:
    from . import settings_store
    if not settings_store.get("allow_web_retrieval"):
        raise FetchError("Web retrieval is turned off in Settings.", "offline_mode")
    if check_robots and not robots_allowed(url):
        raise FetchError("This website's robots.txt does not allow automated retrieval of this page.", "robots")
    h = {"User-Agent": USER_AGENT, "Accept": accept or "text/html,application/xhtml+xml,application/xml,application/json,*/*;q=0.5"}
    h.update(headers or {})
    current = url
    with httpx.Client(timeout=config.FETCH_TIMEOUT_S, follow_redirects=False) as client:
        for _ in range(6):
            check_url(current)
            try:
                with client.stream("GET", current, headers=h, params=params) as resp:
                    params = None
                    if resp.status_code in (301, 302, 303, 307, 308):
                        loc = resp.headers.get("location")
                        if not loc:
                            raise FetchError("Redirect without a destination.")
                        current = urljoin(current, loc)
                        continue
                    declared = int(resp.headers.get("content-length") or 0)
                    if declared > max_bytes:
                        raise FetchError(f"The file is too large ({declared // 1_000_000} MB).", "too_large")
                    buf = bytearray()
                    for chunk in resp.iter_bytes():
                        buf.extend(chunk)
                        if len(buf) > max_bytes:
                            raise FetchError("The download exceeded the size limit and was stopped.", "too_large")
                    return FetchResult(url, current, resp.status_code, resp.headers.get("content-type", ""),
                                       bytes(buf), dict(resp.headers))
            except httpx.TimeoutException:
                raise FetchError("The website took too long to respond.", "timeout")
            except httpx.HTTPError as e:
                raise FetchError(f"Network error: {e.__class__.__name__}. Check your internet connection.", "network")
    raise FetchError("Too many redirects.", "redirects")


# ---------- files ----------

ALLOWED_EXT = {
    "text": {".txt", ".md", ".markdown"},
    "html": {".html", ".htm"},
    "pdf": {".pdf"},
    "csv": {".csv", ".tsv"},
    "json": {".json"},
    "docx": {".docx"},
    "audio": {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac"},
    "video": {".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi"},
    "image": {".png", ".jpg", ".jpeg", ".webp", ".gif", ".heic"},
}
BLOCKED_EXT = {".exe", ".app", ".dmg", ".pkg", ".sh", ".command", ".bat", ".js", ".py", ".jar", ".scpt", ".dylib", ".so"}


def classify_file(name: str, head: bytes) -> str | None:
    ext = Path(name).suffix.lower()
    if ext in BLOCKED_EXT:
        return None
    kind = next((k for k, exts in ALLOWED_EXT.items() if ext in exts), None)
    if kind is None:
        return None
    # Sniff magic bytes so a renamed binary is not treated as a document.
    if kind == "pdf" and not head.startswith(b"%PDF"):
        return None
    if kind == "docx" and not head.startswith(b"PK"):
        return None
    if kind in ("text", "csv", "json", "html") and b"\x00" in head[:4096]:
        return None
    if head.startswith(b"\xcf\xfa\xed\xfe") or head.startswith(b"MZ") or head.startswith(b"\x7fELF"):
        return None
    return kind


def safe_filename(name: str) -> str:
    name = Path(name).name
    name = re.sub(r"[^\w.\- ]+", "_", name).strip(" .") or "file"
    return name[:120]
