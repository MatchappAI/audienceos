"""Run the real AudienceOS server for model-based testing, with every outside connection cut off.

- An in-process firewall: any httpx request to a host other than 127.0.0.1/localhost raises ConnectError, and is
  counted (GET /api/__qa/blocked shows the count). So external AI, checkout syncs and link fetches can be exercised
  with fake keys without a single byte leaving this Mac.
- Link fetches (security.safe_get, used by URL import and competitor lookups) are stubbed with canned pages.
- Checkout syncs use an httpx MockTransport that answers like Stripe/Gumroad/Shopify/Lemon Squeezy.
- Proxy variables point at a dead port as a second safety net.

Never use port 8760 or ~/AudienceOS/data. Usage (from backend/):
  AUDIENCEOS_DATA=/tmp/x AUDIENCEOS_PORT=8771 AUDIENCEOS_NO_KEYCHAIN=1 AUDIENCEOS_OLLAMA_URL=http://127.0.0.1:11471 \
    .venv/bin/python ../qa/mbt/serve.py
"""
import os
import sys
from pathlib import Path

port = int(os.environ.get("AUDIENCEOS_PORT", "0"))
data = os.environ.get("AUDIENCEOS_DATA", "")
if port == 8760 or not data or Path(data).resolve() == (Path(__file__).resolve().parents[2] / "data").resolve():
    sys.exit("Refusing: needs a scratch AUDIENCEOS_DATA and a port other than 8760.")
os.environ["AUDIENCEOS_NO_KEYCHAIN"] = "1"
for k in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
    os.environ[k] = "http://127.0.0.1:9"
os.environ["NO_PROXY"] = os.environ["no_proxy"] = "127.0.0.1,localhost"
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

import socket  # noqa: E402

import httpx  # noqa: E402

# No DNS lookups leave this Mac either: every outside name "resolves" to a fixed public address (example.com's; nothing ever connects to it: link fetches are stubbed and the firewall above refuses outside hosts), after the
# same IDNA encoding the real resolver does (so malformed names still fail the way they would for real).
_real_gai = socket.getaddrinfo
DNS = {"n": 0}


def _fake_gai(host, port, *a, **kw):
    h = host.decode() if isinstance(host, bytes) else host
    if h in (None, "127.0.0.1", "localhost", "::1", "0.0.0.0"):
        return _real_gai(host, port, *a, **kw)
    h.encode("idna")
    DNS["n"] += 1
    if h.endswith(".invalid") or "nxdomain" in h:
        raise socket.gaierror(socket.EAI_NONAME, "stub: no such host")
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.215.14", port or 443))]


socket.getaddrinfo = _fake_gai

BLOCKED = {"n": 0, "hosts": []}
_orig_handle = httpx.HTTPTransport.handle_request


def _guarded(self, request):
    host = request.url.host
    if host not in ("127.0.0.1", "localhost"):
        BLOCKED["n"] += 1
        BLOCKED["hosts"] = (BLOCKED["hosts"] + [host])[-20:]
        raise httpx.ConnectError(f"blocked by the QA firewall: {host}", request=request)
    return _orig_handle(self, request)


httpx.HTTPTransport.handle_request = _guarded

from app import security  # noqa: E402
from app.ingest import urls as _urls  # noqa: E402
from app.services import checkout_sync, competitors as _comp  # noqa: E402

PAGE = (b"<html><head><title>Stub page</title></head><body><h1>Sourdough starter guide</h1>"
        b"<p>How do I keep my starter alive while travelling? I would pay for a simple schedule.</p>"
        b"<p>Price: $29</p>"
        + b"<p>" + b" ".join([b"Feeding a starter twice a day keeps it lively; travel, heat and new flour all change the timing."] * 6)
        + b"</p></body></html>")


def fake_safe_get(url, **kw):
    from app import settings_store
    if not settings_store.get("allow_web_retrieval"):
        raise security.FetchError("Web retrieval is turned off in Settings.", "offline_mode")
    security.check_url(url)  # the real SSRF rules still apply
    if "fail" in url:
        raise security.FetchError("Stub: the site could not be reached.")
    if "oembed" in url:
        return security.FetchResult(url, url, 200, "application/json", b'{"title":"Stub video","author_name":"Stub"}')
    return security.FetchResult(url, url, 200, "text/html; charset=utf-8", PAGE)


_urls.safe_get = fake_safe_get
_comp.safe_get = fake_safe_get


def _checkout(request: httpx.Request) -> httpx.Response:
    h = request.url.host
    if "stripe" in h:
        if "checkout/sessions" in request.url.path:
            return httpx.Response(200, json={"has_more": False, "data": [
                {"id": "cs_qa_1", "payment_status": "paid", "amount_total": 2900, "created": 1767225600, "currency": "usd",
                 "payment_intent": None, "client_reference_id": "newsletter", "metadata": {}}]})
        return httpx.Response(200, json={"has_more": False, "data": []})
    if "gumroad" in h:
        return httpx.Response(200, json={"success": True, "sales": [
            {"id": "gr_qa_1", "price": 2900, "created_at": "2026-01-02T00:00:00Z", "refunded": False, "gumroad_fee": 290,
             "referrer": "instagram"}], "next_page_url": None})
    return httpx.Response(401, json={"error": "stub: not authorized"})


checkout_sync._transport = httpx.MockTransport(_checkout)

from app import main  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402


@main.app.get("/api/__qa/blocked")
def _blocked():
    return JSONResponse({**BLOCKED, "dns_stubbed": DNS["n"]})


# The catch-all SPA route was registered first; move ours ahead of it.
main.app.router.routes.insert(0, main.app.router.routes.pop())

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(main.app, host="127.0.0.1", port=port, log_level="warning")
