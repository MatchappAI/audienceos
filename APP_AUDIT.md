# App audit: feature inventory (2026-11-16, v1.5.0)

How this was checked: code read end to end (routers, services, ingest, AI, frontend pages); an independent second reviewer covered security, ingest and AI; 113 automated tests; headless Chrome driving the real UI on a **scratch copy** (port 8761, separate data folder, its own Ollama on 11435). The live app (port 8760, `~/AudienceOS/data`) was not running and was never touched.

Status: **Working** (real outcome verified through UI → API → DB → UI) · **Partial** (works with a stated limit) · **Mock-only** (tested against mocked external APIs) · **Not built**. No fake-success paths were found: every action either persists and re-renders from the database, or shows the server's error.

| # | Area / page | Features and controls | Status | Evidence |
|---|---|---|---|---|
| 1 | **Dashboard** `/` | Stats (excl. demo), next actions, recent activity, running jobs, Load demo, Add creator, empty state | Working | Route sweep; e2e load demo; next actions show "AI provider not ready" when the engine is down |
| 2 | **Audience Research** `/audiences` | List, Add creator form (`?new=1`), channels | Working | Sweep; API edge run (unicode creator name) |
| 3 | **Workspace** `/audiences/:id/:tab` | Overview (edit, channels, delete audience), Content & sources (upload/link/paste, reprocess, delete, transcript drawer), Audience problems (run analysis, problem rows, evidence drawer), Commercial signals, Opportunities, Experiments, Products, Reports; unknown tab → overview | Working | e2e journey; sweep of all tabs incl. `/bogus` |
| 4 | **Import** | Files (text, MD, HTML, PDF+OCR, DOCX, CSV, JSON, audio/video with local Whisper, images), URLs (permitted retrieval per platform, robots.txt), pasted text/comments; duplicate detection; per-source obtained/missing report | Working (UTF-16 CSV refused, O-01) | Demo ingest (4 sources ready in ~5 s); edge run: exe-as-csv refused, empty refused, traversal name sanitized, duplicate detected, unicode CSV, 2 MB paste, over-limit paste 422 |
| 5 | **Analysis pipeline** (local `qwen2.5:7b`) | 7 stages, quote verification, intent guard, distinct-voice counting, evidence drawer, resume after restart, one run at a time | Working (7B quality limits, see AUDIT.md) | Fresh run: **33 signals · 5 problems · 3 opportunities in 10 min 40 s**; restart mid-run resumed (attempt 2) |
| 6 | **Audience Intelligence** `/intelligence/:id` | Profile, unknowns, signals by strength | Working | Sweep, e2e |
| 7 | **Product Opportunities** `/opportunities/:id` | Score breakdown/weights, scenario recalculation, approve/reject/restore, competitors (manual add; auto-research needs Brave key), create experiment/product, assets panel | Working (auto-research blocked without key) | e2e |
| 8 | **Validation Lab** `/validation/:id` | Design + success criteria, manual result rows, CSV import (daily results or orders, idempotent), metrics with intervals, recommendation, Go/Revise/Stop with override label, compare | Working | e2e: 3 rows + 5 orders, re-import skipped 5, Go → validated |
| 9 | **Assets** | 13 kinds drafted by the local model, claim review (rules + AI), flagged-claim confirmation (UI + API), edit → re-approval, preview (strict CSP), export MD/HTML/DOCX | Working | e2e: landing page in 77 s, flag ticked, approved, exports 1.6/3.6/37 KB, CSP `default-src 'none'` |
| 10 | **Products & launch** `/products/:id` | Setup (material edits reset approval), 5-check gate + approver, launch, pause/resume, retire/reopen, sales (manual + CSV, duplicates skipped), costs (shared / agency-only), by-channel table, Next tests, checkout sync | Working; checkout sync **mock-only** | e2e; gate bypass fixed (A-01) |
| 11 | **Creators & Revenue** `/creators`, `/creators/:id` | Pipeline stage, deal terms (share %, basis, loss carry-forward, minimum guarantee, term), statement by period, CSV, PDF, payouts (record/delete), payout file (Wise CSV), creator portal (view/download) | Working | e2e: base $136.85 → creator **$95.80** (half-up of 95.795), agency $41.05, $10 payout → owed $85.80, CSV/PDF/portal match |
| 12 | **Reports** | HTML, PDF, JSON, opportunities CSV, signals CSV | Working | e2e: all 5 files 200 |
| 13 | **Research Library** `/library` | Search across sources, content, comments, evidence, opportunities, competitors, experiments, reports, assets; deep links | Working | e2e search "starter" |
| 14 | **Settings** `/settings` | Provider choice, external AI opt-in, web retrieval toggles, Keychain keys (never echoed), model downloads, OCR status, rubric weights, theme | Working; external providers blocked without keys | Sweep; typed settings (A-20) |
| 15 | **Backup / export** | DB backup to `data/backups`, audience JSON export | Working | Earlier sessions; unchanged code |
| 16 | **Security envelope** | 127.0.0.1 bind, Host allow-list, CSRF header, CSP on generated HTML, SSRF guard (now incl. DNS rebinding), secrets in Keychain, raw errors hidden | Working | Edge run: missing header 403, foreign Host 403, SPA traversal blocked; rebinding test |
| 17 | **External integrations** | Stripe / Gumroad / Shopify / Lemon Squeezy sync; Anthropic / OpenAI; YouTube API; Brave | **Mock-only / unverified live** | No keys on this Mac, by rule |
| 18 | **Not built (deliberate)** | Payments, publishing, accounts/multi-tenant, YouTube OAuth, Meta/TikTok APIs | Not built | DECISIONS.md, ROADMAP.md |

## Performance (scratch server, M-series Mac, CPU busy with the local model)

- Page loads (108 loads across 27 routes, desktop and phone width, light and dark themes): median **0.77 s**, max **1.06 s**, including a network-idle wait.
- 20,000-order CSV import: **0.6 s**. With 20k orders, statement **0.10 s**, dashboard **0.13 s**, product page **0.06 s** (110 KB; sales list capped at 500 rows).
- Frontend bundle: 341 kB JS (98 kB gzipped), one chunk. Fine for a local app; not split further.
