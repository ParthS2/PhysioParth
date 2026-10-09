"""Deterministic on-page SEO checks. No API key needed."""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field

from bs4 import BeautifulSoup

from . import compliance
from .crawler import Page

LOCAL_SCHEMA_TYPES = {"physiotherapy", "medicalbusiness", "medicalclinic", "localbusiness", "physician", "healthandbeautybusiness"}


@dataclass
class Issue:
    severity: str  # "high" | "medium" | "low"
    message: str


@dataclass
class PageReport:
    url: str
    status: int
    title: str = ""
    meta_description: str = ""
    h1: list[str] = field(default_factory=list)
    word_count: int = 0
    schema_types: list[str] = field(default_factory=list)
    issues: list[Issue] = field(default_factory=list)
    compliance: list[compliance.Flag] = field(default_factory=list)
    text: str = ""  # visible text, passed to Claude for rewrites

    @property
    def score(self) -> int:
        penalty = {"high": 15, "medium": 7, "low": 3}
        return max(0, 100 - sum(penalty[i.severity] for i in self.issues))


def _schema_types(soup: BeautifulSoup) -> list[str]:
    types: list[str] = []

    def walk(node):
        if isinstance(node, dict):
            t = node.get("@type")
            if isinstance(t, str):
                types.append(t)
            elif isinstance(t, list):
                types.extend(x for x in t if isinstance(x, str))
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            walk(json.loads(tag.string or ""))
        except json.JSONDecodeError:
            types.append("INVALID_JSON_LD")
    return types


def audit_page(page: Page) -> PageReport:
    rep = PageReport(url=page.url, status=page.status)
    if page.status != 200:
        rep.issues.append(Issue("high", f"Page returned HTTP {page.status or 'error'} {page.error}".strip()))
        return rep

    soup = BeautifulSoup(page.html, "html.parser")
    add = lambda sev, msg: rep.issues.append(Issue(sev, msg))

    # Title
    rep.title = (soup.title.string or "").strip() if soup.title else ""
    if not rep.title:
        add("high", "Missing <title>.")
    elif len(rep.title) < 30:
        add("medium", f"Title is short ({len(rep.title)} chars); aim for 30-60 with service + location.")
    elif len(rep.title) > 60:
        add("low", f"Title is long ({len(rep.title)} chars); Google truncates around 60.")

    # Meta description
    md = soup.find("meta", attrs={"name": "description"})
    rep.meta_description = (md.get("content") or "").strip() if md else ""
    if not rep.meta_description:
        add("high", "Missing meta description.")
    elif not 70 <= len(rep.meta_description) <= 160:
        add("low", f"Meta description is {len(rep.meta_description)} chars; aim for 70-160.")

    # Headings
    rep.h1 = [h.get_text(" ", strip=True) for h in soup.find_all("h1")]
    if not rep.h1:
        add("high", "No <h1> heading.")
    elif len(rep.h1) > 1:
        add("low", f"{len(rep.h1)} <h1> tags; use one main heading per page.")

    # Indexability
    robots = soup.find("meta", attrs={"name": "robots"})
    if robots and "noindex" in (robots.get("content") or "").lower():
        add("high", "Page is set to noindex; it will not appear in Google.")
    if not soup.find("link", rel="canonical"):
        add("low", "No canonical link tag.")

    # Mobile + language
    if not soup.find("meta", attrs={"name": "viewport"}):
        add("high", "No viewport meta tag; page may not be mobile-friendly.")
    html_tag = soup.find("html")
    if not (html_tag and html_tag.get("lang")):
        add("low", "Missing lang attribute on <html>.")

    # Images
    imgs = soup.find_all("img")
    no_alt = [i for i in imgs if not (i.get("alt") or "").strip()]
    if no_alt:
        add("medium", f"{len(no_alt)} of {len(imgs)} images have no alt text.")

    # Social sharing
    if not soup.find("meta", property="og:title"):
        add("low", "No Open Graph tags; links shared on social media will look plain.")

    # Structured data
    rep.schema_types = _schema_types(soup)
    if "INVALID_JSON_LD" in rep.schema_types:
        add("medium", "JSON-LD structured data block fails to parse.")
    if not LOCAL_SCHEMA_TYPES & {t.lower() for t in rep.schema_types}:
        add("medium", "No LocalBusiness/MedicalBusiness/Physiotherapy schema; this helps local search and the map pack.")

    # Content depth
    for t in soup(["script", "style", "noscript", "nav", "footer", "header"]):
        t.decompose()
    rep.text = " ".join(soup.get_text(" ").split())
    rep.word_count = len(rep.text.split())
    if rep.word_count < 300:
        add("medium", f"Thin content ({rep.word_count} words); service pages usually need 500+ to rank.")

    rep.compliance = compliance.check(" ".join([rep.title, rep.meta_description, rep.text]))
    return rep


def audit_site(pages: list[Page]) -> list[PageReport]:
    reports = [audit_page(p) for p in pages]
    for attr, label in (("title", "title"), ("meta_description", "meta description")):
        groups = defaultdict(list)
        for r in reports:
            if getattr(r, attr):
                groups[getattr(r, attr)].append(r)
        for dupes in groups.values():
            if len(dupes) > 1:
                for r in dupes:
                    r.issues.append(Issue("medium", f"Duplicate {label} shared with {len(dupes) - 1} other page(s)."))
    return reports


def to_markdown(reports: list[PageReport], site: str) -> str:
    ok = [r for r in reports if r.status == 200]
    avg = round(sum(r.score for r in ok) / len(ok)) if ok else 0
    lines = [f"# SEO audit: {site}", "", f"Pages checked: {len(reports)} · Average score: **{avg}/100**", ""]

    flagged = [r for r in reports if r.compliance]
    if flagged:
        lines += ["## Advertising-compliance flags (review before publishing)", ""]
        for r in flagged:
            for f in r.compliance:
                lines.append(f"- `{r.url}`: **{f.rule}**, \"{f.match}\". {f.why}")
        lines.append("")

    lines += ["## Pages, worst first", ""]
    for r in sorted(reports, key=lambda r: r.score):
        lines += [f"### {r.url} ({r.score}/100)", ""]
        if r.status == 200:
            lines += [f"- Title: {r.title or '_missing_'}", f"- Meta description: {r.meta_description or '_missing_'}",
                      f"- H1: {' | '.join(r.h1) or '_missing_'}", f"- Words: {r.word_count}",
                      f"- Schema: {', '.join(r.schema_types) or '_none_'}", ""]
        for sev in ("high", "medium", "low"):
            for i in r.issues:
                if i.severity == sev:
                    lines.append(f"- [{sev.upper()}] {i.message}")
        lines.append("")
    return "\n".join(lines)
