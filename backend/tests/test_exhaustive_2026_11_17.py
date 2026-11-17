"""Regression tests for defects found by the model-based pass (qa/mbt, 2026-11-17). Each test is the minimal
sequence the generator shrank the failure to."""
import json

from app import db

CHECKS = {k: True for k in ("creator_approved", "claims_checked", "checkout_tested", "delivery_tested", "support_ready")}


def _org(client, name):
    a = client.post("/api/audiences", json={"org_name": name}).json()
    return a, a["organization_id"]


def _product(client, aud, **kw):
    return client.post("/api/products", json={"audience_id": aud["id"], "name": "Kit", "price": 29,
                                              "checkout_url": "https://x.example/kit", **kw}).json()


def _opp(client, aud_id, name="Idea"):
    """An opportunity row as an analysis would leave it (tests don't run the AI)."""
    oid = db.new_id("op")
    with db.tx() as c:
        db.insert(c, "opportunities", {"id": oid, "audience_id": aud_id, "name": name, "status": "proposed", "price": 29,
                                       "created_at": db.now(), "updated_at": db.now()})
    return oid


# M-01: a sale of $0.015 was stored as typed; the statement showed gross $0.01 (float rounding) while the shares were
# taken from the unrounded amount, so creator + agency no longer matched the line.
def test_money_is_stored_in_whole_cents(client):
    a, org = _org(client, "Cents")
    p = _product(client, a)
    client.post(f"/api/creators/{org}/deal", json={"creator_share_pct": 50, "basis": "net_sales"})
    r = client.post(f"/api/products/{p['id']}/sales", json={"order_ref": "c1", "amount": 0.015, "fee": 0.004})
    assert r.status_code == 200
    s = r.json()["sales"][0]
    assert s["amount"] == 0.02 and s["fee"] == 0.0
    client.post(f"/api/products/{p['id']}/costs", json={"amount": 10.005, "shared": True})
    client.post(f"/api/creators/{org}/payouts", json={"date": "2026-02-01", "amount": 0.015})
    st = client.get(f"/api/creators/{org}/statement").json()
    line = st["lines"][0]
    assert line["gross"] == 0.02 and line["creator_share"] + line["agency_share"] == line["split_base"]
    assert st["paid_out"] == 0.02
    assert client.get(f"/api/products/{p['id']}").json()["costs"][0]["amount"] == 10.01
    csv_text = "order_id,amount,fee\nk1,33.335,0.005\n"
    r = client.post(f"/api/products/{p['id']}/sales/import", files={"file": ("o.csv", csv_text, "text/csv")})
    assert r.json()["result"]["imported"] == 1
    assert next(x for x in r.json()["product"]["sales"] if x["order_ref"] == "k1")["amount"] == 33.34
    assert client.post(f"/api/creators/{org}/payouts", json={"date": "2026-02-01", "amount": 0.004}).status_code == 422


# M-02: one request with Infinity / 1e999 / 1e308 / 2**63 in a number field was stored, and from then on every page
# reading that record answered 500 ("poisoned" product, experiment or deal).
def test_non_finite_and_huge_numbers_are_refused_everywhere(client):
    a, org = _org(client, "Poison")
    p = _product(client, a)
    x = client.post("/api/experiments", json={"audience_id": a["id"]}).json()
    raw = [("POST", f"/api/products/{p['id']}/sales", '{"order_ref":"i1","amount":Infinity}'),
           ("POST", f"/api/products/{p['id']}/sales", '{"order_ref":"i2","amount":1e308}'),
           ("POST", f"/api/products/{p['id']}/costs", '{"amount":"1e999"}'),
           ("POST", "/api/products", json.dumps({"audience_id": a["id"], "price": "Infinity"})),
           ("PATCH", f"/api/products/{p['id']}", '{"price":1e999}'),
           ("POST", f"/api/experiments/{x['id']}/events", '{"gross_revenue":"Infinity"}'),
           ("POST", f"/api/experiments/{x['id']}/events", '{"landing_visits":9223372036854775808}'),
           ("POST", "/api/experiments", json.dumps({"audience_id": a["id"], "target_exposure": 2**63})),
           ("POST", f"/api/creators/{org}/deal", '{"creator_share_pct":50,"basis":"net_sales","min_guarantee_monthly":Infinity}'),
           ("POST", f"/api/creators/{org}/deal", '{"creator_share_pct":50,"basis":"net_sales","guarantee_months":9223372036854775808}'),
           ("POST", f"/api/creators/{org}/payouts", '{"date":"2026-01-01","amount":1e308}'),
           ("POST", f"/api/audiences/{a['id']}/channels", '{"follower_count":9223372036854775808}')]
    for method, path, body in raw:
        r = client.request(method, path, content=body, headers={"content-type": "application/json"})
        assert r.status_code == 422, (path, body, r.status_code, r.text[:200])
    for path in (f"/api/products/{p['id']}", f"/api/experiments/{x['id']}", f"/api/creators/{org}/statement", "/api/dashboard"):
        assert client.get(path).status_code == 200
    # a CSV cell "inf" is not a number either
    r = client.post(f"/api/products/{p['id']}/sales/import", files={"file": ("o.csv", "order_id,amount\nz1,inf\n", "text/csv")})
    assert r.json()["result"]["imported"] == 0


# M-03: more purchases than visits (a typo) made the confidence interval take sqrt of a negative: the experiment page,
# the experiments list and the dashboard all answered 500 until the row was deleted by hand.
def test_more_purchases_than_visits_does_not_break_the_experiment(client):
    a, _ = _org(client, "Typo")
    x = client.post("/api/experiments", json={"audience_id": a["id"]}).json()
    r = client.post(f"/api/experiments/{x['id']}/events", json={"landing_visits": 1, "purchases": 5, "gross_revenue": 10})
    assert r.status_code == 200
    m = r.json()["metrics"]
    assert m["purchase_conversion_ci95"] is None and any("More purchases" in n for n in m["notes"])
    assert client.get("/api/experiments").status_code == 200 and client.get("/api/dashboard").status_code == 200


