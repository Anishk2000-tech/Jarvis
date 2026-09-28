"""
Web research: find, read, and hand the brain the passages that answer.

A local model knows nothing after its training date and cannot tell when it is
guessing. So the assistant looks things up — when the model asks for it
(web_search tool), before the model answers a question that is plainly about
the present ("who won yesterday", "petrol price today"), and after the model
admits it does not know (see sounds_unsure).

    1. search     several engines at once through ddgs (DuckDuckGo, Bing,
                  Google, Brave, Yahoo, Mojeek, Wikipedia…), or a service the
                  user added a key for: Tavily (with its AI answer), Brave
                  Search API, Serper (Google results, answer box, knowledge
                  graph), or a SearXNG server
    2. AI answer  Google's own AI answer through the Gemini API's Google Search
                  grounding when a Gemini key is set (free tier) — the legit
                  way to get "what Google's AI says"
    3. read       the top pages are fetched in parallel and cut into passages;
                  the passages that best match the question are kept (not the
                  whole page — a small model's context is precious)
    4. hand over  a compact [WEB_RESULTS] block with sources, which the brain
                  answers from in its own words

Every step has a deadline, so a slow site costs a few seconds, not the answer.
Results are cached for ten minutes.
"""
from __future__ import annotations

import json
import math
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, wait
from datetime import datetime
from urllib.parse import quote, urlparse

import requests

from core import brain_config

_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
       "Chrome/126.0 Safari/537.36")
_cache: dict[tuple, tuple[float, str]] = {}
_cache_lock = threading.Lock()
_CACHE_S = 600

_SKIP_DOMAINS = ("youtube.com", "youtu.be", "facebook.com", "instagram.com", "tiktok.com",
                 "x.com", "twitter.com", "pinterest.", "linkedin.com")

_STOP = set("""a an the of in on at to for from by with and or but is are was were be been being do does
did what who whom whose which when where why how this that these those it its it's i me my you your he
she they them his her their we our us as about into over than then so if not no yes can could will
would should shall may might must there here also just only very more most much many some any all tell
please give show find search latest current today now kya hai ka ki ke ko se mein me aur""".split())


# ── configuration ────────────────────────────────────────────────────────────

def cfg() -> dict:
    return brain_config.get_search_cfg()


def _region() -> str:
    r = str(cfg().get("region") or "auto").strip().lower()
    if r and r != "auto":
        return r
    try:
        import sys
        if sys.platform == "win32":
            import ctypes
            buf = ctypes.create_unicode_buffer(85)
            if ctypes.windll.kernel32.GetUserDefaultLocaleName(buf, 85):
                m = re.match(r"([a-z]{2})-([A-Z]{2})", buf.value)      # e.g. en-IN, hi-IN
                if m:
                    return f"{m.group(2).lower()}-{m.group(1)}"
    except Exception:
        pass
    try:
        import locale
        loc = (locale.getlocale()[0] or "")
        m = re.search(r"[_-]([A-Za-z]{2})\b", loc)
        country = m.group(1).lower() if m else ""
        if not country and "india" in loc.lower():
            country = "in"
        if country:
            return f"{country}-en"
    except Exception:
        pass
    return "us-en"


# ── deciding when to look things up ─────────────────────────────────────────

_FRESH = re.compile(
    r"\b(today|tonight|tomorrow|yesterday|right now|currently|current|latest|recent(ly)?|"
    r"this (week|month|year|season)|last (night|week|month)|news|headlines?|price|prices|cost|"
    r"rate|rates|stock|shares?|sensex|nifty|bitcoin|crypto|exchange rate|score|scores|match|"
    r"won|winner|result|results|election|released?|release date|launch(ed)?|new version|update|"
    r"trending|live|upcoming|schedule|fixtures?|box office|ranking|who is the (current )?"
    r"(ceo|president|prime minister|pm|chief minister|cm|captain|coach|owner|head)|"
    r"20(2[4-9]|3\d)|aaj|abhi|taaza|khabar|keemat|daam|bhav|"
    r"आज|अभी|ताज़ा|ताजा|खबर|ख़बर|कीमत|क़ीमत|भाव|नवीनतम|हाल ही)\b", re.I)
