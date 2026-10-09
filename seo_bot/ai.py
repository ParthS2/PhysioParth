"""Claude-powered SEO help: page rewrites, keyword research, drafts, and chat."""

from __future__ import annotations

import sys

import anthropic

from .audit import PageReport

MODEL = "claude-opus-5-5"
WEB_SEARCH = {"type": "web_search_20260209", "name": "web_search", "max_uses": 8}
MAX_PAUSE_RESUMES = 5

SYSTEM_TEMPLATE = """You are the SEO assistant for {name}, a physiotherapy practice.

Practice profile:
- Website: {site}
- Clinician: {clinician}
- Location / service area: {location}
- Audience: {audience}
- Services: {services}
- Tone: {tone}
- Advertising rules that apply: {regulators}

How to work:
- Give specific, ready-to-paste output (exact titles, meta descriptions, headings, JSON-LD, copy), not generic SEO advice.
- Prioritise by likely impact for a small local clinic: local search and Google Business Profile, service pages that match how lifters actually search, then content.
- Titles 30-60 characters, meta descriptions 70-160 characters. Put the service and location early when the page is local.
- Every piece of copy must comply with the advertising rules above: no patient testimonials, no guaranteed or "cure" outcomes, no unverifiable superlatives ("best physio in..."), no "specialist" unless the profile says the clinician holds that title, no fear-based or pressuring offers. When existing copy breaks one of these, say so and give a compliant rewrite.
- Health claims must be accurate and conservative. Do not invent credentials, years of experience, prices, addresses, or results. Where a fact is needed and not in the profile, leave a clearly marked placeholder like [ADD CLINIC ADDRESS].
- When you research keywords with web search, say which results you saw; do not invent search-volume numbers. Describe demand qualitatively unless a source gives a figure.
"""


def system_prompt(profile: dict) -> str:
    p = {k: (", ".join(v) if isinstance(v, list) else v) for k, v in profile.items()}
    return SYSTEM_TEMPLATE.format(**{k: p.get(k, "[not set]") for k in
                                     ("name", "site", "clinician", "location", "audience", "services", "tone", "regulators")})


class SEOAssistant:
    def __init__(self, profile: dict):
        self.client = anthropic.Anthropic()
        self.system = system_prompt(profile)

    def _run(self, messages: list[dict], use_web: bool = False, out=sys.stdout) -> str:
        """Stream one turn to `out`, resuming server-tool pauses. Returns the text and appends to `messages`."""
        tools = [WEB_SEARCH] if use_web else []
        chunks: list[str] = []
        for _ in range(MAX_PAUSE_RESUMES + 1):
            with self.client.beta.messages.stream(
                model=MODEL,
                max_tokens=64000,
                system=self.system,
                messages=messages,
                tools=tools,
                output_config={"effort": "high"},
                cache_control={"type": "ephemeral"},
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
            ) as stream:
                for text in stream.text_stream:
                    out.write(text)
                    out.flush()
                    chunks.append(text)
                msg = stream.get_final_message()
            messages.append({"role": "assistant", "content": msg.content})
            if msg.stop_reason == "refusal":
                out.write("\n[The model declined this request. Try rephrasing it.]\n")
                break
            if msg.stop_reason == "max_tokens":
                out.write("\n[Output hit the length limit and was cut off.]\n")
            if msg.stop_reason != "pause_turn":
                break
        out.write("\n")
        return "".join(chunks)

    def fix_page(self, report: PageReport, out=sys.stdout) -> str:
        issues = "\n".join(f"- [{i.severity}] {i.message}" for i in report.issues) or "- none found"
        flags = "\n".join(f"- {f.rule}: \"{f.match}\"" for f in report.compliance) or "- none found"
        prompt = f"""Improve this page's SEO.

URL: {report.url}
Current title: {report.title or '(missing)'}
Current meta description: {report.meta_description or '(missing)'}
Current H1: {' | '.join(report.h1) or '(missing)'}
Structured data types: {', '.join(report.schema_types) or '(none)'}
Word count: {report.word_count}

Automated audit issues:
{issues}

Possible advertising-compliance flags (heuristic, may be false positives):
{flags}

Page text:
<page_text>
{report.text[:30000]}
</page_text>

Return, in this order:
1. The primary search query this page should target, and two or three secondary ones.
2. New title, meta description, and H1 (give 2 options each, mark your pick).
3. Compliance: for each flag, say whether it is a real problem and give the compliant rewrite.
4. Content gaps: the sections or questions a lifter searching that query expects but the page doesn't answer.
5. JSON-LD structured data to paste into the page, if it is missing or wrong.
6. Internal links to add, and any other fixes from the audit, most important first."""
        return self._run([{"role": "user", "content": prompt}], out=out)

    def keywords(self, topic: str, out=sys.stdout) -> str:
        prompt = f"""Do keyword research for: {topic}

Use web search to look at what currently ranks for the main queries in our location, and at the "People also ask" style questions around them.

Return:
1. A keyword cluster table: query, search intent (informational / local-commercial / transactional), difficulty for a small clinic (low/medium/high, with the reason), and which page on our site should target it (existing or new).
2. The five quickest wins and why.
3. Content ideas that would earn links or shares from the lifting community.
4. Google Business Profile categories, services and post ideas that support these terms."""
        return self._run([{"role": "user", "content": prompt}], use_web=True, out=out)

    def write(self, topic: str, kind: str = "blog post", out=sys.stdout) -> str:
        prompt = f"""Write a {kind} for our website on: {topic}

Requirements:
- Start with a metadata block: target query, title tag, meta description, URL slug.
- Then the full draft in Markdown with one H1 and logical H2/H3s, written for lifters, evidence-informed and plain-spoken.
- Include an FAQ section of 3-5 real questions people search, and FAQPage JSON-LD for it.
- Include a clear, non-pressuring call to action to book an assessment.
- Note where to add internal links with [LINK: page description].
- Finish with a compliance check listing anything I should verify before publishing."""
        return self._run([{"role": "user", "content": prompt}], use_web=True, out=out)

    def chat(self, context: str = "") -> None:
        messages: list[dict] = []
        if context:
            messages.append({"role": "user", "content": f"Here is my latest site audit for context:\n\n{context}"})
            messages.append({"role": "assistant", "content": "Got it. I have the audit loaded. What do you want to work on?"})
        print("SEO assistant ready. Type your question, or 'quit' to exit.\n")
        while True:
            try:
                q = input("you> ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                return
            if q.lower() in {"quit", "exit", "q"}:
                return
            if not q:
                continue
            messages.append({"role": "user", "content": q})
            print("\nbot> ", end="")
            self._run(messages, use_web=True)
            print()
