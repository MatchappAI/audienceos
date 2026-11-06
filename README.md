# AudienceOS

A local-first Mac app for running an AI creator-monetization agency. It covers the whole loop: find out what a creator's audience struggles with and would pay for, propose products grounded in the audience's own words, validate demand with real purchases, generate and approve the launch assets, track sales from the creator's own checkout, and settle a 70/30 revenue share.

Everything runs on this Mac. The server listens on `127.0.0.1` only, data lives in one SQLite file, and analysis uses a bundled local model (Ollama `qwen2.5:7b`). No account, no API cost, and no data leaves the Mac unless you switch on an external AI provider and confirm each run.

## Install

Everything is already installed in `~/AudienceOS`:

| Piece | Where |
|---|---|
| Backend (FastAPI + SQLite) | `backend/` with its own `.venv` (Python 3.12) |
| Frontend (React + TypeScript, prebuilt) | `frontend/dist` (served by the backend) |
| Local AI engine + models | `runtime/ollama`, `runtime/models` (`qwen2.5:7b`, `qwen2.5:3b`) |
| Transcription | faster-whisper `base` + bundled FFmpeg (in the venv) |
| Your data | `data/` (`audienceos.db`, uploads, media, reports, exports, backups, logs) |

To rebuild from source after code changes:

```sh
cd ~/AudienceOS/frontend && npm install && npm run build      # type-checks, then builds to frontend/dist
cd ~/AudienceOS/backend && .venv/bin/python -m pytest          # 56 tests
```

## Launch

- Double-click **`~/Desktop/AudienceOS.app`**, or
- run `~/AudienceOS/start.sh` (or double-click `AudienceOS.command`).

Each starts the local AI engine if it isn't running, starts the server on `http://127.0.0.1:8760`, and opens it in a Chrome app window (or your default browser). Running it twice is safe.

**To quit:** run `~/AudienceOS/stop.sh`. It stops the server and the bundled AI engine. It never stops a system-wide Ollama install. Background jobs (imports, analyses, drafts) are saved in the database and resume automatically on the next launch.

## Your first workflow (about 20 minutes, mostly waiting on the local model)

1. **Dashboard → Load demo project.** This loads a clearly labeled synthetic creator, *Hearth & Crumb (DEMO)*: an Instagram comment export, post analytics, a newsletter issue and a short video that gets transcribed locally.
2. **Content & sources:** wait until all 4 sources say *Ready*, then click **Run analysis →**.
3. **Audience problems:** the analysis takes about 10–15 minutes on the 7B model. Then click a problem row to see the quotes, and click any quote to open the **evidence drawer**: the verbatim text, how it was classified, and the original comment or timestamp.
4. **Commercial signals / Audience Intelligence:** these show buying language ranked by strength, the audience profile, and the unknowns.
5. **Product Opportunities:** open one. Adjust the **scenario** (reach, share who see it, purchase rates), **Approve for testing**, then **Create validation experiment**.
6. **Validation Lab:** set success criteria *before* results come in. Import `fixtures/demo/experiment_results_demo.csv` and `fixtures/demo/orders_demo.csv`, read the recommendation, and record **Go / Revise / Stop**.
7. **Assets:** on the opportunity, use **+ Draft asset** (for example, a landing page). Review the claim check, **Approve**, then export as `.md`, `.html` or `.docx`.
8. **Product & launch:** **Create product**, add the storefront and an `https://` checkout link, tick the 5 launch checks, enter your name, **Approve for launch**, then **Mark as launched** once it's live.
9. **Revenue:** import the checkout's order CSV on the product and add costs. On **Creators & Revenue → the creator**, set the deal (default 70% creator / 30% agency of contribution), record a payout, and download the statement CSV.
10. **Reports & library:** **Reports → Generate report** gives HTML, PDF, JSON and two CSVs. **Research Library** searches everything, and **Back up database** writes a copy to `data/backups/`.

For a real creator, use **Add creator** and import their own exports (see `DATA_SOURCES.md` and `NEXT_STEPS.md`).

## Documentation

| File | What it covers |
|---|---|
| `FEATURES.md` | What works, what's limited, what's not built |
| `TESTING.md` | Automated tests and live end-to-end runs, with real results |
| `AUDIT.md` | Strategy audit: each workflow step → status, pilot readiness, what's deferred |
| `ARCHITECTURE.md` | Modules, data model, pipeline, security |
| `DECISIONS.md` | Why things are built the way they are |
| `DATA_SOURCES.md` | What each platform allows, and the permitted alternatives |
| `NEXT_STEPS.md` | Things only you can do (contracts, checkouts, exports, keys) |
| `ROADMAP.md` | Deliberately deferred work |
| `CHANGELOG.md`, `PROGRESS_LOG.md` | History |
