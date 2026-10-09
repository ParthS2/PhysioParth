# PhysioParth SEO bot

A command-line SEO assistant for physioparth.com. It crawls the live site, checks every page for SEO problems and advertising-compliance risks, and uses Claude to write fixes, research keywords and draft new pages.

## Setup

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...   # only needed for the AI commands
```

Then open `profile.toml` and fill in every `[ADD ...]` placeholder: your credentials, location and services. The bot won't invent these facts. Anything you leave blank shows up as a placeholder in its output.

## Commands

| Command | What it does | Needs API key |
|---|---|---|
| `python -m seo_bot audit` | Crawls the site (sitemap + links, respects robots.txt), scores each page and flags compliance risks | No |
| `python -m seo_bot fix <url>` | Builds a rewrite plan for one page: target queries, titles, meta descriptions, compliant copy fixes, content gaps, JSON-LD and internal links | Yes |
| `python -m seo_bot keywords "<topic>"` | Researches keywords with live web search and returns a keyword cluster, quick wins and Google Business Profile ideas | Yes |
| `python -m seo_bot write "<topic>" [--kind "service page"]` | Writes a full draft with metadata, FAQ and FAQPage schema, followed by a compliance checklist | Yes |
| `python -m seo_bot chat` | Starts an open-ended conversation that uses your latest audit as context | Yes |

Every command saves its output to `reports/YYYY-MM-DD-*.md`.

## What the audit checks

- Title and meta description: present, the right length, not duplicated across pages
- One H1 per page, canonical tag, noindex, viewport, `lang` attribute
- Image alt text and Open Graph tags
- Structured data: whether the page has LocalBusiness, MedicalBusiness or Physiotherapy schema, and whether the JSON-LD parses
- Thin content (under 300 words)
- **Advertising-compliance flags**: testimonials, guaranteed outcomes, "cure" language, superlatives ("best physio"), "specialist", free or discount offers, and fear-based copy

The compliance flags come from pattern matching. They tell you what to review and are not legal advice. Check flagged copy against the CPO advertising standard before you change it.

## Suggested workflow

1. Run `audit` and fix the HIGH items first.
2. For your 3-5 most important service pages, run `fix <url>`.
3. Run `keywords` for each service, then `write` the missing pages it suggests.
4. Re-run `audit` monthly.

## Tests

```bash
python -m unittest discover -s tests -t .
```

## Model

The AI commands use Claude Opus 5.5 at high effort, with streaming and prompt caching. If the model declines a request, an automatic server-side fallback retries it. Change `MODEL` in `seo_bot/ai.py` if you want something cheaper.
