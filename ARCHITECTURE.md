# Architecture

One local process, one SQLite file, one folder. Nothing listens beyond `127.0.0.1`.

```
Browser (Chrome app window) ──► FastAPI on 127.0.0.1:8760 ──► SQLite  data/audienceos.db
   React + TS (frontend/dist)      │                          files   data/uploads, media, reports, exports, backups
                                   ├─ background worker (thread; jobs persisted in SQLite, resumed after restart)
                                   ├─ FFmpeg (bundled via imageio-ffmpeg) + faster-whisper (local transcription)
                                   └─ AI providers: Ollama on 127.0.0.1:11434 (local, default)
                                                    Anthropic / OpenAI (optional, external, opt-in + per-run consent)
                                                    Rules engine (no model; labeled)
```

## Backend modules (`backend/app`)

| Module | Responsibility |
|---|---|
| `db.py`, `migrations/` | Connections, numbered SQL migrations, integrity constraints, backup |
| `security.py` | SSRF-safe fetching (public IPs only, every redirect re-checked, ports 80/443, size caps, robots.txt), file-type sniffing |
| `settings_store.py` | Settings in SQLite; API keys in the macOS Keychain (never logged or returned) |
| `jobs.py` | Persisted job queue, progress, cancel, retry, crash recovery |
| `ingest/` | `platforms.py` (detection + honest access policy), `urls.py` (permitted retrieval per platform), `files.py` (text/PDF/DOCX/CSV/JSON/media/images), `media.py` (FFmpeg, Whisper, frame sampling), `store.py` (normalization, dedup, spam, hashed authors) |
| `ai/` | `providers.py` (provider interface), `schemas.py` (validated structured outputs), `pipeline.py` (the 7 stages), `evidence.py` (quote verification), `rules.py` (no-model analysis + intent guard) |
| `services/` | `scoring.py` (rubric), `economics.py` (scenarios + formulas), `experiments.py` (metrics, criteria, CSV), `assets.py` (generation + claim review + landing pages), `competitors.py`, `reports.py` (HTML/PDF/JSON/CSV), `intel.py` (intelligence view), `agency.py` (product P&L, revenue share, payouts, pipeline stage) |
| `routers/` | REST API (`core.py`, `monetize.py`), `demo.py` |

## Data model

Original evidence and AI interpretation are stored separately:

- **Original material:** `sources` → `content_items` (+ `transcripts`, `media_frames`, `engagement_metrics`) and `comments`. Every source records retrieval method, date, what was obtained and what is missing.
- **Evidence:** `evidence` holds verbatim excerpts with a locator (timestamp or character range) pointing back to a comment or content item.
- **AI interpretation:** `analyses` (one per run) → `signals` (each points to one evidence row) → `clusters`; `opportunities` (linked to evidence via `opportunity_evidence`); every model call is logged in `ai_runs` with provider, model and whether data left the Mac.
- **Validation:** `experiments` → `experiment_events` (funnel counts) and `orders`.
- **Agency operations:** `organizations` (creators) → `deals` (revenue-share terms), `products` (approval + launch), `product_sales`, `product_costs`, `payouts`.
- Hierarchy: `workspaces` → `organizations` → `audiences` → `channels`/`sources`. The workspace layer is where future self-service creator accounts would attach; it is not exposed yet.

## The intelligence pipeline

1. **Classification:** a sample of content and comments → profile (topics, intended audience, characteristics with evidence pointers, unknowns).
2. **Extraction:** small batches of units (`C#` comments, `D#` content chunks) → signals with type, intent level and a quote. **Every quote is located in the source text; quotes that can't be found are discarded.** Strong intent labels (spending, purchase, paid request, buying question) are kept only if the quote's own words support them.
3. **Clustering:** the model groups signals into specific problems; a theme holding most signals is split again. If the model fails, keyword grouping is used instead.
4. **Commercial intent:** computed in code per distinct voice (one person repeating themselves counts once): intent score 0–5, evidence quality (Strong / Moderate / Weak / Creator content only).
5. **Competitors** (separate): entered URLs are retrieved and visible prices extracted with a date; automated search only with a Brave API key.
6. **Opportunities:** the model must cite theme and evidence numbers. Ideas with no traceable evidence are dropped.
7. **Scoring:** 3 data-derived criteria + 8 model-rated criteria, with configurable weights → a 0–100 index of how attractive an idea is to test next, compared with the others. It is not a probability.

Retrieved content is wrapped as untrusted `<source_material>`. Providers have no tools, file access or shell, and every output is schema-validated, so injected instructions can't cause actions.

## Security

- The server binds to 127.0.0.1 only. It rejects requests whose Host isn't localhost (stops DNS-rebinding attacks), and every state-changing API call needs a custom header (stops cross-site forgery).
- Generated landing pages and reports are served with a strict Content-Security-Policy (no scripts, except the validated calculator).
- Calculator formulas are checked against an arithmetic-only grammar before being turned into JavaScript.
- Parameterized SQL throughout; uploads are sanitized, sniffed, size-capped and stored per audience.