# M-04: the page hides Reject once an opportunity has a product, but the API (and the experiment "Stop" decision)
# still rejected it, leaving a launched product under a rejected idea that Restore then sent back to "proposed".
def test_opportunity_with_a_product_is_not_rejected(client):
    a, _ = _org(client, "HasProduct")
    oid = _opp(client, a["id"])
    assert client.post("/api/products", json={"opportunity_id": oid, "checkout_url": "https://x.example"}).status_code == 200
    r = client.patch(f"/api/opportunities/{oid}", json={"status": "rejected"})
    assert r.status_code == 409 and "Retire the product" in r.json()["detail"]
    x = client.post("/api/experiments", json={"opportunity_id": oid}).json()
    client.post(f"/api/experiments/{x['id']}/decision", json={"decision": "stop"})
    o = client.get(f"/api/opportunities/{oid}").json()
    assert o["status"] == "testing"
    assert client.get(f"/api/experiments/{x['id']}").json()["decision"] == "stop"
    # without a product, both still work
    o2 = _opp(client, a["id"], "Other")
    assert client.patch(f"/api/opportunities/{o2}", json={"status": "rejected"}).status_code == 200


# M-05: values the database refuses (CHECK / NOT NULL) reached it and came back as 500.
def test_invalid_status_and_null_names_are_refused_or_ignored(client):
    a, _ = _org(client, "Checks")
    assert client.patch(f"/api/audiences/{a['id']}", json={"status": "deleted"}).status_code == 422
    assert client.patch(f"/api/audiences/{a['id']}", json={"status": "archived"}).status_code == 200
    p = _product(client, a)
    r = client.patch(f"/api/products/{p['id']}", json={"name": None, "status": None, "notes": "kept"})
    assert r.status_code == 200 and r.json()["name"] == "Kit" and r.json()["status"] == "draft" and r.json()["notes"] == "kept"
    x = client.post("/api/experiments", json={"audience_id": a["id"], "name": "Named"}).json()
    r = client.patch(f"/api/experiments/{x['id']}", json={"name": None, "status": None})
    assert r.status_code == 200 and r.json()["name"] == "Named"


# M-06: an unknown AI provider (any text was accepted) made the dashboard and "Draft asset" answer 500.
def test_settings_with_fixed_choices_refuse_other_values(client):
    for k, v in (("ai_provider", "bogus"), ("theme", "neon"), ("whisper_model", "../../x")):
        r = client.put("/api/settings", json={"values": {k: v}})
        assert r.status_code == 400 and "must be one of" in r.json()["detail"]
    assert client.get("/api/dashboard").status_code == 200
    assert client.put("/api/settings", json={"values": {"theme": "dark"}}).status_code == 200
    client.put("/api/settings", json={"values": {"theme": "system"}})


# M-07: a malformed link (over-long name, RTL control character, bad port) raised UnicodeError/ValueError inside the
# safety check: competitor "Add" answered 500 and URL imports failed with a raw error.
def test_malformed_links_are_refused_in_plain_words(client):
    from app import security
    for u in ("https://" + "a" * 80, "https://مرحبا ‮abc", "https://x.example:abc/", "https://../../etc/passwd"):
        try:
            security.check_url(u)
            raise AssertionError(u)
        except security.FetchError as e:
            assert "valid web address" in str(e) or "host name" in str(e)
    a, _ = _org(client, "Links")
    r = client.post(f"/api/audiences/{a['id']}/competitors", json={"name": "Rival", "url": "https://" + "a" * 80})
    assert r.status_code == 200 and "valid web address" in r.json()["note"]


# M-08: CSV files with a cell bigger than Python's csv limit answered 500.
def test_csv_with_a_huge_cell_is_refused_plainly(client):
    a, _ = _org(client, "HugeCSV")
    p = _product(client, a)
    x = client.post("/api/experiments", json={"audience_id": a["id"]}).json()
    body = "order_id,amount\n" + "x" * 2_000_000 + ",1\n"
    for path in (f"/api/products/{p['id']}/sales/import", f"/api/experiments/{x['id']}/import"):
        r = client.post(path, files={"file": ("big.csv", body, "text/csv")})
        assert r.status_code == 400 and "can't be read" in r.json()["detail"]


# M-09: names and audience quotes starting with = + - @ were written raw into the statement, payout and report CSVs,
# where a spreadsheet runs them as formulas.
def test_csv_exports_neutralise_formulas(client):
    from app.csvsafe import safe_cell
    assert safe_cell("=HYPERLINK(\"x\")") == "'=HYPERLINK(\"x\")" and safe_cell("-5.00") == "-5.00" and safe_cell("@x") == "'@x"
    a, org = _org(client, "=HYPERLINK(\"http://evil\",\"x\")")
    p = _product(client, a, name="+SUM(1,1)")
    client.post(f"/api/creators/{org}/deal", json={"creator_share_pct": 50, "basis": "net_sales"})
    client.post(f"/api/products/{p['id']}/sales", json={"order_ref": "f1", "amount": 10})
    client.patch(f"/api/creators/{org}", json={"contact_name": "@SUM(A1)", "contact_email": "pay@example.com"})
    st = client.get(f"/api/creators/{org}/statement.csv").text
    assert "'+SUM(1,1)" in st and "\n+SUM" not in st
    pay = client.get("/api/payouts/export.csv").text
    assert "'@SUM(A1)" in pay and ",@SUM" not in pay
