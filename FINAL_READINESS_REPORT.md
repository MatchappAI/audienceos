# Final readiness report: AudienceOS v1.5.0 (2026-11-16)

## Verdict

**Ready for the 3 supervised creator pilots on this Mac. Readiness score: 8.5 / 10.**

This isn't "production-ready for the public". There are no accounts, no hosting, and the checkout syncs and external AI have never touched a real account. For what AudienceOS is meant to do now (one operator, local data, pilots), every core flow works end to end with evidence, and every serious defect found is fixed.

What stops it scoring higher:
- **−0.5:** four checkout syncs and the external AI providers are mock-tested only (no keys).
- **−0.5:** two money rules need your decision (deal term and changed terms; today they show warnings).
- **−0.5:** the quality of the local 7B model's ideas on real creators is still unproven. The analysis itself is reliable.

## Evidence

| What | Result |
|---|---|
| Automated suite | **117 passed, 0 failed** (`cd backend && .venv/bin/python -m pytest`) |
| Frontend build | Clean (`tsc --noEmit` + Vite; 341 kB JS / 98 kB gzipped) |
| Full journey, fresh DB, real local model | **33/33 checks**, 0 console errors, 0 failed API calls (`e2e/2_full_journey.js`) |
| Analysis | 33 signals · 5 problems · 3 opportunities in 8–11 min; quotes verified against the source |
| Money | 70/30 of contribution: base $136.85 → creator $95.80 (half-up of 95.795), agency $41.05. A $10 payout leaves $85.80 owed, and the screen, CSV, PDF and creator portal all agree |
| Route sweep | 108 page loads (27 routes × 2 themes × desktop/phone). No errors, no unnamed controls, no horizontal scroll. Median 0.77 s |
| Edge cases | **30/30** (uploads, unicode, injection, headers, money validation, a 20k-order CSV in 0.6 s) |
| Recovery | Double start → 1 job. Refresh mid-run → progress shown. Restart mid-run → resumed. Engine down → clear message |
| Independent review | 13 backend defects reproduced by a second reviewer; all fixed and re-run |
| Network | Listens on 127.0.0.1 only. No API-key patterns in the logs |

## Tests: passed, failed, blocked, not run

- **Passed:** 117 automated, 33/33 journey, 30/30 edge, 108/108 sweep loads (excluding 8 deliberate "not found" checks), 5/5 extra UI checks (keep unfilled criterion, retire → reopen, delete-with-confirm).
- **Failed (open, minor):** UTF-16 CSV import (O-01, P3; workaround: save as CSV UTF-8).
- **Blocked:** real Stripe/Gumroad/Shopify/Lemon Squeezy sync, Anthropic/OpenAI, the YouTube Data API, Brave search (no keys, by rule); YouTube OAuth and Meta/TikTok APIs (need app registrations).
- **Not run:** restarting the live app on 1.5.0 (needs your OK); Windows/Linux.

## Bugs found and fixed: 36 plus 6 from the unfinished 08 Nov pass (full list in `ISSUE_TRACKER.md`)

- **P1 (6):**
  - Reprocessing deleted the evidence behind finished analyses.
  - A draft could be launched without approval through the API.
  - Video frames went to an external AI without per-run consent.
  - DNS rebinding could reach this Mac or the local network.
  - The vision model locked the database.
  - A small analysis could run 30+ minutes.
- **P2 (17):**
  - Money: the owed-to-creators total, undated or out-of-term orders, changed terms, truncated syncs, delete and overpay confirmations.
  - Imports: CSV and JSON data loss.
  - Settings: the string "false" switched external AI on.
  - API keys in logs, prompt-wrapper breakout, no download deadline, DOCX bomb, headers forwarded on redirect, duplicate analyses, partial channel update.
  - Contrast below WCAG AA.
- **P3 (13):** retired products, statement badge, email and experiment-date validation, cancelled jobs, calculator grammar, inf/NaN, robots 5xx, bad Content-Length, unknown /api 404, narrow headers, kept criteria, stage labels, path checks.

## UX improvements

- Plain-language warnings on the statement (what's left out, and why).
- Confirmation before destructive or unusual money actions.
- **Reopen as draft** for retired products.
- An honest "not generated: too little evidence" note instead of a long hang.
- The right stage label during analysis.
- Contact errors shown next to the form.
- An icon-rail sidebar and wrapping headers on narrow windows.
- Readable faint and warning text.

## Still open or blocked, and why

- **O-01 (P3):** UTF-16 CSV is refused.
- **O-02 (P3):** deleting a video mid-sampling can leave an orphan frames folder.
- **O-03 (decision):** an asset quoting a different price than the product is only a warning.
- **O-07 / A-07 / A-08 (decision):** one active deal applies to all time.
- **O-04 to O-06 (blocked):** external integrations need your keys or app registrations.
- **Limit:** cancelling during a long model call stops the job, but the local model finishes its current request unless the app restarts.

## Needs your approval

1. **Push** branch `audit/2026-11-16` to GitHub (nothing is pushed) and merge it into `main`.
2. **Restart the live app** to run 1.5.0. It applies migration 005 to your real database.
   - Your live DB is nearly empty today, and the migration was tested on a copy of it.
   - Safe steps: quit AudienceOS, copy `~/AudienceOS/data` to a backup folder, then run `~/AudienceOS/start.sh`. Note that `start.sh` opens a window.
   - The frontend in `frontend/dist` is already rebuilt, so the live app shows the new UI on its next page load. The old backend keeps working with it until you restart.
3. **Keys and registrations** (optional, to remove the "unverified live" marks):
   - a Stripe restricted key, Gumroad token, Shopify read_orders token or Lemon Squeezy key;
   - an Anthropic key, if you want higher-quality analysis (with consent);
   - YouTube and Brave keys.
4. **Two contract decisions:** should sales outside a deal's dates be shared? And should new terms apply only to later sales?

## Top next improvements (highest value first)

1. Make deals dated history (terms per period), once the contract wording is settled.
2. Run one real checkout sync per provider as soon as a pilot creator's checkout exists.
3. For each pilot, compare local 7B ideas against one consented external-model run, and decide per creator.
4. Accept UTF-16 CSVs (common Excel "Unicode text" exports).
5. Make Cancel interrupt an in-flight local-model call, using a streaming request.
6. Add the `e2e/` scripts to a manual pre-release checklist (they need Chrome and the local model, so they're not in CI).
