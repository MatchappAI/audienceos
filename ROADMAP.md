# Roadmap (later — deliberately not built for the three pilots)

## After the first pilots prove the economics
- **Direct checkout sync**: pull orders automatically from Stripe/Gumroad/Shopify APIs (read-only keys) instead of CSV.
- **Payout export**: one-click payout CSV for the bank / Wise; optional signed PDF statement for creators.
- **Loss carry-forward and minimum guarantees** as deal options (current rule: losses are never charged to the creator).
- **Optimization loop**: compare launched products' channel performance and price tests over time; suggest the next test.
- **Creator portal (read-only)**: a shareable statement + product dashboard per creator. This is the first step toward self-service.

## Data and analysis
- YouTube transcripts for the creator's *own* videos via YouTube Data API OAuth (captions.download requires channel ownership).
- Meta Graph API / TikTok Business API for creators who authorize their accounts.
- OCR for scanned PDFs and images (Apple Vision framework via a small Swift helper).
- Embedding-based clustering (local `nomic-embed-text`) to complement the model's clustering on large comment sets (>600 comments are currently sampled by likes/recency).
- Vision model preset (e.g. `qwen2.5vl`) one-click download for frame analysis.

## Self-service (only once agency economics are validated)
- Accounts + workspaces per creator (the `workspaces` table is already the tenant boundary), authentication, hosted deployment, Postgres.
- Hosted landing pages/storefront (today: export HTML and publish on the creator's own site/storefront).
- Billing for the platform itself.
