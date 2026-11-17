# Audit change log: 2026-11-16 (branch `audit/2026-11-16`, v1.5.0)

Commits are listed in order. IDs refer to `ISSUE_TRACKER.md`. Nothing here has been pushed.

1. **Money input checks and narrow-window sidebar** (finishes the unfinished 2026-11-08 pass; reviewed and tested before committing)
   - Money dates must be YYYY-MM-DD, a refund can't exceed its sale, and a deal can't end before it starts.
   - CSV imports skip unreadable dates and refunds bigger than the sale, and say why.
   - Plain wording in the statement CSV.
   - A never-approved draft is no longer shown as "back to draft".
   - Below 760 px the sidebar becomes an icon rail.
   - Issues: B-01 to B-06.
2. **Launch gate and money safety**
   - No pause-to-launch bypass, only drafts can be approved, and retired products reopen as drafts.
   - Flagged assets need an explicit confirmation in the API.
   - "Owed to creators" ignores overpaid creators.
   - Statement warnings: undated orders, orders outside the deal term, changed terms.
   - Creator email and experiment dates are validated.
   - Partial channel updates are safe.
   - One analysis at a time.
   - Stricter path checks.
   - Confirmation before deleting orders and costs, and before a payout bigger than the balance.
   - Issues: A-01 to A-15.
3. **Ingest and fetch safety** (from the independent backend review; each finding reproduced first)
   - Evidence survives reprocessing (migration 005).
   - DNS-rebinding guard, whole-download deadline, and keys dropped on cross-host redirects.
   - The vision model no longer locks the database.
   - CSV/JSON import fixes; DOCX bombs refused.
   - Typed settings, and consent needs a real `true`.
   - No API keys in logs.
   - Prompt wrappers can't be broken out of.
   - Cancelled jobs stay cancelled.
   - Calculator grammar tightened; AI output can't contain inf/NaN.
   - Issues: A-16 to A-28, A-31, A-32.
4. **Checkout sync truncation warning; no external AI for video frames during import.** Issues: A-29, A-30.
5. **Unknown `/api` paths return a JSON 404; card headers wrap at phone width.** Issues: A-33, A-35.
6. **WCAG AA contrast for faint and warning text; Save design keeps criteria that still need a threshold.** Issues: A-34, A-36.
7. **Analysis robustness, v1.5.0, e2e scripts in the repo**
   - Thin material skips product ideas with a reason instead of a 30-minute run-on.
   - Stage labels are no longer dropped.
   - Cancel closes the analysis.
   - New `e2e/` folder.
8. **Docs**: the six audit documents, plus updates to AUDIT.md, TESTING.md, CHANGELOG.md and README.

## Data and migration notes

- **Migration 005** rebuilds the `evidence` table (same rows, same ids). Only the foreign-key action on `content_item_id`/`comment_id` changes, from CASCADE to SET NULL. Tested on:
  - the scratch DB that holds a real analysis (33 evidence, 33 signals, 22 opportunity links kept; foreign-key check clean);
  - a read-only copy of the live DB.
- The live app needs a restart to pick up the backend changes; it applies migration 005 on start. Back up `data/` first (see FINAL_READINESS_REPORT.md).

## Before and after

| Measure | Before | After |
|---|---|---|
| Automated tests | 87 (incl. 5 from the unfinished pass) | **117** |
| Known P1 issues | 6 found (gate bypass, evidence loss, DNS rebinding, DB lock, frames to external AI, analysis run-on) | 0 open |
| Small-text contrast (light) | 3.0:1 faint, 4.4:1 warning | 4.6:1+, 5.5:1 |
| Unknown `/api` route | 200 + app HTML | 404 JSON |
| Thin-material analysis (5 signals) | 30+ min, then cancelled | Finishes after clustering with a reason |
