"""URL retrieval using only documented, public, permitted methods. Never logs in, never bypasses blocks."""
import json
import logging
import re
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse

import feedparser
from bs4 import BeautifulSoup

from .. import config, db, settings_store
from ..security import FetchError, safe_get
from . import files, platforms, store

log = logging.getLogger("audienceos.urls")


def _unsupported(platform: str, extra: str | None = None) -> dict:
    pol = platforms.policy(platform)
    missing = [pol["not_available"]]
    if extra:
        missing.insert(0, extra)
    return {"obtained": [], "missing": missing, "alternatives": pol["fallback"], "status": "unsupported",
            "method": "none — no permitted automated access"}


def youtube_id(url: str) -> str | None:
    p = urlparse(url)
    if p.hostname and p.hostname.endswith("youtu.be"):
        return p.path.strip("/").split("/")[0] or None
    if "/shorts/" in p.path:
        return p.path.split("/shorts/")[1].split("/")[0]
    if "/live/" in p.path:
        return p.path.split("/live/")[1].split("/")[0]
    return (parse_qs(p.query).get("v") or [None])[0]


def fetch_youtube(c, source, url):
    pol = platforms.policy("youtube")
    obtained, missing = [], []
    vid = youtube_id(url)
    title = author = None
    try:
        r = safe_get("https://www.youtube.com/oembed", params={"url": url, "format": "json"}, check_robots=False)
        if r.status == 200:
            o = json.loads(r.text)
            title, author = o.get("title"), o.get("author_name")
            obtained.append("Title and channel name (oEmbed)")
    except (FetchError, ValueError) as e:
        missing.append(f"Title (oEmbed failed: {e})")
    key = settings_store.get_secret("youtube_api_key")
    description, stats, comments = None, {}, []
    if key and vid:
        try:
            r = safe_get("https://www.googleapis.com/youtube/v3/videos", check_robots=False,
                         params={"part": "snippet,statistics", "id": vid, "key": key})
            items = json.loads(r.text).get("items", [])
            if items:
                sn, st = items[0]["snippet"], items[0].get("statistics", {})
                description, title, author = sn.get("description"), sn.get("title", title), sn.get("channelTitle", author)
                stats = {k: int(v) for k, v in st.items() if str(v).isdigit()}
                stats["published"] = sn.get("publishedAt")
                obtained.append("Description and public view/like/comment counts (YouTube Data API)")
            page, n = None, 0
            while n < 5:
                params = {"part": "snippet", "videoId": vid, "maxResults": 100, "key": key, "textFormat": "plainText"}
                if page:
                    params["pageToken"] = page
                r = safe_get("https://www.googleapis.com/youtube/v3/commentThreads", params=params, check_robots=False)
                d = json.loads(r.text)
                if "error" in d:
                    missing.append(f"Comments: {d['error'].get('message', 'not available')}")
                    break
                for it in d.get("items", []):
                    s = it["snippet"]["topLevelComment"]["snippet"]
                    comments.append({"text": s.get("textDisplay"), "author": s.get("authorChannelId", {}).get("value"),
                                     "date": s.get("publishedAt"), "likes": s.get("likeCount"),
                                     "replies": it["snippet"].get("totalReplyCount"), "url": url})
                page, n = d.get("nextPageToken"), n + 1
                if not page:
                    break
        except (FetchError, ValueError, KeyError) as e:
            missing.append(f"YouTube Data API request failed: {e}")
    elif not key:
        missing.append("Description, statistics and comments (add a free YouTube Data API key in Settings)")
    missing.append(pol["not_available"])
    if not title and not description:
        return {"obtained": obtained, "missing": missing, "alternatives": pol["fallback"], "status": "failed",
                "method": "YouTube oEmbed"}
    text = "\n\n".join(x for x in [title, description] if x)
    cid, _ = store.add_content_item(c, source, text=text, title=title, kind="video", url=url, author=author,
                                    published_at=store.parse_date(stats.get("published")),
                                    metadata={"video_id": vid, "note": "Metadata only — transcript not retrieved"})
    for m in ("viewCount", "likeCount", "commentCount"):
        if m in stats:
            store.add_metric(c, cid, m.replace("Count", "s"), stats[m], "YouTube Data API (public counts)")
    if comments:
        counts = store.add_comments(c, source, comments, content_item_id=cid)
        obtained.append(f"{counts['added']:,} public comments (YouTube Data API)")
    return {"obtained": obtained, "missing": missing, "alternatives": pol["fallback"],
            "status": "partial", "method": "YouTube oEmbed" + (" + YouTube Data API" if key else "")}


