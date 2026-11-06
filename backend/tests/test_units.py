import pytest

from app import security
from app.ai import rules
from app.ai.evidence import locate_quote, timestamp_before
from app.services import economics, experiments as ex, scoring


def test_quote_must_exist_in_source():
    src = "Hi! My starter always collapses after day 5 — what am I doing wrong?"
    hit = locate_quote("my starter always collapses after day 5", src)
    assert hit and hit[0].startswith("My starter")
    assert locate_quote("I would pay $100 for a course", src) is None  # invented quote rejected


def test_near_verbatim_quote_accepted_and_replaced_with_source_text():
    src = "[0:12] Around day four or five the early bacteria die off and the starter looks dead."
    hit = locate_quote("around day four or five, the early bacteria die off and the starter look dead", src)
    assert hit is not None
    assert timestamp_before(src, hit[1]) == "0:12"


@pytest.mark.parametrize("quote,label,expected", [
    ("My crumb is always gummy in the middle.", "existing_spending", "engagement"),
    ("Why is my crumb gummy?", "verified_purchase", "curiosity"),
    ("I paid $120 for a class", "existing_spending", "existing_spending"),
    ("Would buy a kit from you", "paid_solution_request", "paid_solution_request"),
])
def test_strong_intent_requires_supporting_words(quote, label, expected):
    assert rules.check_intent(label, quote) == expected


def test_rules_engine_finds_buying_language():
    sigs = rules.analyze_unit("Where can I buy that banneton? I'd pay for a course.", "audience")
    levels = {s["intent_level"] for s in sigs}
    assert "buying_question" in levels and "paid_solution_request" in levels


def test_cluster_stats_do_not_double_count_one_person():
    one_person = [{"intent_level": "paid_solution_request", "author_ref": "a_1", "source_id": "s1", "platform": "x",
                   "date": None, "voice": "audience"}] * 5
    st = scoring.cluster_stats(one_person)
    assert st["unique_authors"] == 1 and st["signal_count"] == 5


def test_score_total_bounds():
    assert scoring.total({k: 5 for k in scoring.settings_store.DEFAULT_RUBRIC}) == 100
    assert scoring.total({k: 1 for k in scoring.settings_store.DEFAULT_RUBRIC}) == 0


def test_economics_formulas():
    s = economics.scenario(100, 10, 450, {"payment_fee_pct": 3, "payment_fee_fixed": 0.3, "reach": 10000,
                                          "exposure_pct": 10, "rates_pct": [1]})
    assert s["fee_per_sale"] == 3.3 and s["unit_contribution"] == 86.7
    assert s["breakeven_units"] == 6  # ceil(450 / 86.7)
    assert s["rows"][0]["buyers"] == 10 and s["rows"][0]["net_contribution"] == round(10 * 86.7 - 450, 2)


def test_experiment_metrics_and_separate_denominators():
    exp = {"payment_fee_pct": 10, "payment_fee_fixed": 1, "criteria": [], "target_exposure": None}
    events = [{"impressions": 1000, "clicks": 50, "landing_visits": 40, "checkout_visits": 10, "purchases": 4,
               "gross_revenue": 200, "refunds": 1, "refund_amount": 50, "payment_fees": None, "other_costs": 20}]
    m = ex.compute(exp, events, [])["values"]
    assert m["ctr"] == 5.0 and m["purchase_conversion"] == 10.0 and m["checkout_conversion"] == 40.0
    assert m["net_sales"] == 150 and m["payment_fees"] == 24  # 200*10% + 4*1
    assert m["contribution_margin"] == 106 and m["rpm"] == 150.0 and m["revenue_per_visitor"] == 3.75


def test_missing_denominator_is_none_not_zero():
    m = ex.compute({"payment_fee_pct": 0, "payment_fee_fixed": 0}, [{"purchases": 2, "gross_revenue": 20}], [])["values"]
    assert m["ctr"] is None and m["purchase_conversion"] is None and m["rpm"] is None and m["net_sales"] == 20


