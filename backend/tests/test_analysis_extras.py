"""OCR (Apple Vision helper), local-embedding sampling/clustering, and one-click model downloads.
External pieces (the Swift binary, Ollama) are mocked so this runs on Linux CI; one real OCR test runs only on a Mac."""
import io
import json

import numpy as np
import pytest

from app import jobs, settings_store
from app.ai import embeddings, pipeline, rules
from app.ingest import ocr

from .conftest import drain


def _audience(client, name):
    settings_store.set_many({"ai_provider": "rules"})
    return client.post("/api/audiences", json={"org_name": name}).json()["id"]


def _png() -> bytes:
    from PIL import Image
    b = io.BytesIO()
    Image.new("RGB", (40, 20), "white").save(b, "PNG")
    return b.getvalue()


def _blank_pdf(pages=2) -> bytes:
    from pypdf import PdfWriter
    w = PdfWriter()
    for _ in range(pages):
        w.add_blank_page(width=200, height=200)
    b = io.BytesIO()
    w.write(b)
    return b.getvalue()


def _source(client, aid, name):
    return next(s for s in client.get(f"/api/audiences/{aid}/sources").json() if s.get("filename") == name or s.get("title") in (name, name.rsplit(".", 1)[0]))


# ---------- OCR ----------

def test_scanned_pdf_uses_ocr(client, monkeypatch):
    calls = []

    def fake(path, pages=None, timeout=600):
        calls.append(pages)
        return [{"page": 1, "text": "I would pay for a meal plan under $30", "confidence": 0.95},
                {"page": 2, "text": "zz", "confidence": 0.1}]  # low confidence → ignored
    monkeypatch.setattr(ocr, "recognize", fake)
    aid = _audience(client, "OCR PDF")
    client.post(f"/api/audiences/{aid}/sources/upload", files={"files": ("scan.pdf", _blank_pdf(2), "application/pdf")})
    drain()
    s = _source(client, aid, "scan.pdf")
    assert s["status"] == "ready", s
    assert calls == [None]  # whole document had no text layer → OCR all pages
    assert any("OCR" in o for o in s["obtained"])
    assert any("1 page had no text layer" in m for m in s["missing"])
    units, _ = pipeline.build_units(aid)
    assert any("meal plan under $30" in u["text"] for u in units)


def test_scanned_pdf_reports_ocr_unavailable(client, monkeypatch):
    def unavailable(*a, **k):
        raise ocr.OCRUnavailable(ocr.UNAVAILABLE_NOTE)
    monkeypatch.setattr(ocr, "recognize", unavailable)
    aid = _audience(client, "OCR none")
    client.post(f"/api/audiences/{aid}/sources/upload", files={"files": ("scan2.pdf", _blank_pdf(1), "application/pdf")})
    drain()
    s = _source(client, aid, "scan2.pdf")
    assert s["status"] == "failed"
    assert any("unavailable" in m for m in s["missing"]), s["missing"]


def test_image_upload_is_ocrd(client, monkeypatch):
    monkeypatch.setattr(ocr, "recognize", lambda p, pages=None, timeout=600:
                        [{"page": 1, "text": "Where can I buy this kit?", "confidence": 0.9}])
    aid = _audience(client, "OCR image")
    client.post(f"/api/audiences/{aid}/sources/upload", files={"files": ("shot.png", _png(), "image/png")})
    drain()
    s = _source(client, aid, "shot.png")
    assert s["status"] == "ready", s
    assert any("OCR" in o for o in s["obtained"])
    assert any("vision" in m.lower() for m in s["missing"])  # no vision model configured


def test_ocr_unavailable_off_mac(monkeypatch):
    monkeypatch.setenv("AUDIENCEOS_NO_OCR", "1")
    assert ocr.available() is False
    if not ocr.binary_path().exists():
        with pytest.raises(ocr.OCRUnavailable):
            ocr.ensure_binary()


