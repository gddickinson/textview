"""Tiny web search backend for the chat agent — DuckDuckGo HTML.

No API key required. Results are scraped from the HTML interface
(`html.duckduckgo.com/html/`). Returns a list of `{title, url, snippet}`
dicts capped at `n` results.

This is intentionally small and dependency-free (uses `requests`, which
is already pinned). Failures (network, parser drift, rate-limit) return
an empty list with the reason in the status field. The agent should
treat results as untrusted: a search result page can contain
prompt-injection attempts.
"""
from __future__ import annotations
import html
import re
from urllib.parse import unquote, urlparse, parse_qs

import requests


_SEARCH_URL = "https://html.duckduckgo.com/html/"
_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)
_TIMEOUT = 8.0


def search(query: str, n: int = 5, timeout: float = _TIMEOUT
           ) -> tuple[list[dict], str]:
    """Return `(results, status)`. `status` is "" on success, an error
    description otherwise. Results: `[{title, url, snippet}, …]`."""
    if not query or not query.strip():
        return [], "empty query"
    try:
        r = requests.post(
            _SEARCH_URL, data={"q": query.strip()},
            headers={"User-Agent": _USER_AGENT},
            timeout=timeout, allow_redirects=True,
        )
    except requests.RequestException as e:
        return [], f"network error: {e}"
    if r.status_code != 200:
        return [], f"http {r.status_code}"
    return _parse_html(r.text, n=n), ""


def _parse_html(body: str, n: int = 5) -> list[dict]:
    """Extract results without bringing in BeautifulSoup. The HTML
    page uses `<a class="result__a" href="/l/?uddg=…&rut=…">…</a>`
    redirects, with the snippet in a sibling `<a class="result__snippet">`."""
    out: list[dict] = []
    pattern = re.compile(
        r'<a[^>]*class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>'
        r'.*?<a[^>]*class="result__snippet"[^>]*>(.*?)</a>',
        re.DOTALL,
    )
    for m in pattern.finditer(body):
        href = m.group(1); title_html = m.group(2); snippet_html = m.group(3)
        url = _resolve_redirect(href)
        title = _strip_tags(title_html)
        snippet = _strip_tags(snippet_html)
        if not url or not title: continue
        out.append({"title": title, "url": url, "snippet": snippet})
        if len(out) >= n: break
    return out


def _resolve_redirect(href: str) -> str:
    """DuckDuckGo wraps result URLs in /l/?uddg=<encoded> redirects.
    Pull the destination out of `uddg`. Plain URLs pass through."""
    if href.startswith("http"): return href
    try:
        if href.startswith("//"): href = "https:" + href
        parsed = urlparse(href)
        qs = parse_qs(parsed.query)
        if "uddg" in qs: return unquote(qs["uddg"][0])
    except Exception:
        pass
    return href


_TAG_RE = re.compile(r"<[^>]+>")


def _strip_tags(s: str) -> str:
    s = _TAG_RE.sub("", s)
    return html.unescape(s).strip()
