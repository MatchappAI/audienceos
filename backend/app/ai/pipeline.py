"""The audience intelligence pipeline. Multi-stage, each stage small, structured and validated.

Stage 1  Content classification         (AI)
Stage 2  Problem & intent extraction     (AI, per batch; every quote verified against the source)
Stage 3  Problem clustering              (AI; deterministic fallback)
Stage 4  Commercial intent per cluster   (computed from stored signals, not AI opinion)
Stage 5  Competitor research             (separate, optional job — see services/competitors.py)
Stage 6  Opportunity generation          (AI, must cite stored evidence)
Stage 7  Opportunity scoring             (data-derived + AI-rated criteria, configurable weights)
"""
import json
import logging

from .. import db, jobs, settings_store
from ..services import scoring
from . import providers, rules, schemas
from .evidence import locate_quote, timestamp_before

log = logging.getLogger("audienceos.pipeline")

MAX_COMMENTS = 600
CHUNK_CHARS = 1400
BATCH_CHARS = 2400


class AnalysisError(Exception):
    pass


# ---------- corpus ----------

def build_units(audience_id: str) -> tuple[list[dict], dict]:
    """Units are what the model sees: comments (C#) and chunks of content (D#)."""
    c = db.connect()
    try:
        items = db.rows(c.execute(
            "SELECT ci.*, s.voice AS src_voice FROM content_items ci JOIN sources s ON s.id=ci.source_id "
            "WHERE ci.audience_id=? AND length(ci.text) > 0 ORDER BY ci.published_at DESC, ci.created_at", (audience_id,)))
        comments = db.rows(c.execute(
            "SELECT * FROM comments WHERE audience_id=? AND is_duplicate=0 AND is_spam=0 "
            "ORDER BY COALESCE(likes,0) DESC, published_at DESC", (audience_id,)))
        n_dups = c.execute("SELECT COUNT(*) FROM comments WHERE audience_id=? AND is_duplicate=1", (audience_id,)).fetchone()[0]
        n_spam = c.execute("SELECT COUNT(*) FROM comments WHERE audience_id=? AND is_spam=1", (audience_id,)).fetchone()[0]
        frames = db.rows(c.execute(
            "SELECT mf.content_item_id, mf.timestamp_s, mf.description, mf.described_by FROM media_frames mf "
            "JOIN content_items ci ON ci.id=mf.content_item_id WHERE ci.audience_id=? AND mf.description IS NOT NULL",
            (audience_id,)))
    finally:
        c.close()
    units = []
    for it in items:
        voice = it["src_voice"] or "creator"
        text = it["text"]
        for k in range(0, len(text), CHUNK_CHARS):
            chunk = text[k:k + CHUNK_CHARS + 150]  # small overlap so quotes aren't cut
            units.append({"ref": f"D{len(units) + 1}", "kind": "content", "text": chunk, "offset": k,
                          "content_item_id": it["id"], "source_id": it["source_id"], "comment_id": None,
                          "platform": it["platform"], "date": it["published_at"], "author_ref": None, "voice": voice,
                          "title": it["title"]})
    analyzed = comments[:MAX_COMMENTS]
    for cm in analyzed:
        units.append({"ref": f"C{len(units) + 1}", "kind": "comment", "text": cm["text"], "offset": 0,
                      "content_item_id": cm["content_item_id"], "source_id": cm["source_id"], "comment_id": cm["id"],
                      "platform": cm["platform"], "date": cm["published_at"], "author_ref": cm["author_ref"],
                      "voice": "audience", "likes": cm["likes"]})
    meta = {"content_items": len(items), "comments_total": len(comments), "comments_analyzed": len(analyzed),
            "duplicates_excluded": n_dups, "spam_excluded": n_spam, "frames_described": len(frames),
            "frames": frames, "items": items}
    return units, meta


def batches(units: list[dict]):
    cur, size = [], 0
    for u in units:
        t = len(u["text"])
        if cur and size + t > BATCH_CHARS:
            yield cur
            cur, size = [], 0
        cur.append(u)
        size += t
    if cur:
        yield cur


