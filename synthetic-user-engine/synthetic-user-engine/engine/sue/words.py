"""What this person sees in place of each word on screen (engine-design.md 4.1).

Order of precedence for any piece of text:
1. test harness words (I'm finished) and data (names, IDs, months) stay as they are;
2. word items from the persona card are shown the way the card says;
3. every other word follows the off-list rule: a common English word for his
   English level stays and counts as everyday meaning, anything else becomes a
   fake word. The blank card fakes every off-list word, the full card keeps them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .persona import KNOW, NONE, Persona

# ---- fake words ---------------------------------------------------------------

_CONSONANTS = "bdfgklmnprstvz"
_VOWELS = "aeiou"


def _imul(a: int, b: int) -> int:
    return ((a & 0xFFFFFFFF) * (b & 0xFFFFFFFF)) & 0xFFFFFFFF


def fake(word: str) -> str:
    """Same algorithm as fake() in tools/knowledge-workbench.html, so a fake word
    matches the card's "shown". Same length, same capitals, and the same word always
    turns into the same fake word."""
    h = 2166136261
    for ch in word:
        h = _imul(h ^ ord(ch), 16777619)
    out, pos = [], 0
    for i, ch in enumerate(word):
        if ch.isascii() and ch.isalpha():
            h = _imul(h ^ (i + 7), 2654435761)
            letters = _VOWELS if pos % 2 == 1 else _CONSONANTS
            c = letters[h % len(letters)]
            out.append(c.upper() if ch != ch.lower() else c)
            pos += 1
        else:
            out.append(ch)
            if ch in " /":
                pos = 0
    return "".join(out)


# ---- common English words -----------------------------------------------------

def _variants(token: str) -> list[str]:
    """The token and the simple base forms it may come from, so Budgets, pricing and
    labels count when budget, price and label are common."""
    t = token.lower()
    if t.endswith("'s"):
        t = t[:-2]
    out = [t]
    if t.endswith("ies") and len(t) > 4:
        out.append(t[:-3] + "y")
    if t.endswith("es") and len(t) > 3:
        out.append(t[:-2])
    if t.endswith("s") and len(t) > 3:
        out.append(t[:-1])
    if t.endswith("ing") and len(t) > 5:
        out += [t[:-3], t[:-3] + "e"]
    if t.endswith("ed") and len(t) > 4:
        out += [t[:-2], t[:-1]]
    return out


class CommonWords:
    """The words ranked within limit on the frequency list. Keeps the ranks of a longer
    list too, so the log can show how close each off-list word was to the limit."""

    def __init__(self, ranks: dict[str, int], limit: int):
        self.ranks = ranks
        self.limit = limit

    @classmethod
    def from_wordfreq(cls, limit: int, ranked: int = 100_000) -> "CommonWords":
        from wordfreq import top_n_list

        words = top_n_list("en", max(limit, ranked))
        return cls({w: i + 1 for i, w in enumerate(words)}, limit)

    @classmethod
    def from_words(cls, words: set[str]) -> "CommonWords":
        """A fixed list where every word counts as common. For tests."""
        return cls({w: 1 for w in words}, 1)

    def rank(self, token: str) -> int | None:
        found = [self.ranks[v] for v in _variants(token) if v in self.ranks]
        return min(found) if found else None

    def __contains__(self, token: str) -> bool:
        r = self.rank(token)
        return r is not None and r <= self.limit


# ---- rewriting ------------------------------------------------------------------

TOKEN = re.compile(r"[A-Za-z]+(?:'[A-Za-z]+)?")


@dataclass(frozen=True)
class Hit:
    """One word or phrase on screen and how this person sees it."""

    original: str
    shown: str
    level: str  # understands / everyday / other / none
    source: str  # item / offlist / data / harness
    item_id: str | None = None
    gloss: str = ""
    rank: int | None = None  # off-list words: place on the frequency list, for the log


@dataclass
class Rewritten:
    text: str
    hits: list[Hit] = field(default_factory=list)


def _match_case(shown: str, matched: str) -> str:
    """Puts the capitals of the text on screen onto the shown word. Shown words have the
    same length as the original, so this works letter by letter."""
    if len(shown) != len(matched):
        return shown
    return "".join(s.upper() if m.isupper() else s.lower() if m.islower() else s for s, m in zip(shown, matched))


def _bounded(phrase: str, flags: int = 0) -> re.Pattern[str]:
    return re.compile(r"(?<![A-Za-z])" + re.escape(phrase) + r"(?![A-Za-z])", flags)


EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")


class Vocabulary:
    """Rewrites any text the way one persona sees it."""

    def __init__(
        self,
        persona: Persona,
        common: CommonWords,
        data_terms: list[str],
        harness_terms: list[str],
        force_fake: list[str],
        ui_words: list[str] = (),
    ):
        self.persona = persona
        self.common = common
        self.force_fake = {w.lower() for w in force_fake}
        self.ui_words = {w.lower() for w in ui_words}
        keep = [(t, "harness") for t in harness_terms] + [(t, "data") for t in data_terms]
        keep.sort(key=lambda x: -len(x[0]))
        self._keep = [(_bounded(t), source) for t, source in keep]
        words = sorted(persona.words, key=lambda w: -len(w.original))
        self._words = [(_bounded(w.original, re.IGNORECASE), w) for w in words]

    def rewrite(self, text: str) -> Rewritten:
        spans: list[tuple[int, int, str, Hit]] = []

        def free(start: int, end: int) -> bool:
            return all(end <= s or start >= e for s, e, _, _ in spans)

        for m in EMAIL.finditer(text):
            spans.append((m.start(), m.end(), m.group(), Hit(m.group(), m.group(), KNOW, "data")))
        for pattern, source in self._keep:
            for m in pattern.finditer(text):
                if free(m.start(), m.end()):
                    spans.append((m.start(), m.end(), m.group(), Hit(m.group(), m.group(), KNOW, source)))
        for pattern, w in self._words:
            for m in pattern.finditer(text):
                if free(m.start(), m.end()):
                    shown = _match_case(w.shown, m.group())
                    spans.append((m.start(), m.end(), shown, Hit(m.group(), shown, w.level, "item", w.id, w.gloss)))
        for m in TOKEN.finditer(text):
            if free(m.start(), m.end()):
                hit = self._offlist(m.group())
                spans.append((m.start(), m.end(), hit.shown, hit))

        spans.sort(key=lambda s: s[0])
        out, pos = [], 0
        for start, end, replacement, _ in spans:
            out.append(text[pos:start])
            out.append(replacement)
            pos = end
        out.append(text[pos:])
        return Rewritten("".join(out), [s[3] for s in spans])

    def _offlist(self, token: str) -> Hit:
        """An off-list word has no special meaning here (words that do are items), so
        knowing its everyday meaning is knowing it (2026-10-04). Interface words such as
        Deselect are known to anyone who uses a computer, however rare in ordinary text."""
        card = self.persona.card_type
        rank = self.common.rank(token)
        if card == "full":
            return Hit(token, token, KNOW, "offlist", rank=rank)
        lower = token.lower()
        if card != "blank" and lower not in self.force_fake and (token in self.common or lower in self.ui_words):
            return Hit(token, token, KNOW, "offlist", rank=rank)
        return Hit(token, fake(token), NONE, "offlist", rank=rank)


def common_word_limit(persona: Persona, config: dict) -> int:
    """His own vocabulary size from the test, or the default for his English level
    when he did not take it (engine-design.md 4.1)."""
    if persona.vocab_size:
        return int(persona.vocab_size)
    top_n = config["words"]["top_n"]
    return top_n.get(persona.english, max(top_n.values()))


def build_vocabulary(persona: Persona, config: dict) -> Vocabulary:
    words = config["words"]
    top_n = common_word_limit(persona, config)
    return Vocabulary(
        persona,
        CommonWords.from_wordfreq(top_n),
        data_terms=words["data_terms"],
        harness_terms=[config["platform"]["harness_button_text"]],
        force_fake=words["force_fake"],
        ui_words=words.get("ui_words", []),
    )
