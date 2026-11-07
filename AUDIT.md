# Strategy audit

**Strategy:** a done-for-you AI creator-monetization agency. AudienceOS finds what a creator's audience will pay for, the agency builds and launches the product through the creator's own checkout, and the profit is split **70% creator / 30% agency**. The first goal is **3 real creator pilots** that prove the economics before any self-service product.

Status key: ✅ ready for pilots · 🟡 works with a stated limit · ⏸ deferred on purpose.

## Workflow step by step

| # | Step | Status | What exists | Limit / note |
|---|---|---|---|---|
| 1 | **Discovery** (sign a creator, gather material) | ✅ | Creators with a pipeline stage and contact. File, link and paste import for every platform, with an honest obtained/missing report per source. | Instagram, Facebook and LinkedIn need the creator's data export. Reddit is often blocked by robots.txt. |
| 2 | **Audience analysis** | 🟡 | A local 7-stage pipeline with verified quotes, a strong-intent guard, intent counted per voice, an evidence drawer and an audience profile. | 7B output can be generic, and a demo-sized run takes about 12 minutes. An optional external model, with consent, improves quality. |
| 3 | **Product opportunities** | 🟡 | 3–5 evidence-cited ideas per run, scored as a relative index, with scenario economics. | Ideas can overlap or repeat phrasing on the 7B model. A human picks which to test. |
| 4 | **Demand validation** | ✅ | Experiments with up-front criteria, CSV and manual results, order import, intervals, a recommendation and a recorded decision (overrides labeled). | Purchase rates in scenarios are your assumptions, never benchmarks. |
| 5 | **Product generation** | ✅ | 13 asset types drafted from the audience's words, a claim review, approval, and export to MD/HTML/DOCX. Landing pages carry a strict CSP. | Drafts need human editing for voice. Nothing publishes itself. |
| 6 | **External checkout** | ✅ | The product stores the storefront and an https checkout link. Landing pages link to it. | No payment processing, by design (decision 10). |
| 7 | **Launch** | ✅ | A 5-check gate, all assets approved, a named approver, then "mark launched". Material edits send the product back to draft, with a clear reason. | "Launched" is your attestation that you published it. AudienceOS doesn't publish. |
| 8 | **Sales attribution** | ✅ | Order CSV import with a channel taken from `utm_source`/`channel`, duplicate protection, and a by-channel table. | Only as good as the tracking links used. Read-only order sync for Stripe Payment Links, Gumroad, Shopify and Lemon Squeezy (1.3–1.4); untested against real accounts until you add keys. |
| 9 | **70/30 revenue share** | ✅ | Per-creator deals (configurable %, contribution or net-sales base), shared vs agency-only costs, payouts, balance owed, and a statement plus CSV. | **You must confirm the contract's base** (see `NEXT_STEPS.md` item 1). Losses are never charged to the creator. |
| 10 | **Optimization** | ✅ | You can compare experiments, see sales by channel, get rules-based next-test suggestions (1.3) and reanalyze when new material arrives. | Suggestions are rules, not a model; a human picks the next test. |

## What changed in this pass (2026-11-05, session 2)

These changes matter for running the 3 pilots.

1. **Revenue decisions can't rest on mislabeled intent.** Every stored signal now passes one intent guard. The earlier mislabels (e.g. "Living at 7000 ft…" stored as *existing spending*) came from a run made before the guard existed. A regression test now covers those exact quotes, and every storage path.
2. **Readable outputs for creators.** Internal reference numbers (`T1, T3`, `E12`) are stripped from opportunity text, gaps and hypotheses. The auto-written hypothesis now reads as a sentence. Landing-page buttons are short labels.
3. **Trustworthy money screens.** Products that went back to draft after a price, name or link change say so everywhere (product page, product list, statement, dashboard), and their sales stay counted. Date fields default to the *local* date (they were writing tomorrow's date in the evening). The statement CSV shows money to the cent and whole order counts.
4. **Always a next step.** The dashboard now guides you from analysis, through review, experiment decision, product creation, approval and launch, to first orders. The Sources tab tells you when everything is ready to analyze.
5. **Clarity fixes.** Imported orders vs daily rows disagreements are shown as a warning. Success criteria show their units (`≥ 2%`). Fee hints separate payment fees from fulfillment. Duplicate "missing evidence" is removed. Settings no longer offers text-only models as vision models. "Excl. demo" labels are on dashboard totals.
6. **Asset drafts are sturdier and safer.** A draft is no longer lost when the local model omits its title. Links, emails and phone numbers in drafts are flagged, because the 7B model invented a website for the demo creator.
7. **Operations.** `stop.sh` now reliably stops the bundled AI engine. An interrupted analysis also closes its AI-call log rows. Backups are named in local time. Library results deep-link to their source.

## Readiness for the 3 pilots

- **Ready:** the full loop runs end to end on a fresh database (see `TESTING.md`), on this Mac, with no paid services.
- **Before pilot 1** (only you can do these; details in `NEXT_STEPS.md`): confirm the revenue-share base in the contract, choose each creator's checkout, collect the creator's data exports and get their consent, and decide whether an external model is worth its cost and consent step for higher-quality analysis.
- **Watch during pilots:** whether the 7B model's opportunities are specific enough for real creators. If not, switch that creator to an external provider (with consent) rather than tuning prompts further.

## Deferred, on purpose

As of 1.4.0, all the post-pilot money items, every checkout sync and the local analysis items are built (see `CHANGELOG.md`). Still open, and why:

- YouTube OAuth transcripts and the Meta/TikTok business APIs need developer apps that you register and that the platforms review.
- Self-service accounts and hosting are deliberately held until the 3 pilots prove the economics.
