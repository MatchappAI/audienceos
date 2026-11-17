"""Regression tests for bugs found by operating the live UI (live QA pass, 2026-11-16)."""
import httpx

from app.ai import providers


def _org(client, name):
    a = client.post("/api/audiences", json={"org_name": name}).json()
    return a, a["organization_id"]


def _deal(client, org, pct, replaces=None, **kw):
    body = {"creator_share_pct": pct, "basis": "contribution", **kw}
    if replaces is not None:
        body["replaces_deal_id"] = replaces
    return client.post(f"/api/creators/{org}/deal", json=body)


def test_stale_deal_editor_cannot_overwrite_newer_terms(client):
    a, org = _org(client, "TwoWindows")
    first = _deal(client, org, 70, replaces="")          # opened with no deal yet
    assert first.status_code == 200
    d1 = first.json()["deal"]["id"]
    assert _deal(client, org, 65, replaces=d1).status_code == 200   # window B saves 65%
    stale = _deal(client, org, 70, replaces=d1, notes="window A")   # window A still thinks d1 is current
    assert stale.status_code == 409 and "another window" in stale.text
    assert client.get(f"/api/creators/{org}/statement").json()["deal"]["creator_share_pct"] == 65


def test_stale_first_deal_cannot_overwrite_a_deal_made_meanwhile(client):
    a, org = _org(client, "FirstDealRace")
    assert _deal(client, org, 60, replaces="").status_code == 200
    r = _deal(client, org, 70, replaces="")              # second window also opened when there was no deal
    assert r.status_code == 409
    assert client.get(f"/api/creators/{org}/statement").json()["deal"]["creator_share_pct"] == 60


def test_deal_without_replaces_field_still_works(client):
    a, org = _org(client, "OldClient")
    assert _deal(client, org, 70).status_code == 200
    assert _deal(client, org, 50).status_code == 200
    assert client.get(f"/api/creators/{org}/statement").json()["deal"]["creator_share_pct"] == 50


def test_blank_names_are_refused(client):
    assert client.post("/api/audiences", json={"org_name": "   "}).status_code == 422
    a, org = _org(client, "Named")
    for body in ({"org_name": ""}, {"org_name": "  "}, {"name": ""}):
        r = client.patch(f"/api/audiences/{a['id']}", json=body)
        assert r.status_code == 422 and "blank" in r.text
    after = client.get(f"/api/audiences/{a['id']}").json()
    assert after["org_name"] == "Named" and after["name"]
    ok = client.patch(f"/api/audiences/{a['id']}", json={"org_name": "  Renamed  "}).json()
    assert ok["org_name"] == "Renamed"


def test_blank_product_name_refused_and_partial_patch_keeps_other_fields(client):
    a, _ = _org(client, "ProdCo")
    p = client.post("/api/products", json={"audience_id": a["id"], "name": "Kit", "price": 30,
                                           "checkout_url": "https://x.example/kit"}).json()
    assert client.patch(f"/api/products/{p['id']}", json={"name": " "}).status_code == 422
    client.patch(f"/api/products/{p['id']}", json={"price": 45})          # window B
    q = client.patch(f"/api/products/{p['id']}", json={"notes": "A"}).json()  # window A sends only what it changed
    assert q["price"] == 45 and q["notes"] == "A" and q["name"] == "Kit"


def test_engine_failure_message_is_plain(monkeypatch):
    def boom(*a, **k):
        raise httpx.RemoteProtocolError("Server disconnected")
    monkeypatch.setattr(providers.httpx, "post", boom)
    try:
        providers.OllamaProvider("qwen2.5:7b")._chat("sys", "user", None, None, 100)
    except providers.ProviderUnavailable as e:
        assert "local AI engine (Ollama) stopped" in str(e) and "try again" in str(e)
    else:
        raise AssertionError("expected ProviderUnavailable")