def fmt_units(units):
    lines = []
    for u in units:
        who = "AUDIENCE COMMENT" if u["kind"] == "comment" else f"CREATOR CONTENT ({u.get('title') or 'untitled'})"
        lines.append(f"<unit ref=\"{u['ref']}\" type=\"{who}\">\n{u['text']}\n</unit>")
    return "<source_material>\n" + "\n".join(lines) + "\n</source_material>"


# ---------- run bookkeeping ----------

def start_run(audience_id, analysis_id, stage, provider, input_chars):
    rid = db.new_id("run")
    with db.tx() as c:
        db.insert(c, "ai_runs", {"id": rid, "audience_id": audience_id, "analysis_id": analysis_id, "stage": stage,
                                 "provider": provider.name, "model": provider.model or None,
                                 "external": int(provider.external), "input_chars": input_chars,
                                 "status": "running", "started_at": db.now()})
    return rid


def finish_run(rid, status="done", output=None, error=None, notes=None):
    with db.tx() as c:
        db.update(c, "ai_runs", rid, {"status": status, "finished_at": db.now(), "error": error, "notes": notes,
                                      "output_json": json.dumps(output, default=str)[:200_000] if output is not None else None})


# ---------- stages ----------

PROFILE_SYS = ("You are a careful audience researcher. Classify a creator's or business's content and audience. "
               "Only state what the material supports; cite unit refs for audience characteristics. "
               "Never infer sensitive personal attributes (health, ethnicity, religion, politics, sexuality, finances of "
               "individuals). Put anything uncertain under unknowns.")

EXTRACT_SYS = ("You extract audience problems and buying signals from source units. For each genuine signal, return "
               "the unit ref, a type, an intent level and a VERBATIM quote copied exactly from that unit. "
               "Intent levels, weakest to strongest: engagement (praise/reaction), curiosity (casual question), "
               "free_info_request (asks for free help/content), existing_spending (mentions money already spent on "
               "solutions), buying_question (asks where/what to buy, price), paid_solution_request (says they would pay "
               "or asks the creator to sell something), verified_purchase (says they bought something). "
               "Popularity is NOT willingness to pay. Skip pure praise, spam and off-topic chatter. "
               "Creator content: only extract problems the creator says their audience has. Return an empty list if "
               "there are no signals. Never paraphrase inside the quote field.")

CLUSTER_SYS = ("Group audience signals into distinct, SPECIFIC problem themes. Merge synonyms and near-duplicates into "
               "one theme, but never use broad buckets like 'general issues', 'process problems' or 'feedback'. "
               "Good labels name one concrete problem, e.g. 'Starter collapses in week one', 'Fitting the hobby into a "
               "9-to-5', 'Wants a structured paid course'. Use 4-10 themes. Every signal id appears in exactly one "
               "theme. Labels name the problem, not a product.")

OPP_SYS = ("You are a pragmatic product strategist for creators. Propose 3-5 credible products or services this "
           "audience could realistically be sold, grounded ONLY in the provided themes and evidence. Each must cite "
           "theme numbers (T#) and evidence numbers (E#). Prices are hypotheses to test, with reasoning based on the "
           "problem's value and any stated spending — do not invent market data or conversion rates. Consider many "
           "formats (templates, toolkits, courses, memberships, calculators, software, services, physical goods); do "
           "not default to an ebook. Prefer things that solve a real problem and can be delivered profitably. "
           "Score honestly; low scores are useful. List what is supported, assumed and unknown. Put theme and "
           "evidence numbers ONLY in theme_ids and evidence_ids — never write T#, E# or other reference numbers "
           "in name, buyer, problem, rationale, risks or any other text field; describe the problem in plain words.")