def fetch_oembed(c, source, url, platform):
    pol = platforms.policy(platform)
    endpoint = {"tiktok": "https://www.tiktok.com/oembed", "x": "https://publish.twitter.com/oembed"}[platform]
    try:
        r = safe_get(endpoint, params={"url": url}, check_robots=False)
        o = json.loads(r.text)
    except (FetchError, ValueError) as e:
        return {**_unsupported(platform, f"Public oEmbed lookup failed ({e})"), "status": "failed"}
    if r.status != 200 or not isinstance(o, dict):
        return {**_unsupported(platform, "The post is private, deleted or not embeddable"), "status": "failed"}
    text = o.get("title") or ""
    if platform == "x" and o.get("html"):
        soup = BeautifulSoup(o["html"], "lxml")
        p = soup.find("p")
        text = p.get_text(" ", strip=True) if p else soup.get_text(" ", strip=True)
    if not text:
        return {**_unsupported(platform, "No caption/text returned"), "status": "failed"}
    store.add_content_item(c, source, text=text, title=text[:90], kind="post", url=url, author=o.get("author_name"),
                           metadata={"via": "oEmbed"})
    return {"obtained": ["Caption/post text and author (public oEmbed)"], "missing": [pol["not_available"]],
            "alternatives": pol["fallback"], "status": "partial", "method": "public oEmbed"}


def _flatten_reddit(children, out, depth=0):
    for ch in children:
        if ch.get("kind") != "t1":
            continue
        d = ch["data"]
        out.append({"text": d.get("body"), "author": d.get("author"), "date": d.get("created_utc"),
                    "likes": max(0, d.get("score") or 0), "url": "https://www.reddit.com" + d.get("permalink", "")})
        rep = d.get("replies")
        if isinstance(rep, dict) and depth < 6:
            _flatten_reddit(rep["data"]["children"], out, depth + 1)


def fetch_reddit(c, source, url):
    pol = platforms.policy("reddit")
    p = urlparse(url)
    if "/comments/" not in p.path:
        return _unsupported("reddit", "Only individual Reddit threads (…/comments/…) can be retrieved")
    jurl = f"https://www.reddit.com{p.path.rstrip('/')}.json"
    try:
        r = safe_get(jurl, params={"limit": 500, "raw_json": 1})
    except FetchError as e:
        return {**_unsupported("reddit", str(e)), "status": "failed"}
    if r.status == 429:
        return {**_unsupported("reddit", "Reddit rate-limited the request; try later"), "status": "failed"}
    try:
        data = json.loads(r.text)
        post = data[0]["data"]["children"][0]["data"]
    except (ValueError, KeyError, IndexError, TypeError):
        return {**_unsupported("reddit", f"Reddit did not return thread data (HTTP {r.status})"), "status": "failed"}
    text = f"{post.get('title', '')}\n\n{post.get('selftext', '')}".strip()
    cid, _ = store.add_content_item(c, source, text=text, title=post.get("title"), kind="post", url=url,
                                    published_at=store.parse_date(post.get("created_utc")),
                                    metadata={"subreddit": post.get("subreddit")})
    store.add_metric(c, cid, "score", max(0, post.get("score") or 0), "Reddit public JSON")
    store.add_metric(c, cid, "comments", post.get("num_comments"), "Reddit public JSON")
    out = []
    _flatten_reddit(data[1]["data"]["children"], out)
    counts = store.add_comments(c, source, out, content_item_id=cid)
    return {"obtained": [f"Thread text and {counts['added']:,} visible comments"],
            "missing": ["Collapsed 'load more' comments", pol["not_available"]], "alternatives": pol["fallback"],
            "status": "ready", "method": "Reddit public JSON view"}