_QUESTION = re.compile(
    r"(\?|^\s*(who|what|when|where|which|why|how|is|are|was|were|does|did|do|can|will|has|have|"
    r"tell me|give me|find|search|look up|check)\b|"
    r"\b(kya|kaun|kab|kitna|kitne|kitni|kaise|kahan|kyun|kyon|batao|bataiye)\b|"
    r"क्या|कौन|कब|कितना|कितने|कैसे|कहाँ|कहां|बताओ|बताइए)", re.I)
_COMMAND = re.compile(
    r"^\s*(open|play|start|launch|close|turn|switch|set|create|make|write|send|call|remind|"
    r"schedule|type|click|go to|show me my|lock|shut|restart|mute|pause|resume|stop|record|"
    r"download|install|delete|move|copy|rename)\b", re.I)


def needs_fresh_info(text: str) -> bool:
    """A question about the present that the model cannot answer from training."""
    t = (text or "").strip()
    if len(t) < 8 or _COMMAND.search(t):
        return False
    if re.search(r"\bweather\b|मौसम|mausam", t, re.I):
        return False              # the weather tool is better and faster
    return bool(_FRESH.search(t)) and bool(_QUESTION.search(t))


_UNSURE = re.compile(
    r"(\bi (do not|don't|dont) (know|have (any )?(information|info|data|details|access|real[- ]time|"
    r"current|up[- ]to[- ]date|the ability))|\bi'?m not (sure|aware|certain)|\bi am not (sure|aware|"
    r"certain)|\bas of my (last|knowledge|training)|\bmy (knowledge|training)( data)? (cut[- ]?off|"
    r"only goes|ends|is limited)|\bi (can ?not|can't|cannot|am unable to|'m unable to) (browse|search|"
    r"access|look up|check|provide (real[- ]time|current|live))|\bno (access|ability) to (the )?"
    r"(internet|web|real[- ]time)|\bi (couldn't|could not|was unable to) find|\bi have no (information|"
    r"knowledge|data)|\bnot (able|possible) (for me )?to (browse|access)|मुझे (नहीं|नही) पता|"
    r"मुझे पता (नहीं|नही)|मेरे पास (इसकी )?(कोई )?जानकारी (नहीं|नही)|mujhe (nahi|nahin) pata|"
    r"mere paas (koi )?jaankari (nahi|nahin))", re.I)


def sounds_unsure(text: str) -> bool:
    """The model is admitting it does not know (or cannot browse)."""
    return bool(_UNSURE.search(text or ""))


# ── engines ──────────────────────────────────────────────────────────────────

def _ddgs_text(query: str, n: int, news: bool = False) -> list[dict]:
    try:
        from ddgs import DDGS
    except ImportError:
        from duckduckgo_search import DDGS   # type: ignore
    kw = {"region": _region(), "safesearch": "moderate", "max_results": n}
    with DDGS(timeout=6) as d:
        rows = d.news(query, **kw) if news else d.text(query, **kw)
    out = []
    for r in rows or []:
        out.append({"title": r.get("title", ""), "url": r.get("href") or r.get("url", ""),
                     "snippet": r.get("body", ""), "date": r.get("date", ""),
                     "source": r.get("source", "")})
    return out


def _tavily(query: str, key: str, n: int) -> tuple[str, list[dict]]:
    r = requests.post("https://api.tavily.com/search", timeout=15,
                      headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                      json={"api_key": key, "query": query, "search_depth": "basic",
                            "include_answer": True, "max_results": n})
    r.raise_for_status()
    d = r.json()
    rows = [{"title": x.get("title", ""), "url": x.get("url", ""), "snippet": "",
             "content": x.get("content", ""), "date": x.get("published_date", "")}
            for x in d.get("results") or []]
    return str(d.get("answer") or ""), rows


def _brave(query: str, key: str, n: int) -> list[dict]:
    r = requests.get("https://api.search.brave.com/res/v1/web/search", timeout=10,
                     params={"q": query, "count": n},
                     headers={"X-Subscription-Token": key, "Accept": "application/json"})
    r.raise_for_status()
    d = r.json()
    return [{"title": x.get("title", ""), "url": x.get("url", ""),
             "snippet": re.sub(r"<[^>]+>", "", x.get("description", "")), "date": x.get("age", "")}
            for x in (d.get("web") or {}).get("results") or []]