def stage_profile(provider, audience, units, meta, analysis_id):
    sample, size = [], 0
    for u in units:
        if u["kind"] == "content" and u["offset"] == 0 and size < 9000:
            sample.append({**u, "text": u["text"][:900]})
            size += 900
    for u in [u for u in units if u["kind"] == "comment"][:40]:
        sample.append(u)
    frames = "\n".join(f"- [model-generated visual description @ {f['timestamp_s']}s] {f['description']}"
                       for f in meta["frames"][:12])
    user = (f"Creator/business: {audience['org_name']}\nAudience name: {audience['name']}\n"
            f"Stated niche (from user): {audience.get('niche') or 'not given'}\n\n{fmt_units(sample)}"
            + (f"\n\nVisual observations:\n{frames}" if frames else ""))
    rid = start_run(audience["id"], analysis_id, "1 · content classification", provider, len(user))
    try:
        prof = provider.complete_json(PROFILE_SYS, user, schemas.Profile, max_tokens=2000)
    except Exception as e:
        finish_run(rid, "failed", error=str(e))
        raise
    by_ref = {u["ref"]: u for u in units}
    out = prof.model_dump()
    for ch in out["audience_characteristics"]:
        ev = []
        for r in ch.pop("refs"):
            u = by_ref.get(r.strip())
            if u:  # store a stable pointer to the original material, not the transient unit ref
                ev.append({"source_id": u["source_id"], "comment_id": u["comment_id"],
                           "content_item_id": u["content_item_id"], "excerpt": u["text"][:220]})
        ch["evidence"] = ev
        ch["supported"] = bool(ev)
    finish_run(rid, output=out)
    return out


def stage_extract(provider, audience, units, analysis_id, progress):
    by_ref = {u["ref"]: u for u in units}
    found, rejected = [], 0
    bl = list(batches(units))
    rid = start_run(audience["id"], analysis_id, "2 · problem & intent extraction", provider,
                    sum(len(u["text"]) for u in units))
    try:
        for i, b in enumerate(bl):
            progress(0.15 + 0.5 * i / max(1, len(bl)), f"Reading audience material ({i + 1}/{len(bl)})")
            if provider.is_llm:
                res = provider.complete_json(EXTRACT_SYS, fmt_units(b), schemas.ExtractionResult, max_tokens=3000)
                cands = [s.model_dump() for s in res.signals]
            else:
                cands = [{**s, "ref": u["ref"]} for u in b for s in rules.analyze_unit(u["text"], u["voice"])]
            for s in cands:
                u = by_ref.get(s["ref"].strip())
                hit = locate_quote(s["quote"], u["text"]) if u else None
                if not hit:
                    # Model may cite the wrong unit; search the batch before rejecting.
                    for alt in b:
                        hit = locate_quote(s["quote"], alt["text"])
                        if hit:
                            u = alt
                            break
                if not hit:
                    rejected += 1
                    continue
                if provider.is_llm:
                    s["intent_level"] = rules.check_intent(s["intent_level"], hit[0])
                    ri = rules.intent_of(hit[0])
                    # Rules can only *raise* intent when explicit buying language is present in the quote itself.
                    if ri and scoring.INTENT_WEIGHTS[ri] > scoring.INTENT_WEIGHTS[s["intent_level"]] and ri != "existing_spending":
                        s["intent_level"] = ri
                found.append({**s, "quote": hit[0], "start": hit[1], "unit": u})
    except Exception as e:
        finish_run(rid, "failed", error=str(e))
        raise
    # One signal per (unit, quote) — avoid double counting.
    seen, uniq = set(), []
    for s in found:
        k = (s["unit"]["ref"], s["quote"].lower())
        if k not in seen:
            seen.add(k)
            uniq.append(s)
    finish_run(rid, output={"signals": len(uniq), "rejected_unverifiable_quotes": rejected},
               notes=f"{rejected} AI-cited quotes could not be found in the source and were discarded")
    return uniq, rejected


