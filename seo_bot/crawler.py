"""Fetch pages from a site: sitemap first, then same-domain link crawl as a fallback."""

from __future__ import annotations

import gzip
import urllib.error
import urllib.request
import urllib.robotparser
import xml.etree.ElementTree as ET
from collections import deque
from dataclasses import dataclass, field
from urllib.parse import urldefrag, urljoin, urlparse

from bs4 import BeautifulSoup

USER_AGENT = "PhysioParthSEOBot/1.0 (+site owner audit)"
TIMEOUT = 20
SKIP_EXTENSIONS = (".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".pdf", ".zip", ".mp4", ".mp3", ".css", ".js", ".ico")


@dataclass
class Page:
    url: str
    status: int
    html: str = ""
    final_url: str = ""
    headers: dict = field(default_factory=dict)
    error: str = ""


def fetch(url: str) -> Page:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept-Encoding": "gzip"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            body = resp.read()
            if resp.headers.get("Content-Encoding") == "gzip":
                body = gzip.decompress(body)
            charset = resp.headers.get_content_charset() or "utf-8"
            return Page(
                url=url,
                status=resp.status,
                html=body.decode(charset, errors="replace"),
                final_url=resp.geturl(),
                headers={k.lower(): v for k, v in resp.headers.items()},
            )
    except urllib.error.HTTPError as e:
        return Page(url=url, status=e.code, error=str(e))
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        return Page(url=url, status=0, error=str(e))


def _normalize(url: str) -> str:
    url, _ = urldefrag(url)
    return url.rstrip("/") or url


def _same_site(url: str, root: str) -> bool:
    a, b = urlparse(url).netloc.lower(), urlparse(root).netloc.lower()
    return a.removeprefix("www.") == b.removeprefix("www.")


def sitemap_urls(root: str, limit: int) -> list[str]:
    """Read sitemap.xml (and nested sitemap indexes) for page URLs."""
    queue, seen, urls = deque([urljoin(root, "/sitemap.xml")]), set(), []
    while queue and len(urls) < limit:
        sm = queue.popleft()
        if sm in seen:
            continue
        seen.add(sm)
        page = fetch(sm)
        if page.status != 200 or not page.html.strip():
            continue
        try:
            tree = ET.fromstring(page.html.encode("utf-8"))
        except ET.ParseError:
            continue
        for loc in tree.iter():
            if not loc.tag.endswith("loc") or not loc.text:
                continue
            target = loc.text.strip()
            if tree.tag.endswith("sitemapindex"):
                queue.append(target)
            elif _same_site(target, root):
                urls.append(target)
    return urls[:limit]


def crawl(root: str, limit: int = 50) -> list[Page]:
    """Return up to `limit` HTML pages from the site, honouring robots.txt."""
    if not urlparse(root).scheme:
        root = "https://" + root
    robots = urllib.robotparser.RobotFileParser(urljoin(root, "/robots.txt"))
    try:
        robots.read()
    except OSError:
        robots = None

    def allowed(u: str) -> bool:
        return robots is None or robots.can_fetch(USER_AGENT, u)

    queue = deque([root, *sitemap_urls(root, limit)])
    seen: set[str] = set()
    pages: list[Page] = []
    while queue and len(pages) < limit:
        url = queue.popleft()
        key = _normalize(url)
        if key in seen or url.lower().endswith(SKIP_EXTENSIONS) or not allowed(url):
            continue
        seen.add(key)
        page = fetch(url)
        if page.status == 200 and "html" not in page.headers.get("content-type", "text/html"):
            continue
        pages.append(page)
        if page.status != 200:
            continue
        for a in BeautifulSoup(page.html, "html.parser").find_all("a", href=True):
            link = urljoin(page.final_url or url, a["href"])
            if link.startswith("http") and _same_site(link, root) and _normalize(link) not in seen:
                queue.append(link)
    return pages