def _serper(query: str, key: str, n: int, news: bool = False) -> tuple[str, list[dict]]:
    region = _region()
    country = region.split("-")[0] if "-" in region else "us"
    r = requests.post(f"https://google.serper.dev/{'news' if news else 'search'}", timeout=10,
                      headers={"X-API-KEY": key, "Content-Type": "application/json"},
                      json={"q": query, "gl": country, "num": n})
    r.raise_for_status()
    d = r.json()
    answer = []
    box = d.get("answerBox") or {}
    for k in ("answer", "snippet"):
        if box.get(k):
            answer.append(str(box[k]))
            break
    kg = d.get("knowledgeGraph") or {}
    if kg.get("description"):
        attrs = "; ".join(f"{a}: {v}" for a, v in list((kg.get("attributes") or {}).items())[:6])
        answer.append(f"{kg.get('title', '')}: {kg['description']}" + (f" ({attrs})" if attrs else ""))
    for k, v in d.items():
        if "ai" in k.lower() and "overview" in k.lower():
            answer.append(json.dumps(v, ensure_ascii=False)[:1200] if not isinstance(v, str) else v)
    rows = [{"title": x.get("title", ""), "url": x.get("link", ""), "snippet": x.get("snippet", ""),
             "date": x.get("date", ""), "source": x.get("source", "")}
            for x in (d.get("news") if news else d.get("organic")) or []]
    return "\n".join(answer), rows


def _searxng(query: str, base: str, n: int, news: bool = False) -> tuple[str, list[dict]]:
    params = {"q": query, "format": "json"}
    if news:
        params["categories"] = "news"
    r = requests.get(base.rstrip("/") + "/search", params=params, timeout=10,
                     headers={"User-Agent": _UA})
    r.raise_for_status()
    d = r.json()
    answer = " ".join(str(a) if isinstance(a, str) else str(a.get("answer", ""))
                      for a in d.get("answers") or [])
    rows = [{"title": x.get("title", ""), "url": x.get("url", ""), "snippet": x.get("content", ""),
             "date": x.get("publishedDate") or ""} for x in (d.get("results") or [])[:n]]
    return answer, rows


def _google_ai(query: str) -> str:
    """Google's AI answer via Gemini + Google Search grounding (needs a Gemini key)."""
    if not brain_config.gemini_key():
        return ""
    try:
        from actions.web_search import _gemini_search
        return _gemini_search(query)
    except Exception as e:
        print(f"[Search] Google AI answer unavailable: {str(e)[:120]}")
        return ""


def _wikipedia(query: str) -> str:
    """Encyclopaedia summary for 'who/what is X' questions."""
    m = re.match(r"^\s*(who|what)\s+(is|was|are|were)\s+(an?\s+|the\s+)?(.+?)\??\s*$", query, re.I)
    if not m:
        return ""
    topic = m.group(4)
    try:
        lang = "en"
        r = requests.get(f"https://{lang}.wikipedia.org/w/api.php", timeout=6,
                         params={"action": "opensearch", "search": topic, "limit": 1, "format": "json"},
                         headers={"User-Agent": "JARVIS-assistant/1.0"})
        titles = r.json()[1] if r.ok else []
        if not titles:
            return ""
        r = requests.get(f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{quote(titles[0])}",
                         timeout=6, headers={"User-Agent": "JARVIS-assistant/1.0"})
        if r.ok:
            d = r.json()
            ex = d.get("extract", "")
            return f"{d.get('title', titles[0])} (Wikipedia): {ex}" if ex else ""
    except Exception:
        return ""
    return ""


# ── reading pages ────────────────────────────────────────────────────────────

def fetch_page_text(url: str, timeout: float = 7.0, max_bytes: int = 1_500_000) -> str:
    """Readable text of a web page ('' if it is not HTML or does not load)."""
    try:
        with requests.get(url, timeout=(5, timeout), stream=True, allow_redirects=True,
                          headers={"User-Agent": _UA, "Accept-Language": "en,hi;q=0.8"}) as r:
            if r.status_code >= 400:
                return ""
            ctype = r.headers.get("Content-Type", "")
            if "html" not in ctype and "text" not in ctype:
                return ""
            chunks, got = [], 0
            for c in r.iter_content(65536):
                chunks.append(c)
                got += len(c)
                if got >= max_bytes:
                    break
            raw = b"".join(chunks)
            enc = r.encoding if r.encoding and r.encoding.lower() != "iso-8859-1" else "utf-8"
        html = raw.decode(enc, errors="replace")
    except Exception:
        return ""
    return html_to_text(html)


