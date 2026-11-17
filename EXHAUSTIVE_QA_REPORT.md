# Exhaustive QA report — AudienceOS 1.5.2 (pass 3, 2026-11-17)

This pass checked **completeness of paths and sequences**, on top of the code audit (`FINAL_READINESS_REPORT.md`) and the live UI pass (`LIVE_QA_REPORT.md`), which were not redone. Every number below comes from the generator's own output (`qa/mbt/out/summary.json`, written by `mbt.py summary` from the per-run files). It does not claim "every sequence": the criteria actually met are listed one by one.

## How it was run

- **The real app**, started by `qa/mbt/serve.py` on a scratch data folder and its own port (never 8760, never `~/AudienceOS/data`; the live app stayed stopped). Inside that server process:
  - an httpx firewall refuses every host except 127.0.0.1;
  - DNS lookups are stubbed, so no name lookup leaves the Mac;
  - link fetches return canned pages;
  - checkout syncs answer from a local mock.
  The firewall counted the external-AI attempts it blocked; nothing reached the internet. The Keychain was off (`AUDIENCEOS_NO_KEYCHAIN=1`) and no payment, posting or paid API call was made.
- **AI engine:** most runs used `qa/mbt/fake_ollama.py`, a stand-in that answers from the JSON schema the app sends. It can be switched to invalid, garbage, slow or failing answers. **One seed ran the real bundled `qwen2.5:7b`** on its own port: 60 steps, 2 real analyses (42 s and 375 s), 3 opportunities, 0 failures.
- **UI:** `qa/mbt/ui_walk.js` drives Chrome with `--headless=new` only, using real mouse clicks at each control's position and real typing. Nothing appeared on screen.
- **One command, with a seed:** `backend/.venv/bin/python qa/mbt/mbt.py all --seed 1` (other modes are listed in `TESTING.md`, session 8).

## The model (`qa/model.json`, written by `mbt.py model`)

| Part | Size |
|---|---|
| Screens / controls (from `qa/inventory.json`) | 18 / 209 |
| API routes (read from the routers) | 95 |
| Entity state machines | 6 machines, 25 states, 63 actions, 266 (state, action) transitions; 62 are expected refusals |
| Settings factors for pairwise | 7 factors: provider × external AI × keys × engine up/down/garbage × web retrieval × embeddings × data state |
| Session and environment actions | back, forward, reload, second tab, close/reopen, server restart (clean and kill), slow network, offline, engine down/up/garbage, Escape, Tab+Enter, rapid triple click, plus 27 data/env actions |

| Machine | States | Actions | Transitions (state × action) | Expected refusals |
|---|---|---|---|---|
| Product (draft → approved → launched → paused → retired → reopen) | 5 | 17 | 85 | 25 |
| Opportunity (proposed/approved/testing/validated/rejected) | 5 | 9 | 45 | 0 static (reject with a product is a guarded refusal) |
| Experiment + decision | 4 | 11 | 44 | 16 |
| Asset (draft flagged / draft clean / approved / deleted) | 4 | 8 | 32 | 8 |
| Deal + payouts + creator contact | 2 | 10 | 20 | 10 |
| Analysis job (idle/active/done/failed/cancelled; engine up/down) | 5 | 8 | 40 | 3 |

## Invariants checked after every step

- **Money oracle.** A separate model computes every statement line in exact decimals from the sales, costs and payouts the server accepted, and it must equal the server. It checks:
  - creator + agency = split base, on each line and in the totals;
  - balance = entitlement − paid;
  - entitlement = earned + guarantee top-up;
  - top-up = max(0, guarantee × completed months − earned), with the months counted independently;
  - carry-forward = the cumulative loss;
  - the period filter never changes the balance;
  - no impossible negatives;
  - every stored amount is whole cents.
