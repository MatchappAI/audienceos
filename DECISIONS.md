# Decisions

| # | Decision | Why |
|---|---|---|
| 1 | Local web app (FastAPI + React) opened in a Chrome app window, not Electron | One process, no code signing, same UI can later be hosted for self-service creators |
| 2 | SQLite + numbered SQL migrations | Zero setup, single-file backup, enough for thousands of sources per audience |
| 3 | Project-local Ollama runtime (`runtime/`) with `qwen2.5:7b` default (`3b` also installed) | Real local AI with no account or API cost; doesn't touch system installs. 7B is the best quality that runs comfortably on a 16 GB M4 |
| 4 | faster-whisper `base` on CPU, fed by bundled FFmpeg | No Homebrew needed; accurate enough for spoken content. `small` is selectable for better accuracy |
| 5 | Verify every AI-cited quote against the stored source | Makes "every claim traceable" enforceable rather than aspirational |
| 6 | Strong-intent labels require supporting words in the quote | Testing showed the 7B model labels plain frustration as "spending"; revenue decisions must not rest on that |
| 7 | Intent counted per distinct voice; duplicates and spam excluded | Prevents one loud commenter or a copy-paste campaign looking like demand |
| 8 | Score shown as a 0–100 relative index with visible weights, never a percentage chance | Calibrated probabilities don't exist for this; a transparent ranking does |
| 9 | Opportunities without traceable evidence are dropped | Accuracy over volume |
| 10 | No payment processing. Products sell via the creator's own checkout (Stripe Payment Link, Gumroad, Shopify…); AudienceOS imports orders | Avoids building a regulated payments stack before the model is proven; any checkout works |
| 11 | Launch requires a 5-item checklist, an https checkout link, all assets approved and a named approver; changing price/name/link resets approval | "Human approval before publishing" enforced in the API, not just the UI |
| 12 | Revenue share is configurable per creator (default 70% creator / 30% agency) on either *net sales after fees* or *contribution after shared costs*; losses are not charged to the creator | The strategy says 70/30 but not the base; both bases are supported so the contract decides |
| 13 | Rules engine never generates product ideas | Template ideas would be "generic AI recommendations" pretending to be research |
| 14 | Instagram / Facebook / LinkedIn URLs are reported as unsupported with export instructions | No permitted public access exists; we don't scrape |
| 15 | No accounts, auth, billing or multi-tenant features yet | Premature for three pilots; the workspace → organization hierarchy leaves room for them |