def html_to_text(html: str) -> str:
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))
    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception:
        soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg", "nav", "header", "footer", "aside",
                     "form", "iframe", "button", "select", "template"]):
        tag.decompose()
    root = soup.find("article") or soup.find("main") or soup.body or soup
    blocks = []
    for el in root.find_all(["h1", "h2", "h3", "p", "li", "td", "blockquote", "pre"]):
        t = " ".join(el.get_text(" ", strip=True).split())
        if len(t) >= 25 or (el.name in ("h1", "h2", "h3") and len(t) >= 4):
            blocks.append(t)
    if not blocks:
        t = " ".join(root.get_text(" ", strip=True).split())
        return t[:20000]
    # Drop exact repeats (menus, cookie banners that slipped through).
    seen, out = set(), []
    for b in blocks:
        if b not in seen:
            seen.add(b)
            out.append(b)
    return "\n".join(out)[:40000]


def _terms(text: str) -> list[str]:
    return [w for w in re.findall(r"[\wऀ-ॿ]+", (text or "").lower())
            if (len(w) > 2 or not w.isascii()) and w not in _STOP]


def _passages(text: str, size: int = 420) -> list[str]:
    out, cur = [], ""
    for para in text.split("\n"):
        if len(cur) + len(para) + 1 <= size:
            cur = (cur + " " + para).strip()
        else:
            if cur:
                out.append(cur)
            while len(para) > size * 1.6:
                cut = para.rfind(". ", 0, size)
                cut = cut + 1 if cut > size // 3 else size
                out.append(para[:cut].strip())
                para = para[cut:].strip()
            cur = para
    if cur:
        out.append(cur)
    return out


def best_passages(query: str, docs: list[tuple[str, str]], k: int = 6, per_doc: int = 2) -> list[tuple[str, str]]:
    """[(source, passage)] ranked by a BM25-style match with the question."""
    q = list(dict.fromkeys(_terms(query)))
    if not q:
        return []
    cands = []
    for src, text in docs:
        for p in _passages(text):
            cands.append((src, p, _terms(p)))
    if not cands:
        return []
    n = len(cands)
    df = {t: sum(1 for _, _, ts in cands if t in ts) for t in q}
    avg = sum(len(ts) for _, _, ts in cands) / n or 1.0
    scored = []
    for i, (src, p, ts) in enumerate(cands):
        if not ts:
            continue
        s = 0.0
        for t in q:
            tf = ts.count(t)
            if tf:
                idf = math.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5))
                s += idf * tf * 2.2 / (tf + 1.2 * (0.25 + 0.75 * len(ts) / avg))
        if re.search(r"\d", p):
            s *= 1.1               # facts usually carry numbers or dates
        scored.append((s, i))
    scored.sort(reverse=True)
    per: dict[str, int] = {}
    out = []
    for s, i in scored:
        if s <= 0 or len(out) >= k:
            break
        src, p, _ = cands[i]
        if per.get(src, 0) >= per_doc:
            continue
        per[src] = per.get(src, 0) + 1
        out.append((src, p))
    return out


# ── the pipeline ─────────────────────────────────────────────────────────────

def _domain(url: str) -> str:
    try:
        return urlparse(url).netloc.replace("www.", "")
    except Exception:
        return url[:40]