def test_recommendation_rules():
    exp = {"criteria": [{"metric": "purchases", "op": ">=", "value": 10}], "target_exposure": 100, "end_date": None}
    m = ex.compute({"payment_fee_pct": 0, "payment_fee_fixed": 0}, [{"landing_visits": 50, "purchases": 1}], [])
    assert ex.evaluate(exp, m)["recommendation"] == "continue"
    m = ex.compute({"payment_fee_pct": 0, "payment_fee_fixed": 0}, [{"landing_visits": 200, "purchases": 12}], [])
    assert ex.evaluate(exp, m)["recommendation"] == "go"


@pytest.mark.parametrize("url", ["http://127.0.0.1/x", "http://localhost:8760/api", "http://10.0.0.5/",
                                 "http://169.254.169.254/latest", "file:///etc/passwd", "http://example.com:8080/",
                                 "http://user:pw@example.com/"])
def test_ssrf_blocked(url):
    with pytest.raises(security.FetchError):
        security.check_url(url)


def test_file_sniffing_rejects_disguised_binaries():
    assert security.classify_file("notes.pdf", b"MZ\x90\x00") is None
    assert security.classify_file("run.sh", b"#!/bin/sh") is None
    assert security.classify_file("data.csv", b"a,b\n1,2") == "csv"
    assert security.classify_file("x.txt", b"\x7fELF\x02") is None


@pytest.mark.parametrize("quote,label", [
    # Mislabeled in an early scratch run (analysis an_50a6d9292370414f, before the guard existed)
    ("Living at 7000 ft and my dough overproofs constantly. Help", "existing_spending"),
    ("Do you have a printable feeding schedule? I keep forgetting when to feed it", "existing_spending"),
    ("Do you have a printable feeding schedule?", "verified_purchase"),
    ("My loaf is flat again", "paid_solution_request"),
])
def test_guard_never_keeps_unsupported_strong_intent(quote, label):
    assert rules.guard_intent(label, quote) not in rules.STRONG_INTENTS


@pytest.mark.parametrize("quote,label", [
    ("I paid $120 for a class", "existing_spending"),
    ("We pay $15 a month for this subscription", "existing_spending"),
    ("Where can I buy that banneton?", "buying_question"),
    ("I bought your starter kit", "verified_purchase"),
])
def test_guard_keeps_supported_strong_intent(quote, label):
    assert rules.guard_intent(label, quote) == label


@pytest.mark.parametrize("quote,label,expected", [
    ("Where can I buy the lame you use", "paid_solution_request", "buying_question"),
    ("Is a proofing box worth it? Which one should I buy", "paid_solution_request", "buying_question"),
    ("I have bought two books and a course and I still don't get it", "existing_spending", "existing_spending"),
])
def test_guard_prefers_explicit_buying_language(quote, label, expected):
    assert rules.guard_intent(label, quote) == expected


def test_store_signals_applies_the_guard_on_every_path():
    """Whatever stage produced a signal, storing it re-checks the intent against the quote."""
    from app import db
    from app.ai import pipeline
    from fastapi.testclient import TestClient
    from app import main
    with TestClient(main.app, headers={"x-audienceos": "1"}) as cl:
        a = cl.post("/api/audiences", json={"org_name": "Guard Creator"}).json()
    an = db.new_id("an")
    with db.tx() as c:
        db.insert(c, "analyses", {"id": an, "audience_id": a["id"], "provider": "rules", "status": "running",
                                  "started_at": db.now()})
        sid = db.new_id("src")
        db.insert(c, "sources", {"id": sid, "audience_id": a["id"], "kind": "text", "platform": "other",
                                 "status": "ready", "created_at": db.now()})
    quote = "Living at 7000 ft and my dough overproofs constantly. Help"
    unit = {"kind": "comment", "source_id": sid, "content_item_id": None, "comment_id": None, "author_ref": "a1",
            "offset": 0, "text": quote}
    sigs = pipeline.store_signals(a["id"], an, [{"signal_type": "frustration", "intent_level": "existing_spending",
                                                 "summary": "altitude", "quote": quote, "start": 0, "unit": unit}])
    assert sigs[0]["intent_level"] == "engagement"
    assert db.scalar("SELECT intent_level FROM signals WHERE id=?", (sigs[0]["id"],)) == "engagement"


