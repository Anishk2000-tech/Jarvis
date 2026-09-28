"""Web research: when to search, reading pages, ranking passages, the pipeline."""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from core import websearch


@pytest.mark.parametrize("text", [
    "What is the petrol price in Delhi today?", "who won the match yesterday",
    "What's the latest news about the iPhone?", "Who is the current prime minister of Japan?",
    "aaj sone ka bhav kya hai", "आज की ताज़ा खबर क्या है?", "Is the new GTA released?",
])
def test_needs_fresh_info(text):
    assert websearch.needs_fresh_info(text)


@pytest.mark.parametrize("text", [
    "open youtube and play the latest song", "what's the weather today",
    "what is photosynthesis", "set a timer for 5 minutes", "tell me a joke",
])
def test_does_not_need_fresh_info(text):
    assert not websearch.needs_fresh_info(text)


@pytest.mark.parametrize("text", [
    "I don't know who that is.", "I'm not sure about the current price.",
    "As of my last update in 2023, the CEO was John.", "I cannot browse the internet.",
    "I don't have real-time information about that.", "मुझे नहीं पता।", "mujhe nahi pata",
])
def test_sounds_unsure(text):
    assert websearch.sounds_unsure(text)


@pytest.mark.parametrize("text", [
    "The capital of France is Paris.", "I know a good recipe for that.", "Not sure? Try the blue one.",
])
def test_sounds_sure(text):
    assert not websearch.sounds_unsure(text)


PAGE_A = """<html><head><title>Fuel</title><script>var x=1</script></head><body>
<nav>Home | News | Contact</nav>
<article><h1>Petrol and diesel prices today</h1>
<p>Petrol in Delhi costs Rs 94.77 per litre today, unchanged from yesterday, according to Indian Oil.</p>
<p>Diesel is priced at Rs 87.67 per litre in Delhi.</p>
<p>Prices are revised daily at 6 am based on international crude rates and exchange rates.</p></article>
<footer>Copyright 2026</footer></body></html>"""
PAGE_B = """<html><body><main><p>Cricket scores and live updates from around the world, every day.</p>
<p>The weather in Mumbai will be humid with light rain expected in the evening.</p></main></body></html>"""


@pytest.fixture
def web():
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            body = {"/fuel": PAGE_A, "/other": PAGE_B}.get(self.path)
            if body is None:
                self.send_response(404)
                self.end_headers()
                return
            b = body.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)
    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


def test_page_text_and_passages(web):
    text = websearch.fetch_page_text(web + "/fuel")
    assert "94.77" in text and "var x" not in text and "Home | News" not in text
    best = websearch.best_passages("petrol price in Delhi today",
                                   [("fuel.example", text), ("other.example", websearch.fetch_page_text(web + "/other"))])
    assert best and best[0][0] == "fuel.example" and "94.77" in best[0][1]


def test_research_pipeline(monkeypatch, web, tmp_path):
    from core import brain_config
    f = tmp_path / "api_keys.json"
    f.write_text(json.dumps({"search": {"provider": "auto", "google_ai": False}}), encoding="utf-8")
    monkeypatch.setattr(brain_config, "CONFIG_FILE", f)
    websearch._cache.clear()
    calls = []

    def fake_ddgs(query, n, news=False):
        calls.append((query, news))
        return [{"title": "Fuel prices today", "url": web + "/fuel", "snippet": "Petrol Rs 94.77", "date": "2026-09-28"},
                {"title": "Scores", "url": web + "/other", "snippet": "Cricket", "date": ""},
                {"title": "A video", "url": "https://www.youtube.com/watch?v=1", "snippet": "skip me"}]
    monkeypatch.setattr(websearch, "_ddgs_text", fake_ddgs)
    out = websearch.research("petrol price in Delhi today")
    assert out.startswith('[WEB_RESULTS for "petrol price in Delhi today"')
    assert "Top results:" in out and "Read from the pages:" in out
    assert "94.77" in out.split("Read from the pages:")[1]
    assert "youtube" not in out
    assert calls == [("petrol price in Delhi today", False)]
    # cached: no second search
    websearch.research("petrol price in Delhi today")
    assert len(calls) == 1


def test_research_uses_google_ai_and_keyed_services(monkeypatch, tmp_path):
    from core import brain_config
    f = tmp_path / "api_keys.json"
    f.write_text(json.dumps({"gemini_api_key": "k", "search": {"provider": "serper", "serper_key": "abc",
                                                                "read_pages": False}}), encoding="utf-8")
    monkeypatch.setattr(brain_config, "CONFIG_FILE", f)
    websearch._cache.clear()
    monkeypatch.setattr(websearch, "_google_ai", lambda q: "Google says: Rs 94.77 a litre.")
    seen = {}

    class R:
        ok = True
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {"answerBox": {"answer": "Rs 94.77"},
                    "organic": [{"title": "Fuel", "link": "https://fuel.example/x", "snippet": "Delhi petrol"}]}

    def fake_post(url, **kw):
        seen["url"], seen["headers"] = url, kw.get("headers")
        return R()
    monkeypatch.setattr(websearch.requests, "post", fake_post)
    out = websearch.research("petrol price in Delhi today")
    assert "Google AI answer" in out and "Google says" in out
    assert "Serper answer: Rs 94.77" in out and "fuel.example" in out
    assert seen["url"].endswith("/search") and seen["headers"]["X-API-KEY"] == "abc"


def test_research_reports_nothing(monkeypatch, tmp_path):
    from core import brain_config
    f = tmp_path / "api_keys.json"
    f.write_text(json.dumps({"search": {"google_ai": False}}), encoding="utf-8")
    monkeypatch.setattr(brain_config, "CONFIG_FILE", f)
    websearch._cache.clear()

    def boom(*a, **k):
        raise RuntimeError("offline")
    monkeypatch.setattr(websearch, "_ddgs_text", boom)
    monkeypatch.setattr(websearch, "_wikipedia", lambda q: "")
    out = websearch.research("who won the world cup yesterday")
    assert "found nothing" in out and "do not guess" in out
