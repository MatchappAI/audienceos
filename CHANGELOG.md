# Changelog

## 1.2.0 — 2026-11-06 (new icon, end-to-end run, fixes)

**New icon.** A blue rounded square with a white creator dot sending out arcs of audience dots. One gold dot marks the signal that pays. It's on the Desktop app (`AudienceOS.icns`; the stock applet `Assets.car` was removed so macOS uses it), and a simplified version is the sidebar mark and browser-tab icon. Sources and the generator script are in `docs/brand/`.

**Fixed (found by driving the whole loop in the UI on a fresh copy)**
- **The landing page showed the wrong price.** Drafts render at the opportunity's test price, so the button said "Get it — $50" while the product sold at $39. The page now uses the product's price (the same product its checkout link already came from). Launch approval also warns when an asset's text quotes a different amount.
- **A flagged draft could be approved in one click.** When the claim review flags something, Approve now stays disabled until you tick "I fixed or checked the flagged claim".
- **Opportunity page made duplicate experiments.** Once an experiment or product exists, the header shows *Open experiment* / *Open product*. *New experiment* is still there if you want a second test.
- **Criteria without thresholds were blamed on "missing data".** Go/no-go now says "Set a threshold for each success criterion", and the row shows a *set a threshold* badge.
- **The dashboard asked you to start an analysis that was already running.** It now says the analysis is running.
- **A mistyped audience tab URL showed a blank page.** It now opens the overview.
- **Audience Intelligence showed "Analysis in progress" twice.** It now shows it once.

## 1.1.0 — 2026-11-05 (session 2: bugs, live verification, polish)

**Bugs fixed**
- **Theme/evidence IDs in prose:** the opportunity prompt now forbids `T#`/`E#` in text fields. Any that slip through are stripped (including lists like `(T1, T3)` and `[E1-E3]`) from every free-text field and gap before storing, and from auto-written experiment hypotheses.
- **`existing_spending` mislabels:** the reported mislabels came from analysis `an_50a6d9292370414f` (21:17 UTC), the earliest run, made before the lexical guard. Later runs on the same quotes stored `engagement`/`curiosity`. Every stored signal now passes `rules.guard_intent` in `store_signals` (one chokepoint for every path). When explicit buying language is present it decides the label, e.g. "Where can I buy…" becomes `buying_question`. Regression tests cover the exact quotes.
- **Product "Draft" despite sales:** a material edit (name, price, pricing model or checkout link) after approval or launch now records what changed, when, and who approved it before. Products expose `reapproval`. The UI shows "Back to draft — price changed after launch; re-approve to relaunch. Sales history is kept." on the product page, product list, statement and dashboard.
- **Library content results lack `source_id`:** content, comment and evidence results now carry `source_id`. The Library links straight to the source (`?source=…&item=…` opens the drawer on that item).
- Date inputs defaulted to the **UTC** date, so evening entries were dated tomorrow. They now use the local date.
- `stop.sh` didn't stop the bundled AI engine when it had been started with a relative path. It now matches on the executable path, and never touches a system Ollama.
- An interrupted analysis left its AI-call log rows "running". They are now closed out with it.
- **Asset drafts lost when the model omitted the title.** Found in the fresh-DB run: `qwen2.5:7b` returned an *offer* without `title` twice, so the job failed. The title is now optional and falls back to "<Kind> — <product>".
- **Deleting an audience (or the demo) left files behind** in `data/media` and `data/reports`. They are now removed with it.
- The Pydantic warning about the `copy` field is gone (the field is renamed internally; the API still accepts `copy`).
- **Invented contact details:** the same draft contained a made-up website for the demo creator. The claim review now flags every link, email and phone number in a draft for replacement with the creator's real one.

