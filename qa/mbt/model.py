"""The AudienceOS state-machine model used by the generator (and written out as qa/model.json).

Each machine lists its states, actions and, for every (state, action), what must happen: the next state, or
"REFUSE" (the server must answer 4xx and change nothing). Guards that depend on data (e.g. "has a checkout link",
"its assets are approved") are named in `guards`; the generator evaluates them on the live entity.
"""
REFUSE = "REFUSE"

PRODUCT_STATES = ["draft", "approved", "launched", "paused", "retired"]
PRODUCT = {
    "states": PRODUCT_STATES, "initial": "draft", "terminal": [],
    "actions": {
        "approve":            {"draft": "approved?assets_ok", "approved": REFUSE, "launched": REFUSE, "paused": REFUSE, "retired": REFUSE},
        "approve_incomplete": {s: REFUSE for s in PRODUCT_STATES},
        "launch":             {"draft": REFUSE, "approved": "launched", "launched": REFUSE, "paused": "launched", "retired": REFUSE},
        "pause":              {"draft": REFUSE, "approved": REFUSE, "launched": "paused", "paused": "paused", "retired": REFUSE},
        "retire":             {s: "retired" for s in PRODUCT_STATES},
        "reopen":             {s: "draft" for s in PRODUCT_STATES},
        "edit_price":         {"draft": "draft", "approved": "draft", "launched": "draft", "paused": "draft", "retired": "retired"},
        "edit_notes":         {s: s for s in PRODUCT_STATES},
        "add_sale":           {s: s for s in PRODUCT_STATES},
        "add_sale_dup":       {s: REFUSE for s in PRODUCT_STATES},
        "add_sale_bad_refund": {s: REFUSE for s in PRODUCT_STATES},
        "add_sale_fraction_cents": {s: s for s in PRODUCT_STATES},
        "import_csv":         {s: s for s in PRODUCT_STATES},
        "del_sale":           {s: s for s in PRODUCT_STATES},
        "add_cost":           {s: s for s in PRODUCT_STATES},
        "del_cost":           {s: s for s in PRODUCT_STATES},
        "sync":               {s: "s?key" for s in PRODUCT_STATES},
    },
    "guards": {"assets_ok": "every asset of its opportunity is approved and it has an https checkout link (else REFUSE)",
               "key": "a Stripe key is saved (else REFUSE: 'Add your Stripe key in Settings first')"},
}

OPP_STATES = ["proposed", "approved", "testing", "validated", "rejected"]
OPPORTUNITY = {
    "states": OPP_STATES, "initial": "proposed", "terminal": [],
    "actions": {
        "approve":        {s: "approved" for s in OPP_STATES},
        "reject":         {**{s: "rejected?no_product" for s in OPP_STATES}, "rejected": "rejected"},
        "restore":        {s: "proposed" for s in OPP_STATES},
        "mark_validated": {s: "validated" for s in OPP_STATES},
        "create_experiment": {"proposed": "testing", "approved": "testing", "testing": "testing", "validated": "validated", "rejected": "rejected"},
        "create_product": {s: s for s in OPP_STATES},
        "rescore":        {s: s for s in OPP_STATES},
        "scenario":       {s: s for s in OPP_STATES},
        "add_competitor": {s: s for s in OPP_STATES},
    },
    "guards": {"no_product": "an opportunity that already has a product can't be rejected (the UI hides Reject then); REFUSE"},
}

EXP_STATES = ["draft", "running", "completed", "deleted"]
EXPERIMENT = {
    "states": EXP_STATES, "initial": "draft", "terminal": ["deleted"],
    "actions": {
        "set_running":   {"draft": "running", "running": "running", "completed": "running", "deleted": REFUSE},
        "set_draft":     {"draft": "draft", "running": "draft", "completed": "draft", "deleted": REFUSE},
        "add_event":     {"draft": "draft", "running": "running", "completed": "completed", "deleted": REFUSE},
        "add_event_empty": {s: REFUSE for s in EXP_STATES},
        "import_csv":    {"draft": "draft", "running": "running", "completed": "completed", "deleted": REFUSE},
        "del_event":     {"draft": "draft", "running": "running", "completed": "completed", "deleted": REFUSE},
        "decide_go":     {"draft": "completed", "running": "completed", "completed": "completed", "deleted": REFUSE},
        "decide_revise": {"draft": "completed", "running": "completed", "completed": "completed", "deleted": REFUSE},
        "decide_stop":   {"draft": "completed", "running": "completed", "completed": "completed", "deleted": REFUSE},
        "bad_checkout_link": {s: REFUSE for s in EXP_STATES},
        "delete":        {"draft": "deleted", "running": "deleted", "completed": "deleted", "deleted": "deleted"},
    },
    "guards": {},
}

