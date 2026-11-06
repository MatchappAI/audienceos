# Things only you can do

1. **Decide the revenue-share base for the pilot contracts.** "70/30" is configured as *creator 70% / agency 30%* of **contribution** (net sales − payment fees − shared costs). If your contract means something else (e.g. 30% to the creator, or a split of net sales), change it per creator in **Creators & Revenue → Deal**.
2. **Pick each pilot creator's checkout** (Stripe Payment Link, Gumroad, Lemon Squeezy, Shopify…). AudienceOS doesn't take payments. You paste the checkout link on the product and import the order CSV from that checkout.
3. **Collect creator data exports** (no integrations needed):
   - Instagram: Accounts Center → Download your information → JSON (comments) + Insights CSV
   - TikTok: Settings → Download your data
   - YouTube: YouTube Studio analytics export; for comments add a free YouTube Data API key (Settings)
   - Newsletter: the publication's RSS URL + the platform's subscriber/post stats CSV
   - The creator's own video files (for transcription)
4. **Optional keys** (Settings → saved in your Mac's Keychain):
   - Anthropic API key, for higher-quality analysis. Each run asks before sending data, and usage is billed to your account.
   - A free YouTube Data API key, for public comments and statistics.
   - A Brave Search API key, for automated competitor search.
   - A **Stripe restricted key** (read-only: Checkout Sessions, Payment Intents, Charges, Balance transactions) or a **Gumroad access token**, to sync orders instead of importing CSVs. On each product → Checkout sync, enter the Payment Link ID (`plink_…`) or the Gumroad product ID.
   - Settings → Optional local models: download `nomic-embed-text` (~270 MB) for meaning-based grouping of large comment sets, and a vision model if you analyse video frames.
5. **Get creator consent** before importing their audience's comments, and before any external AI run on them.
6. **Decide the deal options per creator.** Loss carry-forward and a minimum guarantee are off by default. Turn them on only if the signed contract says so.
7. **Before the first payout run**, check each creator's contact email (the payout file needs it), pay outside AudienceOS, then record each payout.