@pytest.mark.skipif(not ocr.available(), reason="needs macOS + swiftc")
def test_real_vision_ocr_on_mac(tmp_path):
    from PIL import Image, ImageDraw, ImageFont
    img = Image.new("RGB", (1200, 220), "white")
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 64)
    except OSError:
        pytest.skip("no system font")
    ImageDraw.Draw(img).text((30, 60), "Starter collapses on day five", fill="black", font=font)
    png = tmp_path / "real.png"
    img.save(png)
    pdf = tmp_path / "real.pdf"
    img.save(pdf, "PDF", resolution=150)
    for f in (png, pdf):
        res = ocr.recognize(f)
        assert res and "collapses" in res[0]["text"].lower(), res


# ---------- embeddings ----------

class _Resp:
    def __init__(self, data, status=200):
        self._d, self.status_code = data, status

    def json(self):
        return self._d

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)


TOPICS = ["sourdough starter", "budget meal prep", "travel with kids"]


def _vec(text):
    v = np.zeros(8, dtype=np.float32)
    for i, t in enumerate(TOPICS):
        if t in text:
            v[i] = 1.0
    v[7] = 0.05 * (hash(text) % 7)
    return v.tolist()


@pytest.fixture()
def fake_ollama(monkeypatch):
    seen = {"embed_calls": 0}

    def get(url, timeout=None):
        return _Resp({"models": [{"name": "qwen2.5:7b"}, {"name": "nomic-embed-text:latest"}]})

    def post(url, json=None, timeout=None):
        assert url.endswith("/api/embed") and json["model"] == "nomic-embed-text"
        seen["embed_calls"] += 1
        return _Resp({"embeddings": [_vec(t) for t in json["input"]]})
    monkeypatch.setattr(embeddings.httpx, "get", get)
    monkeypatch.setattr(embeddings.httpx, "post", post)
    settings_store.set_many({"use_embeddings": True, "embedding_model": "nomic-embed-text"})
    return seen


def test_embedding_model_name_matching():
    assert embeddings.is_installed("nomic-embed-text", ["nomic-embed-text:latest"])
    assert not embeddings.is_installed("nomic-embed-text:v1.5", ["nomic-embed-text:latest"])
    assert not embeddings.is_installed("nomic-embed-text", ["qwen2.5:7b"])


def test_no_embed_model_falls_back(monkeypatch):
    monkeypatch.setattr(embeddings.httpx, "get", lambda url, timeout=None: _Resp({"models": [{"name": "qwen2.5:7b"}]}))
    assert embeddings.embed(["a", "b"]) is None
    sigs = [{"summary": s} for s in ["starter dies fast", "starter collapses", "meal prep cost", "meal prep budget",
                                     "kids travel", "travel with toddlers"]]
    out = rules.cluster_signals(sigs)
    assert out and "Keyword grouping" in out[0]["description"]


def test_stratified_sample_covers_quiet_topic(fake_ollama):
    loud = [{"text": f"budget meal prep idea {i}", "likes": 1000 - i} for i in range(80)]
    quiet = [{"text": f"travel with kids question {i}", "likes": 1} for i in range(20)]
    items = loud + quiet  # priority order: most-liked first
    sample, info = embeddings.stratified_sample(items, 30)
    assert info["method"] == "embedding" and len(sample) == 30
    assert sum("travel" in s["text"] for s in sample) >= 3  # likes-only sampling would pick zero
    assert sum("travel" in s["text"] for s in items[:30]) == 0


def test_rules_clustering_uses_embeddings(fake_ollama):
    sigs = [{"summary": f"{t} problem {i}"} for t in TOPICS for i in range(4)]
    out = rules.cluster_signals(sigs, max_clusters=3)
    assert "embeddings" in out[0]["description"]
    for c in out:  # each group is one topic
        assert len({next(t for t in TOPICS if t in sigs[i]["summary"]) for i in c["signal_ids"]}) == 1


def test_assign_attaches_overflow_signals(fake_ollama):
    texts = ["sourdough starter dies", "sourdough starter weak", "budget meal prep cost", "sourdough starter mold", "unrelated"]
    themes = [{"label": "Starter", "signal_ids": [0, 1]}, {"label": "Budget", "signal_ids": [2]}]
    got = embeddings.assign(themes, texts, [3, 4])
    assert got.get(3) == 0 and 4 not in got  # "unrelated" stays out