def store_signals(audience_id, analysis_id, sigs) -> list[dict]:
    with db.tx() as c:
        for s in sigs:
            u = s["unit"]
            # Single chokepoint: no path may store a strong intent the quote's own words don't support.
            s["intent_level"] = rules.guard_intent(s["intent_level"], s["quote"])
            locator = None
            if u["kind"] == "content":
                ts = timestamp_before(u["text"], s["start"])
                locator = ts or f"chars {u['offset'] + s['start']}–{u['offset'] + s['start'] + len(s['quote'])}"
            eid = db.new_id("ev")
            db.insert(c, "evidence", {"id": eid, "audience_id": audience_id, "source_id": u["source_id"],
                                      "content_item_id": u["content_item_id"], "comment_id": u["comment_id"],
                                      "quote": s["quote"], "locator": locator, "verified": 1, "created_at": db.now()})
            sid = db.new_id("sig")
            db.insert(c, "signals", {"id": sid, "audience_id": audience_id, "analysis_id": analysis_id,
                                     "evidence_id": eid, "signal_type": s["signal_type"],
                                     "intent_level": s["intent_level"], "summary": s["summary"][:300],
                                     "author_ref": u["author_ref"], "created_at": db.now()})
            s["id"], s["evidence_id"] = sid, eid
    return sigs


def stage_cluster(provider, audience, sigs, analysis_id):
    if not sigs:
        return []
    if provider.is_llm:
        listing = "\n".join(f"{i}. [{s['signal_type']}] {s['summary']}" for i, s in enumerate(sigs[:250]))
        rid = start_run(audience["id"], analysis_id, "3 · problem clustering", provider, len(listing))
        try:
            res = provider.complete_json(CLUSTER_SYS, f"<source_material>\n{listing}\n</source_material>",
                                         schemas.ClusterResult, max_tokens=3000)
            themes = [t.model_dump() for t in res.themes]
        except Exception as e:
            finish_run(rid, "failed", error=str(e))
            log.warning("AI clustering failed, using keyword grouping: %s", e)
            themes = rules.cluster_signals(sigs)
        else:
            assigned, clean = set(), []
            for t in themes:
                ids = [i for i in t["signal_ids"] if 0 <= i < len(sigs) and i not in assigned]
                assigned.update(ids)
                if ids:
                    clean.append({**t, "signal_ids": ids})
            # A theme holding most signals is a bucket, not a problem: ask the model to split it once.
            big = [t for t in clean if len(t["signal_ids"]) > max(8, 0.4 * len(sigs))]
            for t in big:
                sub = t["signal_ids"]
                listing2 = "\n".join(f"{j}. [{sigs[i]['signal_type']}] {sigs[i]['summary']}" for j, i in enumerate(sub))
                try:
                    res2 = provider.complete_json(CLUSTER_SYS + " These signals were grouped too broadly; split them "
                                                  "into 3-6 specific problems.",
                                                  f"<source_material>\n{listing2}\n</source_material>",
                                                  schemas.ClusterResult, max_tokens=2500)
                except Exception as e:
                    log.warning("split pass failed: %s", e)
                    continue
                parts, used = [], set()
                for t2 in res2.themes:
                    ids = [sub[j] for j in t2.signal_ids if 0 <= j < len(sub) and sub[j] not in used]
                    used.update(ids)
                    if ids:
                        parts.append({"label": t2.label, "description": t2.description, "signal_ids": ids})
                left = [i for i in sub if i not in used]
                if len(parts) >= 2:
                    if left:
                        parts[0]["signal_ids"] += left
                    clean.remove(t)
                    clean.extend(parts)
            rest = [i for i in range(len(sigs)) if i not in assigned]
            if rest:
                clean.append({"label": "Other signals", "description": "Signals that did not fit a theme.", "signal_ids": rest})
            themes = clean
            finish_run(rid, output=themes)
    else:
        themes = rules.cluster_signals(sigs)
    return themes