**Clarity & polish (4 passes)**
- The dashboard always has a next step: review proposed opportunities, decide on experiments with results, create the product for a validated idea, re-approve, mark launched, import first orders.
- The Sources tab says when everything is ready ("N sources ready → Run analysis") or still processing.
- The analysis empty state no longer offers "Go to analysis" while running or when already there, and says the job survives a restart.
- Experiments: an orders-vs-daily-rows purchase mismatch is a visible warning. The metrics table is readable in the sidebar. Criteria show units (`≥ 2%`). Overriding the recommendation is labeled. Auto-hypotheses read as sentences.
- Opportunities: header actions wrap cleanly. The fee hint separates payment fees from fulfillment. "Missing evidence" no longer repeats "Unknown".
- Products: the storefront form fits the sidebar, and input placeholders are no longer truncated.
- Landing pages: a sentence-length call to action becomes a lead paragraph above a short button. The product's checkout link is used when the experiment has none.
- Statement CSV: money to the cent, whole order counts. Backups are named in local time.
- "Generate report" is disabled until an analysis exists, and the empty state links to the analysis.
- Settings only offers vision-capable models for frame analysis. "Excl. demo" labels are on dashboard totals. Pluralization fixes. The analysis duration estimate now matches measured runs.

**Docs:** README, FEATURES, TESTING, AUDIT and PROGRESS_LOG added.

**Tests:** 29 → 56.

**Data:** `~/AudienceOS/data` was reset to a clean, empty database after verification. A backup of the verified demo state is in `data/backups/audienceos_2026-11-05_202945.db`.

## 1.0.0 — 2026-11-05

**Foundation**
- Local server on 127.0.0.1:8760; SQLite with migrations `001_init` and `002_agency`.
- Persisted background jobs that resume after a quit or crash.
- Project-local Ollama runtime with `qwen2.5:7b` and `qwen2.5:3b`; Whisper `base`; bundled FFmpeg.

**Ingestion**
- Files: text, Markdown, HTML, PDF, DOCX, CSV and JSON (comments, analytics or plain tables), audio, video and images.
- URLs: YouTube (oEmbed, plus the YouTube Data API with a key), TikTok and X (oEmbed), Reddit (public JSON, respects robots.txt), RSS/Atom, Substack, Apple Podcasts (lookup → RSS, optional local episode transcription), and generic web pages.
- Instagram, Facebook and LinkedIn are honestly reported as unsupported, with export instructions.
- SSRF protection, file sniffing, size caps.
- Comment deduplication, spam flags and hashed authors.

**Intelligence**
- A 7-stage pipeline with validated schemas.
- Every quote is verified against its source, and evidence links go back to the comment or the timestamp.
- Strong-intent guard; intent counted per distinct voice; a split pass for over-broad clusters.
- Opportunities must cite evidence (up to 8 quotes from their own themes).
- Configurable scoring rubric; scenarios with formulas.

**Validation**
- Experiments with success criteria, manual and CSV results, and order imports (idempotent).
- Separate-denominator metrics, a 95% interval on conversion, and go/revise/stop recommendations plus a recorded decision.
- Asset generation (13 types) with rule-based and AI claim review, approval, preview under a strict CSP, and export to MD/HTML/DOCX.
- Safe calculator generation.

**Reports & library**
- Reports in HTML, PDF, JSON and CSV.
- Library search across everything; database backup; per-audience JSON export.

**Agency operations (pilot readiness)**
- Creators carry a pipeline stage, contact details and a deal (configurable revenue share and basis).
- Products have a launch gate: checklist, https checkout link, all assets approved, named approver. Changing price, name or link sends the product back for approval.
- Sales come from checkout CSV imports or manual entry, with channel attribution and duplicate protection.
- Costs are recorded as shared or agency-only. Payouts are tracked, and creator statements (with a period filter and CSV export) show the balance owed.
- The dashboard shows product sales and the total owed to creators.

**Fixes found in testing**
- PyAV decode error on video transcription → decode our own WAV.
- The 7B model mislabeled frustration as "spending" → lexical guard.
- Over-broad clusters → specific-theme prompt and an automatic split pass.
- Every opportunity citing all evidence → limited to its own themes.
- Pasted comments didn't report duplicates/spam.
- Timestamp lookup when a quote starts at a marker.
- Cent rounding on statements (half-up).
- Interrupted analyses left "running" → now resumed, with the stale run closed out.
- Non-deterministic local model output → seed 42, temperature 0.