- **Outputs (every 10th step and at the end):** screen data = statement CSV totals and balance = PDF balance and total = portal balance = payout-file row (non-demo, balance > 0) = creators list. The dashboard's amount owed = Σ max(0, balance) over non-demo creators. Dashboard orders and net sales = the sum over products.
- **Counts agree across screens** (opportunities per audience, dashboard counts). There are no orphan rows (`PRAGMA foreign_key_check` plus explicit checks on money tables) and never more than one active deal per creator.
- **A refused action changes nothing:** a hash of every table is compared before and after, once background jobs are quiet. The state is unchanged too.
- **Nothing is lost after a server restart** (clean or killed) and no job is left stuck: no queued/running job, analysis, AI-call row or waiting source remains.
- **No 5xx.** Double submit creates one record; the same paste twice creates one source; a second Analyze click returns the same job; a cancelled job stays cancelled.
- **UI:** no page errors, no uncaught exceptions, no 5xx and no console errors (other than the browser's own line for a refused 4xx call). Money on screen equals the API (creator balance, product net sales, dashboard owed). Reloading leaves the screen the same.

## Coverage achieved, per criterion

| Criterion | Result |
|---|---|
| **(a) All transitions:** every action from every state, refusals included | Product 85/85 · Opportunity 45/45 · Experiment 44/44 · Asset 32/32 · Deal 20/20 · Analysis job 40/40 = **266/266**. Expected refusals tried directly through the API: **62/62** |
| **(b) Transition pairs** (2-switch: from state s, action a1, then a2 on the same entity) | Product 1445/1445 · Opportunity 405/405 · Experiment 363/363 · Asset 192/192 · Deal 200/200 = **2605/2605 for the core entities**. Analysis job: 41/320, not claimed (see limits) |
| **(c) Pairwise settings and data states** | 17 rows cover **137/137** value pairs of the 7 factors |
| **(d) Lifecycle paths** (every path up to 5 moves, each state entered at most twice, so reversals like retire → reopen → approve are included; opportunity up to 3 moves) | **978 action paths run** (product 58, experiment 343, asset 508, opportunity 68, deal 1). Distinct state paths covered: product 42/42, opportunity 68/68, experiment 63/63, deal 1/1, asset 122/126 (the 4 missing can't happen; see limits) |
| API routes | **95/95** routes called at least once |
| UI controls | Sweep: every control on 22 screens, from a fresh load each, **332 controls, 0 problems**. Random UI walks: 3 seeds × 300 steps, 0 hard problems. Of the 200 enabled inventory controls, **193/200** were used |
| Input fuzzing | **2407 requests:** every body field of 29 write endpoints × 25 values (empty, huge, RTL/emoji, injection, wrong types, NaN/Infinity, 1e308, 2^63, −0.0), 11 hostile paths and queries, 7 malformed CSVs × 2 importers, 6 hostile uploads, and a CSV formula-injection export check. **0 failures after the fixes** |
| Jobs and engine | Cancel, retry, engine down, engine killed mid-run, garbage/invalid/error/mixed answers, server killed mid-run (resumed, attempt 2), double analyze, model download through the stand-in engine |

**Seeds and steps:**
- 56 generator runs (all passing in their final run): 29,245 model steps, 201,435 HTTP calls and 26,970 full invariant checks.
- Random API sequences: **40 seeds × 400 steps** (15,997 steps), plus 1 real-model seed of 60 steps.
- UI: 1 full sweep plus 3 random walks (1,300 browser steps).
- **The last 10 consecutive fresh seeds (31–40) ran clean** after the last fix.

## Bugs found and fixed

P1 = wrong money or data broken with no warning · P2 = a broken path or a security weakness · P3 = friction.

| ID | Sev | Minimal sequence | Root cause → fix | Regression |
|---|---|---|---|---|
| M-10 | **P1** | 30% net-sales deal; orders $19 (fee $0.85), $120.50, $120.50 → creator share **$77.74**. Half-up says **$77.75** | Share taken from a float sum (259.14999…). Now computed in exact decimals from the cent-rounded base (`agency.share`). Found by random seed 7 | `test_creator_share_is_exact_half_up_on_the_cent` (fails without the fix) |
| M-01 | **P1** | Add a $0.015 sale → statement gross $0.01, while the shares used 0.015 | Amounts were stored as typed or imported. Every money input (sale, refund, fee, cost, payout, CSV import) is now whole cents, half-up | `test_money_is_stored_in_whole_cents` |
| M-02 | **P1** | POST a sale/price/cost/guarantee/payout of `Infinity`, `1e999` or `1e308` (or an int above 2^63) → stored → that product/experiment/deal page **and the dashboard answer 500 from then on** | No finite or range check; the 422 itself echoed `inf` and crashed. Every request body now refuses non-finite and out-of-range numbers (`app/apimodel.py`), 422s no longer echo the input, and a CSV "inf" is not a number | `test_non_finite_and_huge_numbers_are_refused_everywhere` |
| M-03 | P2 | Experiment result: 1 visit, 5 purchases → experiment page, list and dashboard 500 | Wilson interval took the sqrt of a negative. Now no interval, plus a note to check the numbers | `test_more_purchases_than_visits_does_not_break_the_experiment` |
| M-04 | P2 | Opportunity → create product → Reject (API), or experiment **Stop** (UI) → a live product under a "rejected" idea, which Restore sent back to "proposed" | The UI hid Reject; the API and the Stop decision didn't. Reject is refused (409, "Retire the product instead") and Stop no longer rejects an idea with a product | `test_opportunity_with_a_product_is_not_rejected` |
| M-11 | P2 | Rename creator B to creator A's name → two creators with one name → "Add creator A" attaches to whichever came first. Non-English letters never matched (SQLite `lower()`) | Rename to a taken name is refused (409); matching is case-insensitive for all letters. Found by random seed 24 | `test_creator_names_stay_unique` |
| M-09 | P2 (security) | Creator or product named `=HYPERLINK(...)`/`+SUM(...)`, or an audience quote starting with `=` → written raw into the statement, payout and report CSVs | Formula cells now get a leading apostrophe; numbers like -5.00 are untouched (`app/csvsafe.py`) | `test_csv_exports_neutralise_formulas` |
| M-06 | P2 | `PUT /settings {"ai_provider": "bogus"}` → dashboard and "Draft asset" 500 | Any text was accepted. The provider, theme and Whisper model are now checked against their fixed choices | `test_settings_with_fixed_choices_refuse_other_values` |
| M-07 | P3 | Add a competitor with `https://aaaa…` (over 63 characters), a hidden RTL character or `:abc` port → 500; URL imports failed with a raw error | `UnicodeError`/`ValueError` inside the safety check. Now "That link isn't a valid web address." | `test_malformed_links_are_refused_in_plain_words` |
| M-08 | P3 | Import a CSV with a 2 MB cell → 500 | `csv.Error` not caught. Now "This CSV can't be read… Export it again as CSV UTF-8." | `test_csv_with_a_huge_cell_is_refused_plainly` |
| M-05 | P3 | `PATCH audience {"status": "deleted"}` → 500; `PATCH product/experiment {"name": null}` → 500 | Database CHECK/NOT NULL reached. Status is validated and an explicit null is ignored | `test_invalid_status_and_null_names_are_refused_or_ignored` |

**How the minimal sequences were found:**
- Each P1/P2 row is the smallest reproduction: fuzz findings are single requests; seeds 7 and 24 were cut down by hand to the orders or steps shown.
- The automatic shrinker (ddmin over one entity's actions, on a fresh server per replay) at first couldn't replay those two seeds, because the action values came from the walk's random generator. Values are now keyed by (seed, machine, action, occurrence), so future failures replay and shrink to `qa/mbt/regressions/`.
- Every run listed above passes in its final run, so no regression file is pending.

**Not app defects (fixed in the harness):** parallel runs racing for a port; keys lost on restart (memory keystore in test mode only); the walk deleting the demo's comments (the app then correctly skips product ideas); one server lost during the Mac's sleep. The affected runs (seeds 5, 24, 25, 28, 29, the opportunity pairs and UI seed 3) were re-run clean.

## UX fixes (expert review of the paths)

- **Unsaved edits are no longer lost when leaving.** The product setup and deal forms ask before a sidebar or breadcrumb link, and before closing or reloading the tab. Cancel keeps the edits (`e2e/13_leave_guard.js`, 5/5). Browser Back is not guarded.
- **No dead-end retry.** A page for something deleted, or an old link, showed "Not found" with a **Try again** that could never work; it now offers "Go to the dashboard".
- **Consistent rules for rejecting an opportunity.** The page, the API and the Stop decision now agree, and the Stop help text says so.
- **Reviewed and left as is:**
  - the expanded/collapsed state of problems on Intelligence resets on reload (2 soft notes from the reload check; view state, not data);
  - "Save weights" with a typed invalid weight is refused with a message (an action offered that fails, but it explains why);
  - Restore always returns to Proposed (it already says so when you Reject).

## What can't be covered exhaustively, and why

- **"Every sequence" is infinite.** What is met is: all transitions (266/266), all transition pairs for the core entities (2605/2605), all lifecycle paths up to 5 moves (3 for opportunities), all pairwise settings combinations (137/137), and 40 random seeds of 400 steps. Longer interleavings across entities are sampled, not enumerated.
- **Analysis-job pairs: 41/320 only.** Job states depend on timing (a run takes about 1 s with the stand-in, 7 min with the real model). Each pair would need a timed setup, so they were covered by scenario instead: cancel, retry, engine killed, server killed, garbage answers.
- **4 asset paths are impossible:** unapproving returns to the flag state the content already had.
- **Real external systems** were exercised only against local stubs, by rule: Stripe, Gumroad, Shopify and Lemon Squeezy syncs; Anthropic and OpenAI (attempts were blocked by the firewall, and the job then fails in plain words); link fetches; DNS; the Keychain; downloading a model from the internet.
- **7 of the 200 inventory controls weren't reached:**
  - one exists only while an analysis is running;
  - four are intelligence links named after real-model cluster titles (the stand-in names clusters differently);
  - the demo row of the creators table is labelled differently in the current data;
  - the file drop zone opens the OS file chooser, which headless runs skip. It was covered by keyboard and file-chooser uploads in pass 2.
- **Not covered:** real-model quality, Windows/Linux, screen-reader speech, and many users at once (the app is single-operator).

## Product questions left open (warnings kept)

- Should orders dated outside the deal term count?
- Should changed terms apply only to later sales?

The statement warnings still say both. Nothing was decided here.

## Readiness

**Ready for the 3 supervised creator pilots, with more confidence than after pass 2.** Every modelled action in every state, every pair of actions on the core entities and every short lifecycle path now behaves as the model says, and the money matches an independent decimal oracle across 16,000+ random steps. The serious finds were money rounding by a cent, fractional cents, and one bad number permanently breaking a record. All are fixed with regression tests.

**Still not ready for unsupervised public use,** for the same reasons as before:
- real checkout and external-AI accounts are untested;
- there's a single background worker;
- there are no accounts or hosting;
- the two contract questions above are open.

**Evidence:** pytest **134 passed** three times in a row (`AUDIENCEOS_OLLAMA_URL=http://127.0.0.1:9`); `npm run build` clean. Branch `exhaustive/2026-11-17`, not pushed.
