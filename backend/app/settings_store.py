"""App settings (SQLite) and secrets (macOS Keychain). API keys are never logged or returned."""
import json
import logging
import os

from . import config, db

log = logging.getLogger("audienceos.settings")

DEFAULT_RUBRIC = {
    "problem_frequency": {"label": "Problem frequency", "weight": 12, "source": "data"},
    "commercial_intent": {"label": "Commercial intent", "weight": 15, "source": "data"},
    "evidence_quality": {"label": "Evidence quality", "weight": 12, "source": "data"},
    "audience_fit": {"label": "Audience–product fit", "weight": 10, "source": "model"},
    "distribution_fit": {"label": "Distribution fit", "weight": 8, "source": "model"},
    "competition": {"label": "Competitive room", "weight": 7, "source": "model"},
    "delivery_feasibility": {"label": "Delivery feasibility", "weight": 8, "source": "model"},
    "cost_to_produce": {"label": "Low production & support cost", "weight": 7, "source": "model"},
    "margin_potential": {"label": "Gross margin potential", "weight": 8, "source": "model"},
    "recurring_potential": {"label": "Repeat / recurring potential", "weight": 6, "source": "model"},
    "experiment_feasibility": {"label": "Easy to test quickly", "weight": 7, "source": "model"},
}

DEFAULTS = {
    "ai_provider": "ollama",               # ollama | anthropic | openai | rules
    "ollama_model": "qwen2.5:7b",
    "ollama_vision_model": "",
    "anthropic_model": "claude-sonnet-5-5",
    "openai_model": "gpt-5-mini",
    "allow_external_ai": False,            # must be explicitly enabled before data leaves this Mac
    "allow_web_retrieval": True,           # fetching URLs the user enters
    "allow_web_research": False,           # automated competitor search (needs Brave key)
    "whisper_model": "base",
    "rubric": DEFAULT_RUBRIC,
    "theme": "system",
}

SECRET_NAMES = ("anthropic_api_key", "openai_api_key", "youtube_api_key", "brave_api_key",
                "stripe_api_key", "gumroad_access_token")
_mem_secrets: dict[str, str] = {}  # fallback if Keychain is unavailable (e.g. tests)


def get(key: str):
    r = db.one("SELECT value_json FROM settings WHERE key=?", (key,))
    if r is None:
        return DEFAULTS.get(key)
    return r["value"]


def get_all() -> dict:
    out = dict(DEFAULTS)
    for r in db.all_("SELECT key, value_json FROM settings"):
        out[r["key"]] = r["value"]
    out["secrets"] = {n: has_secret(n) for n in SECRET_NAMES}
    return out


def set_many(values: dict) -> None:
    with db.tx() as c:
        for k, v in values.items():
            if k not in DEFAULTS:
                raise ValueError(f"Unknown setting: {k}")
            c.execute("INSERT INTO settings (key, value_json) VALUES (?, ?) "
                      "ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json", (k, json.dumps(v)))


def _keyring():
    if os.environ.get("AUDIENCEOS_NO_KEYCHAIN"):
        return None
    try:
        import keyring
        return keyring
    except Exception:  # pragma: no cover
        return None


def set_secret(name: str, value: str | None) -> None:
    if name not in SECRET_NAMES:
        raise ValueError("Unknown secret")
    kr = _keyring()
    if kr is None:
        if value:
            _mem_secrets[name] = value
        else:
            _mem_secrets.pop(name, None)
        return
    if value:
        kr.set_password(config.KEYCHAIN_SERVICE, name, value)
    else:
        try:
            kr.delete_password(config.KEYCHAIN_SERVICE, name)
        except Exception:
            pass
    log.info("Secret %s %s", name, "saved" if value else "removed")  # value never logged


def get_secret(name: str) -> str | None:
    if name in _mem_secrets:
        return _mem_secrets[name]
    kr = _keyring()
    if kr is None:
        return None
    try:
        return kr.get_password(config.KEYCHAIN_SERVICE, name)
    except Exception:
        return None


def has_secret(name: str) -> bool:
    return bool(get_secret(name))