def test_big_comment_set_analysis_records_sampling(client, fake_ollama, monkeypatch):
    monkeypatch.setattr(pipeline, "MAX_COMMENTS", 40)
    aid = _audience(client, "Big set")
    lines = [f"budget meal prep tip number {i} please" for i in range(60)] + \
            [f"how do I handle travel with kids on trip {i}?" for i in range(15)]
    client.post(f"/api/audiences/{aid}/sources/text", json={"text": "\n".join(lines), "as_comments": True, "platform": "youtube"})
    drain()
    units, meta = pipeline.build_units(aid)
    assert meta["comments_analyzed"] == 40 and meta["comment_sampling"]["method"] == "embedding"
    unk = pipeline.compute_unknowns(meta, None, [], type("P", (), {"is_llm": False, "name": "rules", "external": False})())
    assert any("topic groups" in u for u in unk), unk


# ---------- model downloads ----------

class _Stream:
    def __init__(self, lines, status=200):
        self.lines, self.status_code, self.text = lines, status, "boom"

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return b""

    def iter_lines(self):
        yield from (json.dumps(l) for l in self.lines)


def test_one_click_vision_download_sets_model(client, monkeypatch):
    import httpx
    settings_store.set_many({"ollama_vision_model": ""})
    lines = [{"status": "pulling manifest"},
             {"status": "pulling", "digest": "a", "total": 100, "completed": 50},
             {"status": "pulling", "digest": "b", "total": 100, "completed": 100},
             {"status": "pulling", "digest": "a", "total": 100, "completed": 100},
             {"status": "success"}]
    monkeypatch.setattr(httpx, "stream", lambda *a, **k: _Stream(lines))
    pre = client.get("/api/models/presets").json()
    assert {p["model"] for p in pre["presets"]} >= {"qwen2.5vl:3b", "nomic-embed-text"}
    jid = client.post("/api/models/pull", json={"model": "qwen2.5vl:3b", "purpose": "vision"}).json()["job_id"]
    again = client.post("/api/models/pull", json={"model": "qwen2.5vl:3b", "purpose": "vision"}).json()["job_id"]
    assert again == jid  # no duplicate downloads
    drain()
    j = client.get(f"/api/jobs/{jid}").json()
    assert j["status"] == "done" and "vision model" in j["message"], j
    assert settings_store.get("ollama_vision_model") == "qwen2.5vl:3b"
    settings_store.set_many({"ollama_vision_model": ""})


def test_embedding_download_and_failures(client, monkeypatch):
    import httpx
    monkeypatch.setattr(httpx, "stream", lambda *a, **k: _Stream([{"status": "pulling manifest"}, {"status": "success"}]))
    jid = client.post("/api/models/pull", json={"model": "nomic-embed-text", "purpose": "embedding"}).json()["job_id"]
    drain()
    assert client.get(f"/api/jobs/{jid}").json()["status"] == "done"
    assert settings_store.get("use_embeddings") is True
    # Truncated stream (no "success") must fail, not report a finished download.
    monkeypatch.setattr(httpx, "stream", lambda *a, **k: _Stream([{"status": "pulling", "digest": "x", "total": 9, "completed": 1}]))
    jid = client.post("/api/models/pull", json={"model": "qwen2.5vl:7b", "purpose": "vision"}).json()["job_id"]
    drain()
    j = client.get(f"/api/jobs/{jid}").json()
    assert j["status"] == "failed" and "ended before" in j["error"]
    monkeypatch.setattr(httpx, "stream", lambda *a, **k: _Stream([{"error": "pull model manifest: file does not exist"}]))
    jid = client.post("/api/models/pull", json={"model": "nope:1b"}).json()["job_id"]
    drain()
    assert client.get(f"/api/jobs/{jid}").json()["status"] == "failed"
    assert client.post("/api/models/pull", json={"model": "x; rm -rf /"}).status_code == 422
    assert client.post("/api/models/pull", json={"model": "x", "purpose": "evil"}).status_code == 422
