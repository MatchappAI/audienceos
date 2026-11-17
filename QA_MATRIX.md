# QA matrix (2026-11-16, v1.5.0)

Feature → journey → action → expected → method → actual → status. **Pass** means the outcome was checked through the stack, not just that the request returned. Methods: **U** = unit/API test in `backend/tests` · **E** = headless Chrome e2e on the scratch server (`e2e/`) · **A** = API script on the scratch server (`e2e/4_edge_cases.py`) · **S** = route sweep (`e2e/3_route_sweep.js`) · **R** = code review only.

| Feature | Journey | Action | Expected | Method | Actual | Status |
|---|---|---|---|---|---|---|
| Demo | J1 | Load demo project | 4 sources ready, then the Sources tab | E | Ready in 5–9 s | Pass |
| Analysis | J1 | Run analysis (qwen2.5:7b) | Signals, problems, opportunities | E | 33 · 5 · 3 in 10 min 40 s | Pass |
| Analysis | J1 | Second start / two tabs | Same job, no duplicate | U, E | 6 threads → 1 job | Pass |
| Analysis | J1 | Refresh mid-run | Progress still shown | E | Stage and % shown | Pass |
| Analysis | J1 | Restart server mid-run | Resumes | E | Attempt 2 continued | Pass |
| Analysis | J1 | Engine down | Clear message, no job | A | "Local AI engine (Ollama) is not running…" | Pass |
| Analysis | J1 | Thin material (5 signals) | Finishes with a reason, no product ideas | U (+ live finding) | Skipped with "Product ideas were not generated…" | Pass |
| Analysis | J1 | Cancel | Job and analysis closed | U | Analysis → failed "Cancelled" | Pass |
| Analysis | J1 | Stage label during stage 6 | Shows stage 6 | U | Fixed (was stuck on "Stage 4") | Pass |
| Import | J1 | exe renamed .csv | Refused | A | "Unsupported or unsafe file type" | Pass |
| Import | J1 | Empty file | Refused | A | "File is empty." | Pass |
| Import | J1 | `../../../etc/passwd.txt` name | Sanitized, stored under uploads/<audience> | A | `src_…_passwd.txt` | Pass |
| Import | J1 | Duplicate file / paste | Detected | A | `duplicate: true` | Pass |
| Import | J1 | Unicode CSV (Japanese, accents, em dash) | 2 comments, text intact | A | Intact | Pass |
| Import | J1 | 2 MB paste / over-limit paste | Accepted / 422 | A | As expected | Pass |
| Import | J1 | BOM CSV, single-column with commas, 200 KB field, extra cells, BOM JSON | Imported correctly | U | All pass | Pass |
| Import | J1 | DOCX decompression bomb | Refused | U | Refused | Pass |
| Import | J1 | UTF-16 CSV | Imported | R | Refused as unsupported | Fail (O-01, P3) |
| Import | J1 | Reprocess after analysis | Evidence kept | U | Kept and re-linked | Pass |
| Evidence | J2 | Click quote | Drawer with verbatim quote and source | E | Opens; Esc closes | Pass |
| Opportunity | J3 | Recalculate, approve | Status approved | E | Approved | Pass |
| Experiment | J3 | Thresholds, Save design | Criteria stored | E | `[2%, 10]` | Pass |
| Experiment | J3 | Import results + orders, re-import | Idempotent | E | "skipped 5 already imported" | Pass |
| Experiment | J3 | Go | Opportunity validated, override labelled | E | Validated | Pass |
| Experiment | J3 | Non-ISO dates | 422 | U | 422 | Pass |
| Asset | J4 | Draft landing page | Draft + claim review | E | 77 s, flags shown | Pass |
| Asset | J4 | Approve without tick (API) | 400 | U | 400 | Pass |
| Asset | J4 | Export md/html/docx, preview CSP | Files; `default-src 'none'` | E | 1.6/3.6/37 KB; CSP ok | Pass |
| Product | J5 | Setup → 5 checks → approve → launch | Launched | E | Launched | Pass |
| Product | J5 | Draft → paused → launch (API) | Refused | U | 400 | Pass |
| Product | J5 | Retire → reopen → approve | Works; launch blocked while retired | U | As expected | Pass |
| Product | J5 | Price change after launch | Back to draft, sales kept | U | As expected | Pass |
| Sales | J5 | Orders CSV (5, 1 refund) | Net $156, fees $7.15 | E | Matches | Pass |
| Sales | J5 | Negative / duplicate / refund > sale / bad date | 422 / 409 / 422 / skipped with reason | A, U | As expected | Pass |
| Sales | J5 | 20,000-order CSV, re-import | Imported in < 2 s; 0 on re-import | A | 0.6 s; 0 | Pass |
| Costs | J5 | Add $12 shared | Split base −$12 | E | $136.85 | Pass |
| Deal | J6 | Save 70/30 contribution | Creator = round_half_up(base × 0.7) | E | $95.80 (95.795) | Pass |
| Deal | J6 | Loss carry-forward, minimum guarantee | Per definitions | U | Pass | Pass |
| Deal | J6 | Share > 100, end < start | 422 | A, U | 422 | Pass |
| Statement | J6 | Undated / out-of-term / changed terms | Warnings | U | Shown | Pass |
| Payout | J6 | Record $10 | Balance $85.80 | E | $85.80 | Pass |
| Payout | J6 | Zero / non-ISO / blank date | 422 | A, U | 422 | Pass |
| Statement | J6 | CSV, PDF, portal agree | Same balance; portal has no scripts, strict CSP | E | Agree | Pass |
| Dashboard | J6 | Overpaid creator | Not subtracted from owed total | U | Pass | Pass |
| Reports | J7 | Generate | 5 files served | E | 200 × 5 | Pass |
| Library | J7 | Search "starter" | Results | E | Results | Pass |
| Settings | J8 | `"false"` string for external AI | Refused; still off | U | 400; off | Pass |
| Settings | J8 | Saved key never returned or logged | Absent | U | Absent | Pass |
| Sync | J9 | Stripe/Gumroad/Shopify/Lemon (mocked) | Idempotent; refunds/fees; warnings | U | Pass | Pass (mock-only) |
| Sync | J9 | Real accounts | Orders appear | — | — | Blocked (no keys) |
| Security | — | No CSRF header / foreign Host | 403 | A | 403 / 403 | Pass |
| Security | — | DNS rebinding to 127.0.0.1 | Refused | U | `private_address` | Pass |
| Security | — | SPA / report path traversal | No file outside dist/reports | A | Blocked | Pass |
| Security | — | Prompt-wrapper breakout | Defanged | U, A | Pass | Pass |
| Security | — | Video frames with external provider active | Not sent | U | `vision_provider()` is None | Pass |
| Security | — | Listening sockets | 127.0.0.1 only | R (`lsof`) | 8761 and 11435 on 127.0.0.1 only | Pass |
| A11y | — | Buttons/links have names; inputs have labels | 0 missing | S | 0 across 27 routes × 4 | Pass |
| A11y | — | Small-text contrast ≥ 4.5:1 | AA | R (computed) | faint 4.6–5.1, warn 5.5 | Pass |
| A11y | — | Escape closes drawers/modals; focus outline | Yes | E, R | Yes | Pass |
| Layout | — | 1440 px and 390 px, light/dark | No horizontal scroll, no blank pages | S | 0 issues (missing-ID pages show "not found") | Pass |
| Errors | — | Missing product/opportunity/creator | Message + Try again, not blank | S | ErrorBox shown | Pass |
| Errors | — | Unknown /api path | JSON 404 | U | 404 | Pass |
| Perf | — | Page load | < 1.5 s | S | Median 0.77 s, max 1.06 s | Pass |
| Perf | — | Statement/dashboard with 20k orders | < 1 s | A | 0.10 s / 0.13 s | Pass |

**Not run:** real external providers (keys, paid), a vision-model description during this session (verified in session 5), whisper `small`, Windows/Linux, multi-user (not a feature).
