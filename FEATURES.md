# Features

Status as of 2026-11-05 (v1.1.0). **Working** means it was exercised in the real app on port 8760 and/or by the automated suite (see `TESTING.md`). **Limited** means it works, with a stated constraint. **Not built** means it is deliberately absent.

## Working

**App & platform**
- A local server on `127.0.0.1:8760`, opened in a Chrome app window. It ships with a Desktop launcher, `start.sh`, `stop.sh` and `AudienceOS.command`.
- Light, dark and auto themes. All 24 routes render with no console errors.
- Background jobs (imports, analyses, asset drafts, model downloads) are persisted in SQLite. After a quit or crash they resume on the next launch, and an interrupted analysis is closed out with a reason.
- Deleting an audience or the demo removes its files as well as its rows.
- One-click database backup, a per-audience JSON export, and library search across sources, content, transcripts, comments, evidence, opportunities, competitors, experiments, assets, reports and analysis history. Library results link straight to the source (and content item) they came from.

**Ingestion**
- Files: text, Markdown, HTML, PDF (text layer), DOCX, CSV and JSON (comment exports, analytics tables), audio and video (transcribed locally with Whisper, with timestamps kept), and images.
- URLs: YouTube (oEmbed, plus the Data API with a key), TikTok and X (oEmbed), RSS/Atom, Substack, Apple Podcasts (optional local episode transcription), and generic web pages. Fetching is SSRF-safe and respects robots.txt.
- Pasted text, as content or as comments.
- Comment deduplication, spam flags and hashed author IDs. Every source records what was obtained and what is missing.

**Intelligence**
- A 7-stage pipeline on the local model: classification, extraction, clustering, intent, competitors, opportunities and scoring.
- Every quote the model cites is verified against the stored source, and unverifiable quotes are discarded and counted.
- **Strong-intent guard at a single chokepoint:** no signal is stored with a spending, purchase, buying-question or paid-request label unless the quote's own words support it. When explicit buying language is present, its label wins (e.g. "Where can I buy…" is a buying question).
- Intent is counted per distinct voice, and the evidence drawer shows the quote, its interpretation and the original comment or timestamp.
- Opportunities must cite evidence from their own themes or they're dropped. Theme and evidence reference numbers (`T3`, `E12`) are kept out of all stored prose, and out of experiment hypotheses.
- A configurable scoring rubric gives a 0–100 relative index (never a probability), with editable per-opportunity scores.
- Scenario economics: price, costs, fees, reach, exposure and purchase-rate sensitivity, with break-even and the formulas shown.

**Validation**
- Experiments carry success criteria set up front, results entered by hand or imported as a daily-results CSV, and order CSV imports (idempotent).
- Metrics use separate denominators and show a Wilson 95% interval. The app gives a go / revise / stop recommendation; your recorded decision is shown next to it, and overrides are labeled.
- When imported orders and daily rows disagree on purchases, a visible warning says which source was used.

**Assets**
- 13 draft types: offer, landing page, newsletter, social, sample, description, outline, checklist, workbook, guide, email campaign, spec and calculator.
- A rule-based plus AI claim review, approval, editing (which resets approval), a strict-CSP preview, and export to `.md`, `.html` and `.docx`.
- Landing pages use the product's checkout link when the experiment has none. A long model-written call to action becomes a lead paragraph above a short button.

**Agency operations**
- Creators, each with a pipeline stage, contact details and a revenue-share deal: configurable %, on either contribution or net sales after fees.
- Products have a launch gate: 5 checks, an https checkout link, all assets approved and a named approver. Changing the price, name, pricing model or checkout link sends the product **back to draft**. The UI says exactly what changed and when, and that sales history is kept. The dashboard asks you to re-approve.
- Order CSV import with channel attribution and duplicate protection, plus costs (shared or agency-only), payouts, creator statements with a period filter, and a statement CSV (money to the cent).
- The dashboard always has a next step: import, analyze, review proposed opportunities, decide on experiments with results, create the product for a validated idea, re-approve, mark launched, or import first orders.

## Limited

- **Local 7B model quality:** with `qwen2.5:7b` the analysis is usable but generic in places. In the demo run all three opportunities got the same buyer sentence, and two got the same problem sentence. Output varies between runs even at temperature 0 because batching affects context. An optional Anthropic or OpenAI key gives higher quality, with per-run consent and paid usage.
- **Speed:** a demo-sized analysis (65 comments, 6 content items) took about 12 minutes on this Mac. An asset draft took about 35 seconds.
- **Reddit:** often blocked by robots.txt for automated fetches. Paste threads, or import them, instead.
- **Instagram, Facebook, LinkedIn:** no permitted public access. They work through the creator's data exports (instructions are in the app and in `DATA_SOURCES.md`).
- **YouTube:** comments and statistics need a free Data API key. Transcripts of videos you don't own can't be downloaded, so paste them or upload your own file.
- **Competitor search:** automatic only with a Brave Search API key. Without one, you enter competitor URLs and visible prices are extracted.
- **Vision:** video frames are stored, but only described if you install a vision-capable model (e.g. `qwen2.5vl:7b`). Settings lists only vision-capable models for this.
- **Large comment sets:** above 600 comments, the top ones by likes and recency are analyzed, and the analysis states this.

## Not built (deliberately)

- Payments of any kind. Products sell through the creator's own checkout (Stripe Payment Link, Gumroad, Shopify…) and orders are imported as CSV.
- Direct checkout or API sync (Stripe/Gumroad/Shopify), Meta or TikTok business APIs.
- OCR for scanned PDFs and images.
- Auto-posting, messaging or emailing anyone.
- Accounts, auth, multi-tenant hosting, a creator portal, and billing for the platform itself.
- Loss carry-forward and minimum guarantees in deals (losses are never charged to the creator).

See `ROADMAP.md` for the order these would come in.