ASSET_STATES = ["draft_flagged", "draft_clean", "approved", "deleted"]
ASSET = {
    "states": ASSET_STATES, "initial": "draft_*", "terminal": ["deleted"],
    "actions": {
        "approve":           {"draft_flagged": REFUSE, "draft_clean": "approved", "approved": "approved?no_flags", "deleted": REFUSE},
        "approve_confirmed": {"draft_flagged": "approved", "draft_clean": "approved", "approved": "approved", "deleted": REFUSE},
        "unapprove":         {"draft_flagged": "draft_flagged", "draft_clean": "draft_clean", "approved": "draft_*", "deleted": REFUSE},
        "edit_clean":        {"draft_flagged": "draft_clean", "draft_clean": "draft_clean", "approved": "draft_clean", "deleted": REFUSE},
        "edit_claim":        {"draft_flagged": "draft_flagged", "draft_clean": "draft_flagged", "approved": "draft_flagged", "deleted": REFUSE},
        "export":            {"draft_flagged": "draft_flagged", "draft_clean": "draft_clean", "approved": "approved", "deleted": REFUSE},
        "preview":           {"draft_flagged": "draft_flagged", "draft_clean": "draft_clean", "approved": "approved", "deleted": REFUSE},
        "delete":            {"draft_flagged": "deleted", "draft_clean": "deleted", "approved": "deleted", "deleted": "deleted"},
    },
    "guards": {"no_flags": "re-approving an approved draft that has flagged claims needs the reviewer's confirmation again (else REFUSE)"},
}

DEAL_STATES = ["none", "active"]
DEAL = {
    "states": DEAL_STATES, "initial": "none", "terminal": [],
    "actions": {
        "set_deal":        {"none": "active", "active": "active"},
        "set_deal_stale":  {"none": REFUSE, "active": REFUSE},
        "set_deal_bad_dates": {"none": REFUSE, "active": REFUSE},
        "set_deal_bad_pct": {"none": REFUSE, "active": REFUSE},
        "payout":          {"none": "none", "active": "active"},
        "payout_bad":      {"none": REFUSE, "active": REFUSE},
        "del_payout":      {"none": "none", "active": "active"},
        "email_ok":        {"none": "none", "active": "active"},
        "email_bad":       {"none": REFUSE, "active": REFUSE},
        "period_statement": {"none": "none", "active": "active"},
    },
    "guards": {},
}

JOB_STATES = ["idle", "active", "done", "failed", "cancelled"]
ANALYSIS_JOB = {
    "states": JOB_STATES, "initial": "idle", "terminal": [],
    "actions": {
        "analyze":        {"idle": "active?engine", "active": "active", "done": "active?engine", "failed": "active?engine", "cancelled": "active?engine"},
        "cancel":         {"idle": "idle", "active": "cancelled", "done": "done", "failed": "failed", "cancelled": "cancelled"},
        "retry":          {"idle": REFUSE, "active": REFUSE, "done": REFUSE, "failed": "active", "cancelled": "active"},
        "wait":           {"idle": "idle", "active": "done|failed", "done": "done", "failed": "failed", "cancelled": "cancelled"},
        "restart_server": {"idle": "idle", "active": "active|done|failed", "done": "done", "failed": "failed", "cancelled": "cancelled"},
        "engine_down":    {s: s for s in JOB_STATES},
        "engine_up":      {s: s for s in JOB_STATES},
        "engine_garbage": {s: s for s in JOB_STATES},
    },
    "guards": {"engine": "the selected AI engine is reachable (else REFUSE 400 with a plain reason)"},
}

MACHINES = {"product": PRODUCT, "opportunity": OPPORTUNITY, "experiment": EXPERIMENT, "asset": ASSET, "deal": DEAL,
            "analysis_job": ANALYSIS_JOB}

# Settings / environment factors for pairwise coverage.
FACTORS = {
    "provider": ["ollama", "rules", "anthropic", "openai"],
    "allow_external_ai": [False, True],
    "keys": ["absent", "present"],
    "engine": ["up", "down", "garbage"],
    "allow_web_retrieval": [True, False],
    "use_embeddings": [True, False],
    "data": ["empty", "demo", "demo+real"],
}

# Session/environment actions the UI generator mixes in.
SESSION_ACTIONS = ["back", "forward", "reload", "second_tab_mutation", "server_restart", "network_slow", "network_offline",
                   "engine_down", "engine_up", "close_reopen", "rapid_repeat_click", "keyboard_tab_enter", "escape"]


def transitions(machine: dict) -> list[tuple[str, str, str]]:
    out = []
    for a, row in machine["actions"].items():
        for s, nxt in row.items():
            out.append((s, a, nxt))
    return out


def nexts(machine: dict, s: str, a: str) -> list[str]:
    v = machine["actions"][a][s]
    if v == REFUSE:
        return [s]
    v = v.split("?")[0]
    if v == "s":
        return [s]
    if v == "draft_*":
        return ["draft_flagged", "draft_clean"]
    return [x for x in v.split("|") if x in machine["states"]] or [s]


def pair_space(machine: dict) -> set[tuple[str, str, str]]:
    """2-switch coverage items: (s1, a1, a2) = from state s1 do a1, then immediately a2 on the same entity.
    (The state after a1 is determined by the model, except where the model allows several outcomes.)"""
    out = set()
    for s in machine["states"]:
        if s in machine.get("terminal", []):
            continue
        for a1 in machine["actions"]:
            for a2 in machine["actions"]:
                out.add((s, a1, a2))
    return out
