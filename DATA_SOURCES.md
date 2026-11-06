# Data sources

AudienceOS only uses documented, public, permitted access. It never logs in as you and never bypasses logins, CAPTCHAs, rate limits or anti-bot protection. It respects robots.txt for web pages. When something can't be retrieved, the source shows exactly what was obtained, what is missing, and the legitimate alternative.

**Creator-provided data is first-class:** every platform's comments, analytics and media can be imported as files (CSV/JSON/MP4/etc.) without any integration.

## YouTube

- **Retrieved automatically:** Title and channel via YouTube's public oEmbed endpoint. With an optional free YouTube Data API key: description, view/like/comment counts and public comments.
- **Not available:** Video transcript (YouTube does not permit downloading captions or media for videos you don't own).
- **Supported alternatives:**
  - Add a free YouTube Data API key in Settings to import public comments and statistics.
  - Paste the transcript (YouTube → '…more' → 'Show transcript') as text.
  - If it's your video, upload the original file from YouTube Studio for local transcription.

## TikTok

- **Retrieved automatically:** Caption and author via TikTok's public oEmbed endpoint.
- **Not available:** Comments, views and the video file (no public access without TikTok's approved research/business APIs).
- **Supported alternatives:**
  - Upload the video file (TikTok → Save video, or your account's data export).
  - Import comments as CSV/JSON from your TikTok data export ('Download your data').

## Instagram

- **Retrieved automatically:** Nothing automatically — Instagram requires a logged-in Meta app for any post data.
- **Not available:** Captions, comments, reach and media.
- **Supported alternatives:**
  - Accounts Center → 'Download your information' (JSON) and import the comments file.
  - Upload the Reel/video file and paste the caption as text.
  - Import Instagram Insights exported as CSV for reach and engagement.

## Facebook

- **Retrieved automatically:** Nothing automatically — Facebook requires an authorized Meta app.
- **Not available:** Posts, comments, group discussions and reach.
- **Supported alternatives:**
  - Use Meta Business Suite exports (CSV) for pages you manage.
  - Download your information (JSON) and import comments.
  - Paste posts or group questions you are authorized to use as text.

## X (Twitter)

- **Retrieved automatically:** Post text and author via X's public oEmbed endpoint (publish.twitter.com).
- **Not available:** Replies, impressions and video files (require paid X API access).
- **Supported alternatives:**
  - Import your X data archive or analytics CSV.
  - Paste replies as text or CSV.

## LinkedIn

- **Retrieved automatically:** Nothing automatically — LinkedIn blocks automated access.
- **Not available:** Posts, comments, articles and analytics.
- **Supported alternatives:**
  - Export post analytics from LinkedIn (Analytics → Export) as CSV/XLSX→CSV.
  - Paste posts and comments as text, or upload the video file.

## Reddit

- **Retrieved automatically:** Public thread text and comments via Reddit's public JSON view (rate-limited, read-only).
- **Not available:** Private/quarantined communities and anything requiring login.
- **Supported alternatives:**
  - Paste the discussion as text if retrieval is rate-limited.

## Newsletter (Substack)

- **Retrieved automatically:** Public posts via the publication's RSS feed (/feed) and public web pages.
- **Not available:** Paywalled posts, subscriber counts, open/click rates.
- **Supported alternatives:**
  - Export your post list and subscriber stats from the Substack dashboard (CSV).

## Podcast

- **Retrieved automatically:** Episode titles, descriptions and (on request) episode audio for transcription via the show's public RSS feed.
- **Not available:** Listener counts and reviews from Apple/Spotify (no public API).
- **Supported alternatives:**
  - Paste the show's RSS feed URL.
  - Upload episode audio files.
  - Paste reviews as text.

## Website / blog

- **Retrieved automatically:** Public page text, title and publish date, if robots.txt allows.
- **Not available:** Pages behind logins or paywalls, and pages that block automated access.
- **Supported alternatives:**
  - Save the page as PDF/HTML and upload it, or paste the text.

## RSS / Atom feeds (newsletters, blogs, podcasts)

Entries (title, text/show notes, date, link). Podcast episode audio can optionally be downloaded from the feed's enclosure and transcribed locally (up to 10 episodes per import, 300 MB each).

## File imports (any platform)

| Type | Formats | What happens |
|---|---|---|
| Text | .txt .md .html | Text extracted (HTML scripts/styles removed) |
| Documents | .pdf .docx | Text extracted; scanned PDFs without a text layer are reported (no OCR offline) |
| Comments / messages | .csv .json | Auto-detects text, date, likes, replies, author and parent-post columns. Meta "Download your information" JSON is understood. Authors are stored only as one-way hashes. Duplicates and likely spam are flagged and excluded from analysis. |
| Analytics | .csv | Rows with a title/URL and metric columns (views, likes, impressions, reach, saves, opens…) become engagement metrics |
| Audio | .mp3 .wav .m4a .aac .ogg .flac | Transcribed on this Mac (Whisper), timestamps kept |
| Video | .mp4 .mov .m4v .webm .mkv .avi | Audio transcribed; up to 6 frames sampled; frames described only if a vision model is configured |
| Images | .png .jpg .webp .gif .heic | Stored; described only if a vision model is configured |

Limits: 1 GB per upload; web pages 15 MB. Executables and disguised binaries are rejected by content sniffing.

## Sales data (validation tests and launched products)

Order exports from any checkout (Stripe, Gumroad, Lemon Squeezy, Shopify, Kajabi…) as CSV. Needs an order-ID column and an amount column; refund, fee, date and `utm_source`/channel columns are used when present. Re-importing the same file never double counts.
