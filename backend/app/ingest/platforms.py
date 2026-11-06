"""Platform detection and the honest access policy for each platform.

The policy text is shown in the app and in DATA_SOURCES.md. It states what AudienceOS can
retrieve directly, and the legitimate fallback when it cannot.
"""
from urllib.parse import urlparse

PLATFORMS = {
    "youtube": {
        "label": "YouTube",
        "hosts": ("youtube.com", "youtu.be", "m.youtube.com"),
        "direct": "Title and channel via YouTube's public oEmbed endpoint. With an optional free YouTube Data API key: "
                  "description, view/like/comment counts and public comments.",
        "not_available": "Video transcript (YouTube does not permit downloading captions or media for videos you don't own).",
        "fallback": ["Add a free YouTube Data API key in Settings to import public comments and statistics.",
                     "Paste the transcript (YouTube → '…more' → 'Show transcript') as text.",
                     "If it's your video, upload the original file from YouTube Studio for local transcription."],
    },
    "tiktok": {
        "label": "TikTok",
        "hosts": ("tiktok.com", "vm.tiktok.com"),
        "direct": "Caption and author via TikTok's public oEmbed endpoint.",
        "not_available": "Comments, views and the video file (no public access without TikTok's approved research/business APIs).",
        "fallback": ["Upload the video file (TikTok → Save video, or your account's data export).",
                     "Import comments as CSV/JSON from your TikTok data export ('Download your data')."],
    },
    "instagram": {
        "label": "Instagram",
        "hosts": ("instagram.com",),
        "direct": "Nothing automatically — Instagram requires a logged-in Meta app for any post data.",
        "not_available": "Captions, comments, reach and media.",
        "fallback": ["Accounts Center → 'Download your information' (JSON) and import the comments file.",
                     "Upload the Reel/video file and paste the caption as text.",
                     "Import Instagram Insights exported as CSV for reach and engagement."],
    },
    "facebook": {
        "label": "Facebook",
        "hosts": ("facebook.com", "fb.watch", "m.facebook.com"),
        "direct": "Nothing automatically — Facebook requires an authorized Meta app.",
        "not_available": "Posts, comments, group discussions and reach.",
        "fallback": ["Use Meta Business Suite exports (CSV) for pages you manage.",
                     "Download your information (JSON) and import comments.",
                     "Paste posts or group questions you are authorized to use as text."],
    },
    "x": {
        "label": "X (Twitter)",
        "hosts": ("x.com", "twitter.com", "mobile.twitter.com"),
        "direct": "Post text and author via X's public oEmbed endpoint (publish.twitter.com).",
        "not_available": "Replies, impressions and video files (require paid X API access).",
        "fallback": ["Import your X data archive or analytics CSV.", "Paste replies as text or CSV."],
    },
    "linkedin": {
        "label": "LinkedIn",
        "hosts": ("linkedin.com",),
        "direct": "Nothing automatically — LinkedIn blocks automated access.",
        "not_available": "Posts, comments, articles and analytics.",
        "fallback": ["Export post analytics from LinkedIn (Analytics → Export) as CSV/XLSX→CSV.",
                     "Paste posts and comments as text, or upload the video file."],
    },
    "reddit": {
        "label": "Reddit",
        "hosts": ("reddit.com", "old.reddit.com", "www.reddit.com"),
        "direct": "Public thread text and comments via Reddit's public JSON view (rate-limited, read-only).",
        "not_available": "Private/quarantined communities and anything requiring login.",
        "fallback": ["Paste the discussion as text if retrieval is rate-limited."],
    },
    "substack": {
        "label": "Newsletter (Substack)",
        "hosts": ("substack.com",),
        "direct": "Public posts via the publication's RSS feed (/feed) and public web pages.",
        "not_available": "Paywalled posts, subscriber counts, open/click rates.",
        "fallback": ["Export your post list and subscriber stats from the Substack dashboard (CSV)."],
    },
    "podcast": {
        "label": "Podcast",
        "hosts": ("podcasts.apple.com", "open.spotify.com", "anchor.fm", "buzzsprout.com", "libsyn.com", "transistor.fm", "simplecast.com"),
        "direct": "Episode titles, descriptions and (on request) episode audio for transcription via the show's public RSS feed.",
        "not_available": "Listener counts and reviews from Apple/Spotify (no public API).",
        "fallback": ["Paste the show's RSS feed URL.", "Upload episode audio files.", "Paste reviews as text."],
    },
    "web": {
        "label": "Website / blog",
        "hosts": (),
        "direct": "Public page text, title and publish date, if robots.txt allows.",
        "not_available": "Pages behind logins or paywalls, and pages that block automated access.",
        "fallback": ["Save the page as PDF/HTML and upload it, or paste the text."],
    },
}

UPLOAD_PLATFORMS = ["youtube", "tiktok", "instagram", "facebook", "x", "linkedin", "reddit", "substack",
                    "newsletter", "podcast", "web", "community", "other"]


def detect(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    host = host[4:] if host.startswith("www.") else host
    for key, p in PLATFORMS.items():
        for h in p["hosts"]:
            if host == h or host.endswith("." + h):
                return key
    path = urlparse(url).path.lower()
    if path.endswith((".rss", ".xml", "/feed", "/rss", "/feed/", "/atom.xml")):
        return "feed"
    return "web"


def policy(platform: str) -> dict:
    return PLATFORMS.get(platform, PLATFORMS["web"])