def fetch_feed(c, source, url, transcribe_audio: int = 0, progress=None):
    try:
        r = safe_get(url, accept="application/rss+xml, application/atom+xml, application/xml, text/xml")
    except FetchError as e:
        return {"obtained": [], "missing": [str(e)], "status": "failed", "method": "RSS/Atom feed"}
    feed = feedparser.parse(r.body)
    if not feed.entries:
        return {"obtained": [], "missing": ["The link did not contain a readable RSS/Atom feed"], "status": "failed",
                "method": "RSS/Atom feed"}
    n_items, enclosures = 0, []
    for e in feed.entries[:200]:
        body = ""
        if e.get("content"):
            body = e["content"][0].get("value", "")
        body = body or e.get("summary", "")
        text, _, _ = files.html_to_text(body) if "<" in body else (body, None, None)
        title = e.get("title")
        enc = next((l.get("href") for l in e.get("links", []) if l.get("rel") == "enclosure"
                    and str(l.get("type", "")).startswith("audio")), None)
        cid, created = store.add_content_item(
            c, source, text=f"{title or ''}\n\n{text}".strip(), title=title,
            kind="episode" if enc else "article", url=e.get("link"), author=e.get("author"),
            published_at=store.parse_date(e.get("published") or e.get("updated")),
            metadata={"feed": feed.feed.get("title"), "enclosure": enc})
        n_items += created
        if enc and created:
            enclosures.append((cid, enc, title))
    obtained = [f"{n_items} entries from '{feed.feed.get('title', 'feed')}' (titles, text/show notes, dates)"]
    missing = ["Subscriber/listener counts and open rates (not published in feeds)"]
    if enclosures and transcribe_audio:
        c.commit()
        done = 0
        for cid, enc, title in enclosures[:transcribe_audio]:
            try:
                if progress:
                    progress(0.3 + 0.6 * done / transcribe_audio, f"Downloading & transcribing: {title[:40] if title else 'episode'}")
                a = safe_get(enc, max_bytes=config.MAX_MEDIA_DOWNLOAD_BYTES, check_robots=False, accept="audio/*")
                work = config.MEDIA_DIR / source["id"]
                work.mkdir(parents=True, exist_ok=True)
                raw = work / f"{cid}.audio"
                raw.write_bytes(a.body)
                from . import media
                wav = media.extract_audio(raw, work / f"{cid}.wav")
                t = media.transcribe(wav)
                raw.unlink(missing_ok=True)
                wav.unlink(missing_ok=True)
                if t["text"]:
                    db.insert(c, "transcripts", {"id": db.new_id("tr"), "content_item_id": cid, "engine": t["engine"],
                                                 "language": t["language"], "text": t["text"],
                                                 "segments_json": t["segments"], "created_at": db.now()})
                    stamped = media.transcript_with_timestamps(t["segments"])
                    c.execute("UPDATE content_items SET text = text || ? , word_count = word_count + ? WHERE id=?",
                              ("\n\nTRANSCRIPT\n" + stamped, len(t["text"].split()), cid))
                    c.commit()
                    done += 1
            except Exception as ex:
                missing.append(f"Episode '{title}': transcription failed ({str(ex)[:120]})")
        obtained.append(f"{done} episode transcripts (local Whisper)")
    elif enclosures:
        missing.append(f"{len(enclosures)} episodes have audio; transcription was not requested")
    return {"obtained": obtained, "missing": missing, "status": "ready", "method": "RSS/Atom feed"}


def fetch_apple_podcast(c, source, url, transcribe_audio, progress):
    m = re.search(r"/id(\d+)", url)
    if not m:
        return _unsupported("podcast", "Could not find the podcast ID in the link")
    try:
        r = safe_get("https://itunes.apple.com/lookup", params={"id": m.group(1), "entity": "podcast"}, check_robots=False)
        res = json.loads(r.text).get("results", [])
    except (FetchError, ValueError) as e:
        return {**_unsupported("podcast", f"Apple lookup failed: {e}"), "status": "failed"}
    feed = next((x.get("feedUrl") for x in res if x.get("feedUrl")), None)
    if not feed:
        return {**_unsupported("podcast", "Apple did not list a public RSS feed for this show"), "status": "failed"}
    out = fetch_feed(c, source, feed, transcribe_audio, progress)
    out["method"] = "Apple Podcasts lookup API → public RSS feed"
    out["obtained"].insert(0, f"Found public feed: {feed}")
    out["missing"].append("Apple Podcasts reviews and ratings (no public API)")
    return out


