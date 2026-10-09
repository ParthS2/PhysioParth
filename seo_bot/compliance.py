"""Heuristic flags for health-advertising risks (CPO Ontario / AHPRA style rules).

These are prompts for human review, not legal determinations. SEO copy for a
regulated clinician has to rank *and* stay within the advertising standard, so
the bot runs these on every page and on everything it drafts.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class Flag:
    rule: str
    match: str
    why: str


RULES: list[tuple[str, str, str]] = [
    (
        "testimonial",
        r"\b(testimonials?|reviews? from (our )?(clients|patients)|what (our )?(clients|patients) say|5[- ]star reviews?)\b",
        "Both CPO and AHPRA restrict patient testimonials in advertising.",
    ),
    (
        "guarantee",
        r"\b(guarantee[sd]?|100% (results|recovery|success)|permanent(ly)? (fix|cure)|never (hurt|get injured) again)\b",
        "Claims of guaranteed outcomes create unreasonable expectations.",
    ),
    (
        "cure",
        r"\b(cures?|cured|eliminates? pain|pain[- ]free forever)\b",
        "'Cure' language overstates what treatment can promise.",
    ),
    (
        "superlative",
        r"\b(best|top[- ]rated|#\s?1|number one|leading|world[- ]class|most (trusted|experienced))\s+(physio|physiotherapist|clinic|in|for)\b",
        "Comparative or superlative claims that can't be objectively verified.",
    ),
    (
        "specialist",
        r"\bspeciali[sz]t\b|\bspecialising in\b|\bspecializing in\b",
        "Use of 'specialist' is a protected or restricted claim in several jurisdictions; check your registration allows it.",
    ),
    (
        "inducement",
        r"\b(free (assessment|session|consult(ation)?)|\d+% off|limited[- ]time offer|book now and save)\b",
        "Discounts and free offers need clear terms and must not pressure people into unnecessary treatment.",
    ),
    (
        "fear",
        r"\b(before it'?s too late|don'?t risk|ruin your (lifts|training|career))\b",
        "Fear-based messaging can be read as encouraging unnecessary use of services.",
    ),
]

_COMPILED = [(name, re.compile(rx, re.I), why) for name, rx, why in RULES]


def check(text: str) -> list[Flag]:
    flags, seen = [], set()
    for name, rx, why in _COMPILED:
        for m in rx.finditer(text):
            key = (name, m.group(0).lower())
            if key not in seen:
                seen.add(key)
                flags.append(Flag(name, m.group(0), why))
    return flags
