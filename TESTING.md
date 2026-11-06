# Testing

## Session 5 — 2026-11-06 (v1.4.0)

**Automated: 82 tests pass.** New tests cover Shopify (only this product's items counted, partial refunds, `utm_source` channel, rejects non-myshopify hosts, follows pagination on the same host, pending orders skipped), Lemon Squeezy (product match, pagination, refunds, non-USD warning), and migration 004 keeping sales rows during the table rebuild. Tests are now pinned to an unreachable AI-engine address.

**Real models (scratch server, port 8761):**
- `qwen2.5vl:3b`: the demo video's 2 frames and an extracted image were described accurately ("DEMO VIDEO" in white on beige), in about 70 s. OCR also read "DEMO VIDEO".
- `nomic-embed-text`, sampling: 700 synthetic comments (560 loud starter/loaf, 110 equipment, 30 gluten-free with ≤5 likes). The 120-comment sample kept 6 gluten-free comments; likes-only sampling kept 0. Took about 33 s.
- `nomic-embed-text`, grouping: before the fix, gluten-free merged with equipment questions; after the prefix + silhouette/Ward change, it forms its own group.

**Live app:** restarted on 1.4.0, with the database backed up first. Migration 004 applied.

**Still not tested live:** a real Stripe, Gumroad, Shopify or Lemon Squeezy account (no keys on this Mac).

## Session 4 — 2026-11-06 (v1.3.0)

**Automated: 79 tests pass** (59 → 79), on this Mac and in GitHub Actions CI (Ubuntu, where OCR is skipped).

| Area | What was checked |
|---|---|
| Loss carry-forward | Default per-product floor vs deal-wide offset; a deal-wide loss is carried forward and nothing is owed |
| Minimum guarantee | Completed-month counting (month-end edge cases), cap at guaranteed months, recouped once earned share exceeds it |
| Payout file / PDF / portal | Wise-column CSV with the right balance; PDF is valid; portal escapes HTML, has no scripts, and is served with a strict CSP; fingerprint is stable and changes with the numbers |
| Next tests | Price and channel suggestions from real sales; a suggestion's prefill creates a valid experiment; the price suggestion disappears once a second price has been tested |
| Checkout sync | Stripe (pagination, unpaid sessions skipped, fees, refunds, channel from client_reference_id or metadata) and Gumroad, both against mocked APIs; re-sync is idempotent; auth errors never echo the key |
| OCR / embeddings / model pulls | See `backend/tests/test_analysis_extras.py`. OCR was verified for real on this Mac (rendered PNG and image-only PDF); embed and pull calls are mocked |

**Live, scratch server (port 8761, separate data folder):** created a creator, launched a $29 product, added 7 orders, a $40 cost and a 70/30 contribution deal with a $100/month guarantee from Aug 1. Results: earned $98.42 (= ($203 − $22.40 − $40) × 70%), plus a $201.58 guarantee top-up for 3 months, for $300 owed. These figures matched in the payout CSV, the PDF and the portal. Screens checked: product page (Next tests, Checkout sync), creator page (deal terms, PDF, Creator view), Creators & Revenue (Payouts due), Settings (new keys, model downloads, OCR status). Two display bugs were found and fixed: "7.0 orders" and a truncated sync dropdown.

**Not tested live:** a real Stripe/Gumroad account (no keys on this Mac; the mapping follows the providers' API docs and was tested against mocks), and a real `nomic-embed-text` or vision-model download (not pulled, to avoid multi-GB downloads without asking).

## Session 3 — 2026-11-06 (v1.2.0)

Run on a **separate copy** (port 8761, scratch data folder) so the real `~/AudienceOS/data` was not touched. Driven by headless Chrome (puppeteer-core), clicking the real UI.

| Step | Result |
|---|---|
| Unit + API suite | **59 passed** (3 new: analysis-running next action, price mismatch, criteria without thresholds). |
| Load demo → analysis (`qwen2.5:7b`) | 4 sources ready; analysis about **10 min** → 3 opportunities. |
| Approve → experiment → results | 400 visitors, 12 purchases → 3.0% conversion, $453 contribution. Decision *Go* → opportunity *Validated*. |
| Product → approve → launch | Price $39, Gumroad https link, 5 checks + approver → Approved → Launched. |
| Orders CSV (4, 1 refunded) | Net $117.00, fees $5.72, contribution **$111.28**. By channel: Instagram 3 / $78, newsletter 1 / $39. |
| 70/30 deal + $20 payout | Creator **$77.90**, agency **$33.38** (111.28 × 0.7 = 77.896). Balance owed **$57.90**. CSV matches. |
| Landing-page asset | Drafted in 235 s (the shared local engine was slower than the 35 s measured before). One claim flagged. Exports md/html/docx 200. Preview CSP `default-src 'none'`. |
| Route sweep | **20 routes × light/dark, 0 console errors, 0 failed API calls, no horizontal scroll, no clipped text**, before and after the fixes. |

The fixes found in this run are listed under 1.2.0 in `CHANGELOG.md`.

Every result below was actually run on this Mac on 2026-11-05. Nothing is estimated.

## 1. Automated suite

```sh
cd ~/AudienceOS/backend && .venv/bin/python -m pytest -q
```

**Result: 56 passed, 0 warnings.** This includes the 29 tests from session 1.

Main areas covered:

| Area | Tests |
|---|---|
| Evidence | Invented quotes rejected; near-verbatim quotes replaced with the source text; timestamp lookup. |
| Intent | Strong labels need supporting words. `guard_intent` downgrades the exact quotes mislabeled in scratch analysis `an_50a6d…`. Explicit buying language decides the label. `store_signals` applies the guard on every path. |
| Reference IDs | `T#`/`E#` stripped from prose (parenthesized lists, ranges, "as seen in E4, E7 and E9"). A leaked opportunity draft validates with clean text. The prompt forbids them. The auto-hypothesis reads cleanly. |
| Scoring & economics | Distinct-voice counting, score bounds, scenario formulas, experiment metrics with separate denominators, missing denominators are `None` (not 0), go/revise/stop rules. |
| Security | SSRF blocklist, file sniffing, Host and header guards. External providers need a key **and** per-run consent. A saved API key never appears in `/api/system`, `/api/dashboard` or the logs. |
| API flows | Full research flow with the rules engine; offline mode; Instagram reported as unsupported; idempotent experiment CSV import; migrations idempotent. |
| Agency | Revenue share on both bases, launch gate, payouts and balance. A price change → back to draft **with `reapproval` details and sales kept**. Re-approval clears it. Statement CSV cents and counts. |
| Library | Content results carry `source_id` pointing to a real source. |
| Cleanup | Deleting an audience removes its uploads, media and report folders. Landing-copy edits still accept the `copy` field. |
| Assets | A draft without a title is accepted. The claim review flags links, emails and phone numbers as possibly invented. |
| Recovery | A stale `running` analysis and its AI-call rows are closed out when a new run starts. |

Frontend: `cd frontend && npm run build` runs `tsc --noEmit` and then the Vite build. **Result: clean** (`index.js` 324.5 kB, 93.0 kB gzipped).

## 2. Live test on the real app (port 8760, `~/AudienceOS/data`, fresh database)

The app was launched with `~/AudienceOS/start.sh` and driven by headless Chrome (puppeteer-core, scripts in the session scratchpad). I chose headless Chrome over the Chrome extension so each page could be captured in both color schemes. Every page was screenshotted in **light and dark** mode and checked for console errors, failed requests and HTTP ≥ 400 on `/api/`.

| Step | Result |
|---|---|
| Load demo project | 4 sources ready (70 comments with 3 flagged duplicates; post analytics for 4 items; newsletter of 160 words; reel transcribed locally, 89 words with timestamps, 2 frames). |
| Local analysis (`qwen2.5:7b`) | **About 12 min.** 71 units, 65/65 comments, 3 duplicates and 2 spam excluded, 1 unverifiable quote discarded, **33 signals, 5 problems, 3 opportunities.** |
| Intent check | All 16 strong-intent signals contain supporting words (e.g. "I paid $120 for an in-person class…", "Would buy a starter kit from you in a second"). The guard was then tightened: "Where can I buy the lame you use" becomes a buying question. |
| `T#`/`E#` leak check | 0 opportunities, 0 hypotheses, and the report HTML contain reference IDs. |
| Evidence drawer | Opens from a problem's quote with the verbatim text, interpretation, source, retrieval method and the full comment with likes and post URL. |
| Scenario | Reach 206,000 × 15% → 30,900 people; 0.1/0.5/1% rows; contribution per sale $38.20; break-even 1. |
| Experiment | Criteria (visitor → purchase ≥ 2%, purchases ≥ 20). Imported 3 result rows and 5 orders. Mismatch warning: "Recorded results list 28 purchases vs 5 orders — orders were used." Recommendation *Stop*; recorded *Go*, labeled as an override. |
| Asset | Landing page drafted in **35 s**, 0 claims flagged, approved. Exports: `.md` 1,928 B, `.html` 4,012 B, `.docx` 37,402 B. The preview is served with `default-src 'none'`. |
| Product & launch | Storefront and https link set, 5 checks plus approver → Approved → Launched. 4 orders imported (1 refunded), $12 shared cost. Net $87.00, fees $4.56, contribution $70.44. |
| Revenue share | Deal 70/30 on contribution: creator **$49.31**, agency **$21.13**. Payout $20 → balance owed **$29.31**. Checked by hand: 70.44 × 0.7 = 49.308. Statement CSV matches. |
| Back to draft | Changing the price to $55 → "Back to draft — price changed after launch; re-approve to relaunch. Sales history is kept." The 4 orders were still counted on the product, statement and dashboard. |
| Reports | HTML 21 kB, PDF 5.9 kB, JSON 168 kB, opportunities CSV, signals CSV, all HTTP 200. |
| Library & backup | Search "starter" → content results deep-link to `?source=…&item=…` and open the transcript drawer. Backup written to `data/backups/` (444 kB). |
| First-time path (non-demo) | New creator → paste text → "1 source ready. Next: run the analysis…". Dashboard: "Run the first analysis for UI Test Creator audience". Empty states checked on every tab. Test creator deleted afterwards. |
| Route sweep | **24 routes × light/dark, 0 console errors, no horizontal scroll** on 3 separate sweeps. Each page settles in about 1.1–1.5 s, including a 0.5 s network-idle wait. |

### Polish passes

| Pass | What it found and fixed |
|---|---|
| 1 | Dashboard "Nothing pending" after an analysis; opportunity header wrapping; cramped experiment metrics; duplicate missing-evidence; a misleading fees hint; running-analysis empty state; no "ready → analyze" cue on Sources. |
| 2 | UTC date defaults (a real bug); a sentence used as the landing-page button; missing checkout fallback; a cramped product sidebar; truncated placeholders; statement CSV formatting. |
| 3 | Awkward auto-hypothesis; criteria without units; duplicate "(demo)" in the picker; text-only models offered as vision models; dashboard action layout; "excl. demo" labels; wrapping dates; pluralization; a duration estimate that didn't match measured runs. |
| 4 | A non-demo first-time path and all empty states. **Nothing material found.** |

## 3. Quit and relaunch (job recovery and persistence)

1. Started a reanalysis of the demo audience.
2. At "Reading audience material (2/3)", ran `stop.sh`; port 8760 was closed.
3. `open ~/Desktop/AudienceOS.app`.

**Result:** the server came back. The same job `job_ecd8269…` resumed (attempt 2), and the interrupted analysis was marked failed: "Interrupted (app closed) — superseded by a new run". The new run finished in about 7 minutes with **33 signals · 5 problems · 3 opportunities**. All data persisted: 1 product, 4 sales, 1 payout, 1 experiment with 5 orders, 1 asset.

Two problems this exposed, both fixed:

- `stop.sh` didn't stop an engine started as `./ollama/ollama serve`. It now matches on the executable path.
- The interrupted run's AI-call row stayed "running". It is now closed out, and a test covers this.

## 4. Fresh-database demo run, end to end (scratch server on port 8761)

A new empty data dir was driven through the HTTP API (`fresh_e2e.py` in the session scratchpad), using the same local model.

**First attempt failed at the asset step:** `qwen2.5:7b` returned an *offer* draft without a `title` twice, and the job failed validation. The same draft also contained a website the model invented for the demo creator. Both were fixed (title optional with a fallback; links, emails and phones flagged in claim review). The run was then **repeated from a new empty database**:

| Step | Result |
|---|---|
| Fresh DB | 0 audiences |
| Demo ingest | 4 sources ready (5 s) |
| Analysis | **33 signals · 5 problems · 3 opportunities in 526 s** |
| Intelligence | 5 clusters; the evidence record resolves to its source |
| Scenario | Recalculated (2 rate rows) |
| Experiment | 3 result rows + 5 orders imported; decision recorded (app recommended *stop*) |
| Asset | *Offer* drafted in 78 s with **2 claims flagged** (guarantee wording, by both rules and AI review). Approved. `.md`/`.html`/`.docx` exports. |
| Launch | Gate passed → launched |
| Statement | Net $156.00 − fees $7.15 − shared $10.00 = base **$138.85** → creator **$97.20** (97.195 rounded half-up, checked with `Decimal`) → owed **$92.20** after a $5 payout |
| Statement CSV | OK |
| Back to draft | Price change → draft, `reapproval` set, sales kept |
| Reports | HTML 21.0 kB · PDF 6.0 kB · JSON 120 kB · opportunities CSV · signals CSV |
| Library | Content results carry `source_id` |
| Backup | Written |

Two first-pass "FAIL" lines in this run came from my test script, not the app: a float tolerance of exactly ±0.01 on the half-up cent, and measuring the size of parsed JSON. I fixed the script and re-checked those values independently. They are correct.

## 5. Final relaunch

`stop.sh` → both the server and the bundled engine stopped, nothing left listening. Then `open ~/Desktop/AudienceOS.app` → health OK, version 1.1.0, local model available, the demo data is intact, and the dashboard shows the next actions.

Afterwards the data was reset to an empty database. Load demo → 2 file folders created; Remove demo → 0 left; 8 top-level pages checked in an empty state with 0 console errors.

## 6. Network and secrets

- `lsof -iTCP -sTCP:LISTEN` during testing: `127.0.0.1:8760` (app), `127.0.0.1:8761` (scratch server), `127.0.0.1:11434` (Ollama) and Ollama's runner on another `127.0.0.1` port. After the final relaunch: only `127.0.0.1:8760` and `127.0.0.1:11434`. **No listener on any non-localhost address at any point.**
- Logs (`data/logs/*`, scratch server output) grepped for `sk-ant-…`, `sk-…` and `AIza…` patterns: **0 matches.** No real keys are configured on this Mac. The automated key-leak test uses a fake key with the in-memory store.

## 7. Not tested live, and why

- **External AI (Anthropic/OpenAI):** no paid API usage, by rule. Tested for refusal without a key and without consent.
- **YouTube, Brave and Podcasts with keys or internet transcription:** no keys configured. URL detection, the offline refusal and the Instagram "unsupported" path are tested.
- **Vision frame analysis:** no vision model installed. Frames are stored and shown as "not analyzed".