def fetch_web(c, source, url, transcribe_audio=0, progress=None):
    pol = platforms.policy("web")
    try:
        r = safe_get(url)
    except FetchError as e:
        return {"obtained": [], "missing": [str(e)], "alternatives": pol["fallback"], "status": "failed",
                "method": "direct web request"}
    if r.status in (401, 403):
        return {"obtained": [], "missing": [f"The site refused access (HTTP {r.status}) — it may require login or block automated access."],
                "alternatives": pol["fallback"], "status": "failed", "method": "direct web request"}
    if r.status >= 400:
        return {"obtained": [], "missing": [f"The page returned an error (HTTP {r.status})."],
                "alternatives": pol["fallback"], "status": "failed", "method": "direct web request"}
    ct = r.content_type.lower()
    if "xml" in ct or "rss" in ct or r.body[:200].lstrip().startswith(b"<?xml") and b"<rss" in r.body[:2000]:
        return fetch_feed(c, source, url, transcribe_audio, progress)
    if "pdf" in ct:
        tmp = config.UPLOADS_DIR / f"{source['id']}.pdf"
        tmp.write_bytes(r.body)
        out = files.import_pdf(c, source, tmp)
        out["method"] = "direct download (PDF)"
        return out
    if "html" not in ct and "text" not in ct:
        return {"obtained": [], "missing": [f"Unsupported content type '{ct}'. Download the file and upload it instead."],
                "status": "unsupported", "method": "direct web request"}
    text, title, meta = files.html_to_text(r.text)
    if len(text.split()) < 40:
        alts = list(pol["fallback"])
        if meta.get("feeds"):
            alts.insert(0, f"This site has a feed you can add: {meta['feeds'][0]}")
        return {"obtained": [f"Page title: {title}"] if title else [],
                "missing": ["Almost no readable text — the page is probably built with JavaScript or requires login."],
                "alternatives": alts, "status": "failed", "method": "direct web request"}
    store.add_content_item(c, source, text=text, title=title, kind="page", url=r.final_url,
                           published_at=store.parse_date(meta.get("published")), metadata=meta)
    missing = ["Comments, reader feedback and engagement on this page (not included in page text)"]
    if not meta.get("published"):
        missing.append("Publish date")
    alts = [f"This site publishes a feed: {meta['feeds'][0]}"] if meta.get("feeds") else []
    return {"obtained": [f"Page text ({len(text.split()):,} words)" + (", publish date" if meta.get("published") else "")],
            "missing": missing, "alternatives": alts, "status": "ready", "method": "direct web request (robots.txt checked)"}


def fetch_url(c, source, url, transcribe_audio=0, progress=None) -> dict:
    platform = source.get("platform") or platforms.detect(url)
    if platform == "youtube":
        return fetch_youtube(c, source, url)
    if platform in ("tiktok", "x"):
        return fetch_oembed(c, source, url, platform)
    if platform in ("instagram", "facebook", "linkedin"):
        return _unsupported(platform)
    if platform == "reddit":
        return fetch_reddit(c, source, url)
    if platform == "podcast" and "podcasts.apple.com" in url:
        return fetch_apple_podcast(c, source, url, transcribe_audio, progress)
    if platform == "feed":
        return fetch_feed(c, source, url, transcribe_audio, progress)
    if platform == "substack":
        p = urlparse(url)
        if p.path in ("", "/"):
            out = fetch_feed(c, source, f"{p.scheme}://{p.netloc}/feed", transcribe_audio, progress)
            out["method"] = "Substack public RSS feed"
            return out
    return fetch_web(c, source, url, transcribe_audio, progress)