@pytest.mark.parametrize("text,expected", [
    ("Bakers at altitude (T1, T3) struggle with overproofing.", "Bakers at altitude struggle with overproofing."),
    ("Starter dies around day 5 [E1-E3].", "Starter dies around day 5."),
    ("As seen in E4, E7 and E9, people want a schedule.", "As seen, people want a schedule."),
    ("Based on themes T2/T5 the buyer is a beginner.", "The buyer is a beginner."),
    ("No references here, 7000 ft and a T-shirt.", "No references here, 7000 ft and a T-shirt."),
])
def test_theme_and_evidence_ids_are_stripped_from_prose(text, expected):
    assert rules.strip_refs(text) == expected
    assert not __import__("re").search(r"\b[TE]\d+\b", rules.strip_refs(text))


def test_opportunity_prose_has_no_reference_ids():
    """Bug 1: a model that writes 'T1, T3' into problem text must not have it stored or reach hypotheses."""
    from app.ai import pipeline, schemas
    leaked = {"name": "Altitude Kit (T1)", "buyer": "High-altitude bakers (T1, T3)",
              "problem": "Dough overproofs at altitude (T1, T3); see E2 and E5.", "product_type": "toolkit",
              "format_rationale": "Per T1 a chart works", "price": 19, "price_model": "one-time",
              "price_rationale": "Cheap vs class (E4)", "theme_ids": [1], "evidence_ids": [1],
              "alternatives": "Generic guides", "production": "Charts", "production_cost_estimate": 50,
              "fulfillment_cost_per_unit": 0, "delivery_difficulty": "low", "recurring": "none",
              "distribution": "Posts", "validation_experiment": "Pre-sell to T1 voices",
              "risks": ["T3 may be small"], "supported": ["E1 shows pain"], "assumed": [], "unknown": [],
              "scores": {k: 3 for k in schemas.ModelScores.model_fields if k != "rationale"} | {"rationale": "T1 strong"}}
    o = schemas.OpportunityDraft.model_validate(rules.strip_refs_deep(leaked))
    import re
    d = o.model_dump()
    d.pop("theme_ids"), d.pop("evidence_ids")
    assert not re.search(r"\b[TE]\d+\b", str(d)), d
    assert o.theme_ids == [1] and o.evidence_ids == [1]
    assert "never write T#" in pipeline.OPP_SYS


def test_asset_draft_without_title_is_accepted():
    """Live run: qwen2.5:7b returned {'markdown': ...} with no title twice and the whole draft was lost."""
    from app.ai import schemas
    d = schemas.AssetDraft.model_validate({"markdown": "## Offer\nBody"})
    assert d.title == "" and d.markdown.startswith("## Offer")


def test_claim_review_flags_possibly_invented_contact_details():
    from app.services import assets
    flags = assets.rule_flags("Join now at www.hearthandcrumb.com or email hello@hearth.co")
    assert any("invented" in f["problem"] for f in flags)
    assert not any("invented" in f["problem"] for f in assets.rule_flags("Fill in [your link] here."))


def test_price_mismatches_flags_other_amounts():
    from app.services.assets import price_mismatches
    a = {"content": "Join for just $50.00 per month. Bakers pay $120 for a class.", "data": {"copy": {"price_line": "$50/month"}}}
    assert price_mismatches(a, 39) == ["$50", "$120"]
    assert price_mismatches({"content": "Only $39 a month", "data": {}}, 39) == []
    assert price_mismatches(a, None) == []


def test_criteria_without_threshold_ask_for_one():
    from app.services.experiments import evaluate
    m = {"values": {"purchases": 12}, "totals": {"landing_visits": 400}, "has_data": True}
    ev = evaluate({"criteria": [{"metric": "purchases", "op": ">=", "value": ""}]}, m)
    assert ev["recommendation"] == "define" and "threshold" in ev["reason"]
    assert ev["criteria"][0]["no_threshold"] is True
    ev = evaluate({"criteria": [{"metric": "purchases", "op": ">=", "value": "10"}]}, m)
    assert ev["recommendation"] == "go"