def research(query: str, mode: str = "search", deadline: float = 14.0, read_pages: bool | None = None) -> str:
    """Look it up and return a [WEB_RESULTS] block for the brain."""
    query = " ".join((query or "").split())
    if not query:
        return "No query given."
    mode = (mode or "search").lower()
    key = (query.lower(), mode)
    with _cache_lock:
        hit = _cache.get(key)
        if hit and time.monotonic() - hit[0] < _CACHE_S:
            return hit[1]
    c = cfg()
    provider = str(c.get("provider") or "auto").lower()
    n = 8
    news = mode == "news"
    if read_pages is None:
        read_pages = bool(c.get("read_pages", True))
    pages = max(0, min(6, int(c.get("pages", 3) or 3)))
    t_end = time.monotonic() + deadline
    answers: list[tuple[str, str]] = []        # (label, text)
    rows: list[dict] = []
    errors: list[str] = []

    pool = ThreadPoolExecutor(max_workers=8, thread_name_prefix="websearch")
    try:
        futs = {}
        if provider != "duckduckgo" and c.get("google_ai", True):
            futs[pool.submit(_google_ai, query if not news else f"latest news: {query}")] = "google_ai"
        if provider == "tavily" and c.get("tavily_key"):
            futs[pool.submit(_tavily, query, c["tavily_key"], 6)] = "tavily"
        elif provider == "brave" and c.get("brave_key"):
            futs[pool.submit(_brave, query, c["brave_key"], n)] = "brave"
        elif provider == "serper" and c.get("serper_key"):
            futs[pool.submit(_serper, query, c["serper_key"], n, news)] = "serper"
        elif provider == "searxng" and c.get("searxng_url"):
            futs[pool.submit(_searxng, query, c["searxng_url"], n, news)] = "searxng"
        else:
            futs[pool.submit(_ddgs_text, query, n, news)] = "ddgs"
        if not news:
            futs[pool.submit(_wikipedia, query)] = "wikipedia"
        done, _ = wait(futs, timeout=max(1.0, t_end - time.monotonic() - (4 if read_pages else 0)))
        for f in done:
            kind = futs[f]
            try:
                res = f.result()
            except Exception as e:
                errors.append(f"{kind}: {str(e)[:120]}")
                continue
            if kind == "google_ai" and res:
                answers.append(("Google AI answer (Gemini with Google Search)", res))
            elif kind == "wikipedia" and res:
                answers.append(("Encyclopaedia", res))
            elif kind in ("tavily", "serper", "searxng"):
                ans, rs = res
                if ans:
                    answers.append((f"{kind.title()} answer", ans))
                rows.extend(rs)
            elif kind in ("ddgs", "brave"):
                rows.extend(res)
        # A keyed service failed: fall back to the free meta-search.
        if not rows and provider not in ("auto", "google_ai") and time.monotonic() < t_end - 3:
            try:
                rows = _ddgs_text(query, n, news)
            except Exception as e:
                errors.append(f"ddgs: {str(e)[:120]}")
        rows = [r for r in rows if r.get("url") and not any(d in r["url"] for d in _SKIP_DOMAINS)]

        passages: list[tuple[str, str]] = []
        docs = [(_domain(r["url"]), r["content"]) for r in rows if r.get("content")]
        if read_pages and pages and rows and time.monotonic() < t_end - 1.5:
            targets = [r["url"] for r in rows if not r.get("content")][:pages + 1]
            pf = {pool.submit(fetch_page_text, u, min(7.0, t_end - time.monotonic())): u for u in targets}
            pdone, _ = wait(pf, timeout=max(0.5, t_end - time.monotonic()))
            for f in pdone:
                try:
                    text = f.result()
                except Exception:
                    text = ""
                if text:
                    docs.append((_domain(pf[f]), text))
        if docs:
            passages = best_passages(query, docs, k=6)
    finally:
        pool.shutdown(wait=False, cancel_futures=True)

    if not answers and not rows:
        why = "; ".join(errors) if errors else "no results"
        return (f"[WEB_RESULTS for \"{query}\"] The web search found nothing ({why}). Tell the user "
                "you could not find it online right now; do not guess.")

    today = datetime.now().strftime("%A %d %B %Y")
    out = [f"[WEB_RESULTS for \"{query}\" — searched {today}]"]
    for label, text in answers:
        out.append(f"{label}: {text.strip()[:1500]}")
    if rows:
        out.append("Top results:")
        for i, r in enumerate(rows[:6], 1):
            date = f" ({r['date']})" if r.get("date") else ""
            snip = (r.get("snippet") or r.get("content") or "").strip().replace("\n", " ")
            out.append(f"{i}. {r.get('title', '').strip()} — {_domain(r['url'])}{date}\n   {snip[:260]}")
    if passages:
        out.append("Read from the pages:")
        for src, p in passages:
            out.append(f"[{src}] {p}")
    out.append("Answer from these results in your own words and name the source site briefly. "
               "If they do not answer the question, say so rather than guessing.")
    text = "\n".join(out)
    with _cache_lock:
        _cache[key] = (time.monotonic(), text)
        if len(_cache) > 64:
            for k in sorted(_cache, key=lambda k: _cache[k][0])[:16]:
                _cache.pop(k, None)
    return text
