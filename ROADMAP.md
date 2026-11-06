# Roadmap

## Done in 1.3.0
- Payout export (Wise batch CSV) + fingerprinted PDF statement
- Loss carry-forward and minimum guarantees as deal options
- Optimization loop: next-test suggestions per launched product, products compared
- Read-only creator portal (self-contained HTML to send)
- Direct checkout sync: Stripe Payment Links, Gumroad, Shopify, Lemon Squeezy (read-only; 1.4.0)
- OCR for scanned PDFs and images (Apple Vision)
- Embedding-based sampling/clustering (local `nomic-embed-text`)
- One-click vision/embedding model downloads

## Needs something only you can provide
- **YouTube OAuth transcripts** for a creator's own videos: requires a Google Cloud OAuth client, plus Google's verification for the `youtube.force-ssl` scope.
- **Meta Graph / TikTok Business APIs**: require registered developer apps and app review by Meta/TikTok. Until then, use data exports, which already work.

## Self-service (only once agency economics are validated)
- Accounts + workspaces per creator (the `workspaces` table is already the tenant boundary), authentication, hosted deployment, Postgres.
- Hosted landing pages/storefront and a hosted creator portal (today: exported HTML).
- Billing for the platform itself.