def store_clusters(audience_id, analysis_id, sigs, themes) -> list[dict]:
    out = []
    with db.tx() as c:
        for t in themes:
            members = [sigs[i] for i in t["signal_ids"]]
            st = scoring.cluster_stats([{"intent_level": m["intent_level"], "author_ref": m["unit"]["author_ref"] or
                                         (None if m["unit"]["kind"] == "comment" else "creator:" + m["unit"]["source_id"]),
                                         "source_id": m["unit"]["source_id"], "platform": m["unit"]["platform"],
                                         "date": m["unit"]["date"], "voice": m["unit"]["voice"]} for m in members])
            cid = db.new_id("cl")
            db.insert(c, "clusters", {"id": cid, "audience_id": audience_id, "analysis_id": analysis_id,
                                      "label": t["label"][:120], "description": t["description"][:500],
                                      "signal_count": st["signal_count"], "unique_authors": st["unique_authors"],
                                      "source_count": st["source_count"], "platform_count": st["platform_count"],
                                      "median_age_days": st["median_age_days"], "intent_score": st["intent_score"],
                                      "evidence_quality": st["evidence_quality"],
                                      "intent_breakdown_json": st["intent_breakdown"], "created_at": db.now()})
            for m in members:
                c.execute("UPDATE signals SET cluster_id=? WHERE id=?", (cid, m["id"]))
            out.append({"id": cid, **t, **st, "members": members})
    out.sort(key=lambda x: (-x["intent_score"] * x["unique_authors"], -x["signal_count"]))
    return out


def stage_opportunities(provider, audience, profile, clusters, analysis_id, audience_size):
    top = [c for c in clusters if c["label"] != "Other signals"][:8] or clusters[:8]
    ev_index, lines, ev_weight = [], [], {}
    for ti, cl in enumerate(top, 1):
        lines.append(f"T{ti}. {cl['label']} — {cl['description']} | distinct voices: {cl['unique_authors']}, "
                     f"sources: {cl['source_count']}, intent score (0-5): {cl['intent_score']}, "
                     f"evidence quality: {cl['evidence_quality']}, intents: {json.dumps(cl['intent_breakdown'])}")
        ranked = sorted(cl["members"], key=lambda m: -scoring.INTENT_WEIGHTS[m["intent_level"]])[:5]
        for m in ranked:
            ev_index.append((m["evidence_id"], cl["id"]))
            ev_weight[m["evidence_id"]] = scoring.INTENT_WEIGHTS[m["intent_level"]]
            lines.append(f"   E{len(ev_index)} [{m['intent_level']}; {m['unit']['voice']}] \"{m['quote'][:240]}\"")
    comps = db.all_("SELECT name, price_text, provenance FROM competitors WHERE audience_id=? AND provenance != 'ai_suggestion'",
                    (audience["id"],))
    comp_txt = "\n".join(f"- {x['name']}: {x['price_text'] or 'price unknown'} ({x['provenance']})" for x in comps) \
        or "None researched yet."
    user = (f"Creator/business: {audience['org_name']}\nProfile: {profile.get('summary') if profile else 'n/a'}\n"
            f"Known audience size (followers/subscribers entered or retrieved): {audience_size or 'unknown'}\n\n"
            f"<source_material>\nPROBLEM THEMES AND EVIDENCE\n" + "\n".join(lines) +
            f"\n\nSTORED COMPETITOR RESEARCH\n{comp_txt}\n</source_material>\n\nPropose 3-5 opportunities.")
    rid = start_run(audience["id"], analysis_id, "6-7 · opportunities & scoring", provider, len(user))
    try:
        res = provider.complete_json(OPP_SYS, user, schemas.OpportunityResult, max_tokens=6000)
    except Exception as e:
        finish_run(rid, "failed", error=str(e))
        raise
    total_voices = sum(c["unique_authors"] for c in clusters) or 1
    created, dropped = [], 0
    with db.tx() as c:
        for o in res.opportunities[:5]:
            # Reference numbers belong in theme_ids/evidence_ids only; strip any that leaked into prose.
            o = type(o).model_validate(rules.strip_refs_deep(o.model_dump()))
            cited = [ev_index[i - 1] for i in dict.fromkeys(o.evidence_ids) if 1 <= i <= len(ev_index)]
            th_named = {top[i - 1]["id"] for i in o.theme_ids if 1 <= i <= len(top)}
            if th_named:  # keep only evidence that belongs to the problems this idea claims to solve
                cited = [x for x in cited if x[1] in th_named] or cited
            cited = sorted(cited, key=lambda x: -ev_weight.get(x[0], 0))[:8]
            ev = [x[0] for x in cited]
            th = sorted(th_named | {x[1] for x in cited})
            if not ev:
                dropped += 1
                continue  # no traceable evidence => not shown as a recommendation
            linked = [cl for cl in clusters if cl["id"] in th]
            scores = scoring.data_scores(linked, total_voices)
            ms = o.scores.model_dump()
            rationale = ms.pop("rationale")
            scores.update(ms)
            missing = list(o.unknown)
            if not any(cl["strong_voices"] for cl in linked):
                missing.insert(0, "No direct spending or buying language in the linked evidence — demand is unproven.")
            oid = db.new_id("op")
            db.insert(c, "opportunities", {
                "id": oid, "audience_id": audience["id"], "analysis_id": analysis_id, "ai_run_id": rid,
                "name": o.name[:200], "buyer": o.buyer, "problem": o.problem, "product_type": o.product_type,
                "format_rationale": o.format_rationale, "price": round(o.price, 2), "price_model": o.price_model,
                "price_rationale": o.price_rationale, "production": o.production,
                "production_cost": round(o.production_cost_estimate, 2),
                "fulfillment_cost_per_unit": round(o.fulfillment_cost_per_unit, 2),
                "delivery_difficulty": o.delivery_difficulty, "recurring": o.recurring,
                "distribution": o.distribution, "validation_plan": o.validation_experiment,
                "competition_notes": o.alternatives, "risks_json": o.risks,
                "confidence_json": {"supported": o.supported, "assumed": o.assumed, "unknown": o.unknown,
                                    "score_rationale": rationale},
                "missing_evidence_json": missing, "scores_json": scores, "total_score": scoring.total(scores),
                "cluster_ids_json": th, "scenario_json": {"reach": audience_size, "exposure_pct": None,
                                                          "rates_pct": [0.1, 0.5, 1.0], "payment_fee_pct": 3.0,
                                                          "payment_fee_fixed": 0.30},
                "status": "proposed", "created_at": db.now(), "updated_at": db.now()})
            for e in ev:
                c.execute("INSERT OR IGNORE INTO opportunity_evidence VALUES (?,?)", (oid, e))
            created.append(oid)
    finish_run(rid, output=res.model_dump(), notes=f"{dropped} ideas dropped for lacking traceable evidence")
    gaps = [{"gap": rules.strip_refs(g.gap), "cluster_ids": [top[i - 1]["id"] for i in g.theme_ids if 1 <= i <= len(top)]}
            for g in res.market_gaps]
    return created, gaps, dropped


