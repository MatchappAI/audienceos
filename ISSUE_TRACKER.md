# Issue tracker — audit 2026-11-16 (v1.5.0)

Priority: **P0** security/data loss · **P1** major defect / broken core rule · **P2** friction, robustness, a11y, perf · **P3** polish.
Status: **Verified fixed** (reproduced, fixed, regression test or e2e re-run passes) · **Implemented, not verified live** · **Still open** · **Blocked** (credentials/environment) · **Needs product decision**.

Tests named below live in `backend/tests/test_audit_2026_11_16.py` (money, gate, API) and `backend/tests/test_audit_ingest_security.py` (ingest, fetch, AI, settings, jobs), unless stated otherwise.

## Found and fixed

| ID | P | Area | Problem (plain words) | Fix | Evidence | Status |
|---|---|---|---|---|---|---|
| A-01 | P1 | Launch gate | A draft product could skip approval through the API: set it to *paused*, then "resume" it to *launched*. | Only a launched product can be paused. Launch needs a recorded approval. | `test_draft_cannot_skip_approval_via_pause` | Verified fixed |
| A-02 | P2 | Launch gate | Approving a product that was already live quietly moved it back to *approved*. | Only drafts can be approved. | `test_pause_resume_keeps_approval_and_draft_withdraws_it` | Verified fixed |
| A-03 | P2 | Product page | A retired product showed "Approved by **undefined**" and had no way back. | The page now explains the retired state, and **Reopen as draft** starts a fresh approval. Retiring asks for confirmation. | `test_retired_product_must_be_reopened_and_reapproved`, UI sweep | Verified fixed |
| A-04 | P2 | Assets | "Tick the flagged-claims box before approving" was only enforced in the UI. | The API refuses to approve a flagged draft unless `flags_checked` is sent. | `test_flagged_asset_needs_confirmation_to_approve`, e2e step "asset approved" | Verified fixed |
| A-05 | P2 | Money | Dashboard **Owed to creators** subtracted an overpaid creator's negative balance from what others were owed. | Only positive balances are counted. | `test_owed_total_ignores_overpaid_creators` | Verified fixed |
| A-06 | P2 | Money | Orders with no date silently dropped out of any dated statement period. | The statement now warns how many orders are left out and why. | `test_statement_warns_about_undated_out_of_term_and_changed_terms` | Verified fixed |
| A-07 | P2 | Money | Orders dated outside the deal's start/end were counted with no notice. | Warning on the statement. Whether to exclude them is a contract question. | same test | Verified fixed (warning) · Needs product decision |
| A-08 | P2 | Money | Changing the deal terms (e.g. 70% → 60%) silently recalculated every past sale and the balance. | Warning when the terms changed. Re-saving the same terms (e.g. a notes edit) doesn't trigger it. | same test | Verified fixed (warning) · Needs product decision |
| A-09 | P3 | Money | The statement's "Back to draft" badge used old logic, so it disagreed with the product page. | Each statement line now carries `back_to_draft`. | `test_statement_line_back_to_draft_flag` | Verified fixed |
| A-10 | P3 | Creators | The contact email (which the payout file needs) wasn't checked. Save errors showed up in the payouts card. | Email is validated, and errors show next to the contact form. | `test_creator_email_validated` | Verified fixed |
| A-11 | P3 | Experiments | Experiment start/end dates accepted any text, which breaks the "experiment has ended" reminder. | Dates must be YYYY-MM-DD. | `test_experiment_dates_must_be_iso` | Verified fixed |
| A-12 | P2 | Audiences | A partial channel update wiped the fields it didn't send. | The PATCH only changes what is sent. | `test_channel_patch_keeps_unsent_fields` | Verified fixed |
| A-13 | P2 | Jobs | Two quick clicks (or two tabs) could start two analyses of the same audience. | Check-then-start runs under a lock. | `test_concurrent_analyze_starts_one_job` (6 threads → 1 job); e2e second start returned the same job | Verified fixed |
| A-14 | P3 | Security | File-serving path checks compared text prefixes, so a sibling folder like `dist-x` would pass. | Uses `is_relative_to`. | Code review + suite | Verified fixed |
| A-15 | P2 | Money UX | Orders and costs were deleted in one click with no confirmation. A mistyped payout bigger than the balance went through silently. | Confirmation before deleting. A payout above the balance asks first (an advance is still allowed). | UI code + e2e | Verified fixed |
| A-16 | P1 | Data loss | **Reprocessing a source deleted the evidence behind finished analyses**: quotes, signals and opportunity links were gone, with no warning. Restarting with an import job running did the same. | Migration 005: evidence survives (pointer set to NULL), then the job re-links each quote to the re-imported comment or item. | `test_reprocess_keeps_evidence_of_finished_analysis`; migration applied to the scratch DB (33/33/22 rows kept, FK check clean) and to a copy of the live DB | Verified fixed |
| A-17 | P1 | Security | DNS rebinding: a hostile domain could pass the public-IP check and then connect to 127.0.0.1/LAN. | The address actually connected to is checked before any body is read. | `test_dns_rebinding_is_refused` (the reviewer's repro now raises `private_address`) | Verified fixed |
| A-18 | P1 | Reliability | Describing video frames with the vision model held the database write lock. Any other save could fail with "database is locked". | Commit before each model call. | Reviewer's repro: an unrelated write went from 7.4 s to 0.0 s | Verified fixed |
| A-19 | P2 | Import | CSV/JSON imports lost data: Excel/YouTube BOM headers, single-column files with commas cut short, extra cells dropped, fields over 128 KB crashed, JSON with a BOM refused. | Read BOM-aware. Single-column mode. Extra cells kept. Larger field limit. | `test_csv_single_column_bom_and_long_fields`, `test_json_with_bom_imports`; unicode CSV via the API on the scratch server | Verified fixed |
| A-20 | P2 | Privacy | Settings had no type check. Sending the string `"false"` actually **turned external AI on**. A bad rubric broke scoring. | Each setting keeps its default's type, and consent requires a real `true`. | `test_settings_types_enforced` | Verified fixed |
| A-21 | P2 | Secrets | httpx wrote full request URLs, including the YouTube API key, into `data/logs`. | httpx/httpcore are logged at WARNING only. | `test_httpx_request_urls_not_logged` | Verified fixed |
| A-22 | P2 | AI safety | A comment containing `</source_material>` could close the "untrusted material" wrapper early in prompts. | Wrapper look-alikes in untrusted text are defanged, both centrally and in unit formatting. | `test_untrusted_text_cannot_close_prompt_wrappers`; injection paste analysed as data on the scratch server | Verified fixed |
| A-23 | P2 | Reliability | No overall download deadline: a server sending 1 byte per second could hold the single worker for hours. | A whole-download deadline (60 s, or longer for big media). | Code; reviewer's slow-server repro | Implemented, not verified live |
| A-24 | P2 | Security | A 751 KB .docx expanded to 300 M characters (647 MB of memory). | Unpacked size and ratio are checked before opening. | `test_docx_decompression_bomb_refused` | Verified fixed |
| A-25 | P3 | Jobs | A cancelled job could be overwritten to *failed* or re-queued. A cancelled import left its source on "Waiting" forever. | Cancelled stays cancelled. The source is marked failed with "reprocess to try again". | `test_cancelled_job_stays_cancelled`, `test_cancelled_ingest_does_not_leave_source_waiting` | Verified fixed |
| A-26 | P3 | Assets | Calculator formulas allowed `//` and `/*` and reserved input names like `new`, giving a broken calculator. | Those are rejected or renamed. | `test_calculator_rejects_comments_and_reserved_words` | Verified fixed |
| A-27 | P3 | AI | `Infinity` in model output passed numeric checks and then broke JSON responses. | AI schemas reject inf/NaN. | `test_ai_schemas_reject_infinity` | Verified fixed |
| A-28 | P2 | Secrets | API headers (the Brave key) were forwarded on a cross-host redirect. | Custom headers are dropped when the host changes. | Code review | Implemented, not verified live |
| A-29 | P2 | Money | Checkout sync stopped at 50 pages with no notice. Lemon Squeezy reads every store order, so big stores lost sales silently. | Truncation warning on the sync result. | `test_sync_warns_when_page_limit_truncates` | Verified fixed |
| A-30 | P1 | Privacy | When an external AI was the active provider, **importing a video sent its frames to that provider with no per-run consent**. | Imports only ever use the local vision model. | `test_frames_never_go_to_external_ai_during_import` | Verified fixed |
| A-31 | P3 | Web | A robots.txt server error was treated as "allowed". | Treated as "don't crawl for now" (RFC 9309), and not cached. | Code | Implemented, not verified live |
| A-32 | P3 | Web | A malformed Content-Length crashed the fetch. | Ignored safely. | Code | Implemented, not verified live |
| A-33 | P3 | API | Unknown `/api/...` paths returned the app's HTML page with status 200. | JSON 404. | `test_unknown_api_path_is_json_404` | Verified fixed |
| A-34 | P2 | A11y | Light theme: faint hint text was 3.0:1 contrast and warning text on yellow was 4.4:1 (WCAG AA needs 4.5:1). | `--faint` #6e6e73 (≥4.6:1), `--warn` #875a00 (5.5:1). | Computed ratios | Verified fixed |
| A-35 | P3 | Layout | At phone width the statement header (title + date filters) was cramped. | Card headers wrap. | Narrow screenshots | Verified fixed |
| A-36 | P3 | Experiments | **Save design** silently deleted success criteria that didn't have a threshold yet. | They're kept and keep showing "set a threshold". | Headless UI check: 3rd criterion saved with blank value, badge shown | Verified fixed |
| B-01..06 | P2–P3 | Money (2026-11-08 pass, finished here) | Non-ISO money dates silently fell out of statements. Refund could exceed sale. Deal end before start. Raw `net_sales` wording in the CSV. A never-approved draft with orders was shown as "back to draft". Sidebar crushed narrow windows. | Validated server-side, with plain wording and an icon rail. | 4 tests in `test_money.py`; route sweep at 390 px | Verified fixed |

## Still open

| ID | P | Problem | Why open / next step | Status |
|---|---|---|---|---|
| O-01 | P3 | UTF-16 CSVs ("Unicode text" from Excel) are refused as unsupported. | The NUL-byte safety sniff rejects them. Workaround: save as CSV UTF-8. Next: detect a UTF-16 BOM before sniffing. | Still open |
| O-02 | P3 | Deleting a source while its video is still being sampled can leave an orphan frames folder. | Cosmetic, disk only. The job ends "failed". | Still open |
| O-03 | P3 | An approved asset can quote a different price than the product. | Shown as a warning on Launch approval, by design (a human decides). Could become a required tick. | Needs product decision |
| O-04 | — | Stripe, Gumroad, Shopify and Lemon Squeezy order sync against real accounts. | No keys on this Mac. Tested against mocked APIs only. | Blocked (credentials) |
| O-05 | — | External AI (Anthropic/OpenAI), YouTube Data API, Brave search. | No paid or keyed calls, by rule. Refusal paths are tested. | Blocked (credentials) |
| O-06 | — | YouTube OAuth, Meta and TikTok business APIs. | Need developer apps you register and the platforms review. | Blocked (app registration) |
| O-07 | P2 | Deal terms are not dated history: one active deal applies to all time. | A-07 and A-08 now warn. Real fix: per-period deals, which depends on how contracts are written. | Needs product decision |
