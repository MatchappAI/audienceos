# User journeys (2026-11-16)

Each journey lists the happy path, then the alternative, failure and recovery paths that were exercised. **E2E** means run in headless Chrome against the scratch server (scripts in `e2e/`). **API** means run against the scratch server over HTTP. **Unit** means the automated suite (`backend/tests`).

## J1. First-time setup: demo creator to first analysis
1. Dashboard (empty) → **Load demo project** → Content & sources. 4 sources become *Ready*. *(E2E)*
2. **Go to analysis →** → **Run analysis**. Progress shows by stage. 10 min 40 s later: 33 signals, 5 problems, 3 opportunities. *(E2E)*
- *Alternative: a real creator.* **Add creator** → upload, paste or link → "N sources ready. Next: run the analysis". *(Earlier session; API edge run)*
- *Failure: AI engine down.* Dashboard shows "AI provider not ready: … Restart AudienceOS with the launcher". Run analysis and Draft asset return the same message, and no job is created. *(API, engine pointed at a dead port)*
- *Failure: double click / two tabs.* The second start returns the running job; only one job exists. *(Unit, 6 threads; E2E)*
- *Recovery: refresh mid-job.* The page reloads showing the stage and percent. *(E2E)*
- *Recovery: app restarted mid-job.* The job resumes as attempt 2 and finishes. *(E2E, server restarted during "Collecting stored material")*
- *Edge: bad uploads.* An exe renamed to .csv, an empty file, a `../../etc/passwd.txt` name, a duplicate, unicode text, a 2 MB paste, a paste over the limit. Each is refused or handled with a clear message. *(API)*
- *Edge: prompt injection in comments.* The text is analysed as data, and no "verified purchase" label results. *(API, rules engine; Unit wrapper test)*
- *Edge: reprocess a source after analysis.* Evidence, signals and opportunity links are kept and re-linked. *(Unit; was data loss before, A-16)*

## J2. Research to evidence
Problems tab → problem row → quote → **evidence drawer** (verbatim quote, "verified against the source", how it was read, original comment) → Esc closes. Then Signals, Intelligence, Library search. *(E2E)*

## J3. Opportunity to validated decision
Opportunity → **Recalculate** scenario → **Approve for testing** → **Create validation experiment** → set thresholds (2%, 10 purchases) → **Save design** → import the results CSV and the orders CSV → re-import orders (shows "skipped 5 already imported") → recommendation *stop* → record **Go** (labelled as an override) → opportunity *Validated*. *(E2E)*
- *Edge:* criteria without thresholds show "set a threshold" (Unit). Experiment dates must be YYYY-MM-DD (Unit).
- *Alternative:* **Revise** keeps it testing; **Stop** rejects it (Unit, earlier sessions).

## J4. Asset: draft, review, approve, export
Opportunity → **+ Draft asset** → Landing page → **Draft it** → drawer opens after 77 s → claim flags shown → tick "I fixed or checked…" → **Approve** → export .md/.html/.docx → preview served with `default-src 'none'`. *(E2E)*
- *Failure:* approve a flagged draft without the tick: the button is disabled, and the API refuses too (Unit).
- *Edit:* changing the text sends it back to draft and re-runs the rule check (Unit).

## J5. Product: create, approve, launch, sell
**Create product** → storefront + https link + price → **Save** → tick 5 checks + approver → **Approve for launch** → **Mark as launched** → import the orders CSV (5 orders, 1 refund) → add a $12 shared cost. *(E2E)*
- *Gate:* no checkout link, a draft asset, a missing check, or no approver → refused with the reason (Unit). A draft can't be paused into launch (A-01). Retired → **Reopen as draft** → approve again (Unit).
- *Material edit after launch:* the product goes back to draft, sales are kept, and the dashboard asks to re-approve (Unit).
- *Edge:* negative sale, duplicate order ID (409), `http://` or `javascript:` checkout link, refund larger than sale, non-ISO dates → refused (API/Unit). A 20,000-order CSV imports in 0.6 s; re-import adds 0 (API).

## J6. Money: deal, statement, payout, portal
Creator page → **Save deal** (70% creator / 30% agency of contribution) → statement: base $136.85 → creator $95.80, agency $41.05 → **Record payout** $10 → owed $85.80 → CSV, PDF and Creator view all show the same balance. *(E2E)*
- *Options:* loss carry-forward, minimum guarantee (completed months, cap, recoup) (Unit).
- *Warnings:* undated orders in a period, orders outside the deal term, terms changed (Unit).
- *Edge:* share over 100%, zero payout, invalid email → refused. A payout above the balance asks first (UI). An overpaid creator doesn't reduce the dashboard total (Unit).
- *Payout file:* only creators with a positive balance, demo excluded, missing emails flagged (Unit).

## J7. Reports, library, backup
Reports tab → **Generate report** → HTML, PDF, JSON, 2 CSVs all served (E2E). Library search deep-links to sources (E2E). Backup writes `data/backups/…db` (earlier session).

## J8. Settings and keys
Toggles save. Keys go to the Keychain and are never returned (Unit). A string `"false"` for external AI is refused (A-20). Model downloads show layer progress (earlier session). External providers need a key **and** opt-in **and** per-run consent (Unit).

## J9. Checkout sync (mock-only)
Product → Checkout sync → provider + ID → **Sync now**. Re-sync is idempotent, refunds/fees update, non-USD and truncation produce warnings, auth errors never echo the key (Unit, mocked APIs). **Not verified against real accounts.**

## State machine: product status (as enforced by the API)
`draft --approve(5 checks, https link, assets approved, approver)--> approved --launch--> launched`
`launched --pause--> paused --launch--> launched`
`approved|launched|paused --material edit or set draft--> draft (approval withdrawn, sales kept)`
`any --retire--> retired --set draft--> draft`
Refused: `draft→paused`, `draft→launched`, approving anything that isn't a draft.