# ---------- job ----------

def audience_context(audience_id):
    a = db.one("SELECT a.*, o.name AS org_name FROM audiences a JOIN organizations o ON o.id=a.organization_id "
               "WHERE a.id=?", (audience_id,))
    size = db.scalar("SELECT SUM(follower_count) FROM channels WHERE audience_id=?", (audience_id,))
    return a, size


def compute_unknowns(meta, audience_size, sigs, provider):
    u = []
    if meta["comments_total"] == 0:
        u.append("No audience comments or messages were imported — problems are inferred from the creator's own content, "
                 "which is weaker evidence than what the audience says.")
    if meta["comments_total"] > meta["comments_analyzed"]:
        u.append(f"Only the top {meta['comments_analyzed']} of {meta['comments_total']} comments (by likes/recency) were analyzed.")
    if not audience_size:
        u.append("Audience size unknown — add follower/subscriber counts to channels to size scenarios.")
    if not any(s["intent_level"] in ("verified_purchase", "existing_spending") for s in sigs):
        u.append("No evidence of past spending was found. Willingness to pay must be tested.")
    if not db.scalar("SELECT COUNT(*) FROM engagement_metrics em JOIN content_items ci ON ci.id=em.content_item_id "
                     "WHERE ci.audience_id=?", (meta.get("audience_id"),)):
        u.append("No engagement metrics imported — content performance cannot be compared.")
    u.append("Demographics are not measured by AudienceOS; they are only listed where the material states them.")
    if not provider.is_llm:
        u.append("Analyzed by the rules engine (no AI model): grouping is keyword-based and product ideas were not generated.")
    return u


