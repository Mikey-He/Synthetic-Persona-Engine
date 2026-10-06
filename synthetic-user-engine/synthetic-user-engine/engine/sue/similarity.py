""""The most alike", computed by code and never by the model (engine-design.md 4.3).

Each element is compared with the task text word by word, through what he understands:
words he knows or reads in their everyday sense count as they are, a word he reads
another way counts by that reading, a fake word never counts. The more words shared
with the task, the more alike."""

from __future__ import annotations

import re
from typing import Any

from .persona import NONE, OTHER
from .words import Vocabulary, _variants

TOKEN = re.compile(r"[A-Za-z]+(?:'[A-Za-z]+)?")

# Words too common to say anything about a match. Placeholder, kept short on purpose.
STOP = {
    "a", "an", "the", "of", "for", "to", "and", "or", "in", "on", "at", "by", "with", "all", "this", "that",
    "is", "are", "be", "your", "you", "when", "during", "each", "from", "should", "only", "it", "its",
    "i", "i'm", "not", "no", "yes", "as", "if", "into", "per",
}


def task_words(task: str) -> set[str]:
    words: set[str] = set()
    for t in TOKEN.findall(task):
        if t.lower() not in STOP:
            words.update(_variants(t))
    return words


NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")


def number(text: str) -> str | None:
    """1,000 / $1000 / 80% / 80.0 -> "1000", "80": a number as the task or a field writes it."""
    m = NUMBER.search(str(text or ""))
    if not m:
        return None
    n = m.group(0).replace(",", "")
    return n[:-2] if n.endswith(".0") else n


def task_values(task: str) -> set[str]:
    """The numbers the task names (1,000 and 80 for Version A). Typing one of them into a
    field matches the task literally, even when the field's label shares no word with it."""
    return {number(m) for m in NUMBER.findall(task)} - {None}


def similarity(element: dict[str, Any], vocab: Vocabulary, task: set[str]) -> int:
    if element.get("harness"):
        return 0
    seen: set[str] = set()
    for h in vocab.rewrite(element.get("original") or "").hits:
        if h.level == NONE:
            continue
        text = h.gloss if h.level == OTHER and h.gloss else h.shown
        for t in TOKEN.findall(text):
            if t.lower() not in STOP and any(v in task for v in _variants(t)):
                seen.add(t.lower())
    return len(seen)
