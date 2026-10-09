"""PhysioParth SEO bot.

    python -m seo_bot audit                       # crawl + rule-based audit (no API key needed)
    python -m seo_bot fix https://physioparth.com/some-page
    python -m seo_bot keywords "lower back pain deadlift"
    python -m seo_bot write "returning to squats after a knee injury"
    python -m seo_bot chat                        # ask anything; uses your latest audit as context
"""

from __future__ import annotations

import argparse
import datetime as dt
import io
import sys
import tomllib
from pathlib import Path

from . import audit, crawler

ROOT = Path(__file__).resolve().parent.parent
REPORTS = ROOT / "reports"


def load_profile(path: Path) -> dict:
    with open(path, "rb") as f:
        return tomllib.load(f)


def save(name: str, text: str) -> Path:
    REPORTS.mkdir(exist_ok=True)
    path = REPORTS / f"{dt.date.today().isoformat()}-{name}.md"
    path.write_text(text, encoding="utf-8")
    return path


def slug(s: str) -> str:
    return "-".join("".join(c if c.isalnum() else " " for c in s.lower()).split())[:60] or "page"


class Tee(io.TextIOBase):
    """Stream to the terminal while keeping a copy to save."""

    def __init__(self):
        self.buf = io.StringIO()

    def write(self, s):
        sys.stdout.write(s)
        return self.buf.write(s)

    def flush(self):
        sys.stdout.flush()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="seo_bot", description="SEO assistant for PhysioParth")
    ap.add_argument("--profile", type=Path, default=ROOT / "profile.toml")
    sub = ap.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("audit", help="crawl the site and run rule-based SEO + compliance checks")
    a.add_argument("--site", help="defaults to `site` in profile.toml")
    a.add_argument("--max-pages", type=int, default=50)

    f = sub.add_parser("fix", help="AI rewrite plan for one page")
    f.add_argument("url")

    k = sub.add_parser("keywords", help="AI keyword research with live web search")
    k.add_argument("topic")

    w = sub.add_parser("write", help="AI draft of an SEO page or blog post")
    w.add_argument("topic")
    w.add_argument("--kind", default="blog post", help='e.g. "service page", "blog post", "FAQ page"')

    sub.add_parser("chat", help="interactive SEO assistant")

    args = ap.parse_args(argv)
    profile = load_profile(args.profile)

    if args.cmd == "audit":
        site = args.site or profile["site"]
        print(f"Crawling {site} (up to {args.max_pages} pages)...", file=sys.stderr)
        pages = crawler.crawl(site, args.max_pages)
        if not pages:
            print("No pages fetched. Check the URL and your network.", file=sys.stderr)
            return 1
        reports = audit.audit_site(pages)
        md = audit.to_markdown(reports, site)
        print(md)
        print(f"\nSaved to {save('audit', md)}", file=sys.stderr)
        return 0

    from .ai import SEOAssistant  # imported here so `audit` works without the SDK configured

    bot = SEOAssistant(profile)
    tee = Tee()
    if args.cmd == "fix":
        page = crawler.fetch(args.url)
        bot.fix_page(audit.audit_page(page), out=tee)
        name = f"fix-{slug(args.url.split('://')[-1])}"
    elif args.cmd == "keywords":
        bot.keywords(args.topic, out=tee)
        name = f"keywords-{slug(args.topic)}"
    elif args.cmd == "write":
        bot.write(args.topic, args.kind, out=tee)
        name = f"draft-{slug(args.topic)}"
    else:
        latest = sorted(REPORTS.glob("*-audit.md"))
        bot.chat(latest[-1].read_text(encoding="utf-8") if latest else "")
        return 0
    print(f"\nSaved to {save(name, tee.buf.getvalue())}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