@jobs.handler("analyze_audience")
def analyze_audience(job, progress):
    audience_id = job["audience_id"]
    p = jobs.payload(job)
    provider = providers.require(providers.get_provider(p.get("provider")))
    if provider.external and not settings_store.get("allow_external_ai"):
        raise providers.ProviderUnavailable("External AI is disabled in Settings.")
    audience, size = audience_context(audience_id)
    progress(0.03, "Collecting stored material")
    units, meta = build_units(audience_id)
    meta["audience_id"] = audience_id
    if not units:
        raise AnalysisError("There is no readable material yet. Add content or comments first.")
    analysis_id = db.new_id("an")
    with db.tx() as c:
        # A run interrupted by a quit/crash leaves a 'running' analysis behind; close it out honestly.
        c.execute("UPDATE ai_runs SET status='failed', finished_at=?, error=? WHERE status='running' AND analysis_id IN "
                  "(SELECT id FROM analyses WHERE audience_id=? AND status='running')",
                  (db.now(), "Interrupted (app closed)", audience_id))
        c.execute("UPDATE analyses SET status='failed', finished_at=?, unknowns_json=? WHERE audience_id=? AND status='running'",
                  (db.now(), json.dumps(["Interrupted (app closed) — superseded by a new run"]), audience_id))
        db.insert(c, "analyses", {"id": analysis_id, "audience_id": audience_id, "provider": provider.name,
                                  "model": provider.model or None, "external": int(provider.external),
                                  "status": "running", "started_at": db.now()})
        c.execute("UPDATE jobs SET ref_id=? WHERE id=?", (analysis_id, job["id"]))
    try:
        profile = None
        if provider.is_llm:
            progress(0.06, "Stage 1 · Understanding the content")
            profile = stage_profile(provider, audience, units, meta, analysis_id)
        progress(0.15, "Stage 2 · Extracting problems and buying signals")
        sigs, rejected = stage_extract(provider, audience, units, analysis_id, progress)
        sigs = store_signals(audience_id, analysis_id, sigs)
        progress(0.68, "Stage 3 · Grouping problems")
        themes = stage_cluster(provider, audience, sigs, analysis_id)
        progress(0.75, "Stage 4 · Measuring commercial intent")
        clusters = store_clusters(audience_id, analysis_id, sigs, themes)
        opp_ids, gaps, dropped = [], [], 0
        if provider.is_llm and clusters:
            progress(0.8, "Stages 6–7 · Generating and scoring opportunities")
            opp_ids, gaps, dropped = stage_opportunities(provider, audience, profile, clusters, analysis_id, size)
        if profile is not None:
            profile["market_gaps"] = gaps
        stats = {k: v for k, v in meta.items() if k not in ("frames", "items", "audience_id")}
        stats.update({"units": len(units), "signals": len(sigs), "rejected_quotes": rejected,
                      "clusters": len(clusters), "opportunities": len(opp_ids), "opportunities_dropped": dropped})
        with db.tx() as c:
            db.update(c, "analyses", analysis_id, {
                "status": "done", "finished_at": db.now(), "profile_json": json.dumps(profile) if profile else None,
                "stats_json": stats, "unknowns_json": compute_unknowns(meta, size, sigs, provider)})
            c.execute("UPDATE audiences SET last_analyzed_at=?, updated_at=? WHERE id=?", (db.now(), db.now(), audience_id))
            db.log_activity(c, audience_id, "analysis",
                            f"Analysis finished with {provider.label}: {len(sigs)} signals, {len(clusters)} problems, "
                            f"{len(opp_ids)} opportunities")
    except Exception as e:
        with db.tx() as c:
            db.update(c, "analyses", analysis_id, {"status": "failed", "finished_at": db.now(),
                                                   "unknowns_json": [f"Analysis failed: {str(e)[:300]}"]})
        raise
    return {"message": f"{len(sigs)} signals · {len(clusters)} problems · {len(opp_ids)} opportunities"}
