# Progress log

Times are local (EST) unless marked UTC.

## 2026-11-05 — session 1 (original build)

- Built the backend: FastAPI, SQLite migrations 001/002, persisted job worker, ingestion, 7-stage pipeline, validation, assets, reports and agency operations.
- Set up the project-local Ollama runtime (`qwen2.5:7b`, `qwen2.5:3b`), faster-whisper `base` and bundled FFmpeg.
- Built the frontend: React/TS/Vite, 21 routes, verified headlessly against a scratch server on port 8761.
- Added the launchers (`start.sh`, `stop.sh`, `AudienceOS.command`, `~/Desktop/AudienceOS.app`) and docs (ARCHITECTURE, DECISIONS, DATA_SOURCES, ROADMAP, NEXT_STEPS, CHANGELOG).
- 29 tests passing. Paused with 4 open backend bugs and the real-app verification still to do.

## 2026-11-05 — session 2 (this pass)

| Time | Step |
|---|---|
| 19:20 | Read the continuation prompt and docs. Investigated bug 2 in the scratch DB: the mislabeled run `an_50a6d…` (21:17 UTC) is the earliest one. Later runs on the same quotes stored low intents, so it predates the guard. Added a storage-time guard anyway. |
| 19:22 | Fixed bugs 1–4 and added regression tests (29 → 45). Rebuilt the frontend (type-check clean). Launched the real app with `start.sh` on a fresh `~/AudienceOS/data`. |
| 19:24 | Real app, headless Chrome: Dashboard → Load demo project → 4 sources ingested and transcribed → Run analysis. |
| 19:24–19:36 | Local analysis: 33 signals, 5 problems, 3 opportunities, about 12 minutes. Verified every strong-intent label has supporting words. Tightened the guard so explicit buying language decides the label (45 → 48 tests). |
| 19:38 | Drove intelligence, the evidence drawer, signals, opportunities, the scenario, approval, the experiment, both CSV imports and the decision. 0 console errors. Polish pass 1 (next actions, header wrap, metrics layout, duplicate missing-evidence, fee hint). |
| 19:41 | Drove an asset draft (landing page, 35 s), approval, MD/HTML/DOCX export, product, launch gate, launch, order import, cost, deal, payout and statement CSV. Found the UTC date bug and fixed it. Pass 2 (landing CTA, checkout fallback, product sidebar, placeholders). |
| 19:42 | Generated reports in all 5 formats, library search with deep link, backup. Changed the price on the launched product: "Back to draft" shown everywhere, sales kept. |
| 19:43–19:47 | Full 24-route light/dark sweeps (3 runs, 0 errors, no horizontal scroll). Passes 2–3 (hypothesis wording, criteria units, vision-model list, intelligence picker, dashboard layout, "excl. demo", nowrap dates, pluralization). |
| 19:48 | Pass 4: a non-demo first-time path (new creator → paste text → "1 source ready → Run analysis"; empty states). Nothing material found. Removed the UI test creator. |
| 19:49–19:57 | Recovery test: started a reanalysis, quit with `stop.sh` mid-stage-2, relaunched from `~/Desktop/AudienceOS.app`. The same job resumed (attempt 2), the interrupted run was closed out, and the new run finished (33 signals · 5 problems · 3 opportunities). All products, sales, payouts and experiments persisted. Found and fixed `stop.sh` not stopping the engine, and stale AI-call rows. |
| 19:58–20:05 | Docs (README, FEATURES, AUDIT, TESTING, this log, CHANGELOG). Key-leak test (52 tests). Version 1.1.0. |
| 20:00–20:08 | Fresh-DB end-to-end run on port 8761: analysis OK, then the **asset step failed** (the model omitted `title`; it also invented a website). Fixed both and added tests (54). |
| 20:10–20:20 | Repeated the fresh-DB run from an empty database: all steps pass (2 script-side checks corrected and verified). |
| 20:21 | `stop.sh` stops server and engine; relaunched from `~/Desktop/AudienceOS.app`; localhost-only listeners; 54 tests pass. |
| 20:28–20:33 | Finish-up: removed the Pydantic warning; report button disabled before analysis; fixed audience/demo deletion leaving media and report files. Backed up the verified state, then reset `data/` to an empty DB so the README's first workflow starts from "Load demo project". 56 tests, empty-state check with 0 errors. Done. |
