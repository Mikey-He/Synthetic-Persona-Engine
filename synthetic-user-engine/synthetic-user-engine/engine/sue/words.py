"""What this person sees in place of each word on screen (engine-design.md 4.1).

Order of precedence for any piece of text:
1. test harness words (I'm finished) and data (names, IDs, months) stay as they are;
2. word items from the persona card are shown the way the card says;
3. every other word follows the off-list rule: a common English word for his
   English level stays and counts as everyday meaning, anything else becomes a
   fake word. The blank card fakes every off-list word, the full card keeps them.

Chinese text follows the same rules. It has no spaces, so each run of Chinese
characters is cut into words first (wordfreq's Chinese tokenizer), and his Chinese
level decides which of them are common.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache

from .persona import KNOW, NONE, Persona

# ---- fake words ---------------------------------------------------------------

_CONSONANTS = "bdfgklmnprstvz"
_VOWELS = "aeiou"


def _imul(a: int, b: int) -> int:
    return ((a & 0xFFFFFFFF) * (b & 0xFFFFFFFF)) & 0xFFFFFFFF


# Chinese characters a reader of Chinese will not know: real ones that every Chinese
# font has (GB2312 level 2), none of them among wordfreq's 30,000 most common Chinese
# words. A faked Chinese word still looks like Chinese, but cannot be read.
_CJK_POOL = (
    "亍鬲爻亟嘏赝刈剜罔仞伉伲佻俚俳倥傥僦俎兖蠃诃诙诳谌谝谯阢陔隗邴邾郗鄣劢叟弁壅圯坼"
    "垲埚埝塄馨芄苈苁芤苴茆茈荏茺荪莪莸菥萜菸葜蒉葭蒿蓣蕖蕞蕹藜弈尥拗揶掮揎搠摺擢叱呋"
    "吲咝哕哝唢啉啶喹嗟嗔嗍嘣噍噻囡帏幄岐岵峄崦崴嵊巅徨犴狨猃猝獐夥饪馇庀庳忤怵怿悖惬"
    "愠慵隳阃阏戕沌泔泖洹洎浔涔淠涮湓滠滗潇漪潼濡瀵宸逅逵遨邃屙艴妗娈娑婵媲嫘尕驵骈骜"
    "绁绠绻缏缡缫缵玢珥珲琮瑾璩杞枧栉柚柁桄栾桫棰楂榇榧榕橥樽猷殍轲轼辎戟瓴旰昝晁暝贶"
    "赇觎牯挈毵氙牍肓肷胍脍脬腱媵臊歆彀旃炻焖煸燔熹祉祺恚慝沓砑砟硖碓碥礓盱眙睚瞑畋罟"
    "盍钌钣钶铄铒铟铩铼锍锘锩锼镌镙镥镯秕稞皎鸩鸷鹇鹗鹨疴痍痼瘘瘭癔窀窳裆裱褓襻耖耨聩"
    "颍颢虺蚧蛎蛩蛴蜊蜚螂蝮螓螗蟓蟮缶笄笙笞筮箸箫篦簟舂舯艄袅羲粽艮翮麸赭"
)

# Chinese characters: the main CJK block and extension A.
_CJK = "\u3400-\u4dbf\u4e00-\u9fff"
CJK_CHAR = re.compile(f"[{_CJK}]")
CJK_RUN = re.compile(f"[{_CJK}]+")


def _is_cjk(ch: str) -> bool:
    return "\u4e00" <= ch <= "\u9fff" or "\u3400" <= ch <= "\u4dbf"


def fake(word: str) -> str:
    """Same algorithm as fake() in tools/knowledge-workbench.html, so a fake word
    matches the card's "shown". Same length, same capitals, and the same word always
    turns into the same fake word. A Chinese character becomes another, rarer one
    (never itself); text without Chinese comes out exactly as it always has."""
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
        elif _is_cjk(ch):
            h = _imul(h ^ (i + 7), 2654435761)
            c = _CJK_POOL[h % len(_CJK_POOL)]
            if c == ch:
                c = _CJK_POOL[(h + 1) % len(_CJK_POOL)]
            out.append(c)
        else:
            out.append(ch)
            if ch in " /":
                pos = 0
    return "".join(out)


# ---- common English words -----------------------------------------------------

def _simplified(text: str) -> str:
    """Traditional characters looked up as Simplified ones, since the Chinese frequency
    list is Simplified. The text as it is when wordfreq's Chinese support is missing."""
    try:
        from wordfreq.chinese import simplify_chinese
    except ImportError:
        return text
    return simplify_chinese(text)


def _variants(token: str) -> list[str]:
    """The token and the simple base forms it may come from, so Budgets, pricing and
    labels count when budget, price and label are common. A Chinese word has no such
    forms; it may only be written in Traditional characters."""
    if CJK_CHAR.search(token):
        simple = _simplified(token)
        return [token] if simple == token else [token, simple]
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
    list too, so the log can show how close each off-list word was to the limit.
    One list per language: English and Chinese words are ranked apart."""

    def __init__(self, ranks: dict[str, int], limit: int):
        self.ranks = ranks
        self.limit = limit

    @classmethod
    def from_wordfreq(cls, limit: int, ranked: int = 100_000, lang: str = "en") -> "CommonWords":
        from wordfreq import top_n_list

        words = top_n_list(lang, max(limit, ranked))
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
LETTERS = re.compile(r"[A-Za-z]+")  # plain runs of letters: I'm is I and m


@lru_cache(maxsize=4096)
def segment(run: str) -> tuple[str, ...]:
    """Cuts a run of Chinese characters into words with wordfreq's Chinese tokenizer
    (it needs jieba). Without it, or if its words do not add up to the run, every two
    characters count as one word."""
    try:
        import jieba
        from wordfreq import tokenize

        jieba.setLogLevel(30)  # its "Building prefix dict" notes do not belong in the log
        words = tuple(tokenize(run, "zh"))
    except ImportError:
        words = ()
    if "".join(words) != run:
        words = tuple(run[i:i + 2] for i in range(0, len(run), 2))
    return words


def _cjk_spans(text: str, start: int = 0, end: int | None = None) -> list[tuple[int, int]]:
    """Where each Chinese word in text[start:end] begins and ends."""
    out = []
    for m in CJK_RUN.finditer(text, start, len(text) if end is None else end):
        pos = m.start()
        for w in segment(m.group()):
            out.append((pos, pos + len(w)))
            pos += len(w)
    return out


def tokens(text: str, english: re.Pattern[str] = TOKEN) -> list[str]:
    """The words in text, English and Chinese, in the order they appear. english is
    the pattern for English words (TOKEN, or LETTERS)."""
    found = [(m.start(), m.group()) for m in english.finditer(text)]
    found += [(s, text[s:e]) for s, e in _cjk_spans(text)]
    return [w for _, w in sorted(found)]


_READABLE = re.compile(f"[A-Za-z]+|[{_CJK}]+")


def unreadable_text(text: str) -> str:
    """Text too small for him to read: every word becomes a made-up word, digits blur to #."""
    return re.sub(r"\d", "#", _READABLE.sub(lambda m: fake(m.group(0)), text))


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
        common_zh: CommonWords | None = None,
    ):
        """common_zh: the Chinese words common enough for his Chinese level. Without it
        no Chinese word counts as common."""
        self.persona = persona
        self.common = common
        self.common_zh = common_zh or CommonWords({}, 0)
        self.force_fake = {w.lower() for w in force_fake}
        self.ui_words = {w.lower() for w in ui_words}
        # Chinese interface and jargon words may be cut in two by the tokenizer (下一步
        # becomes 下 + 一步), so they are found as whole phrases before the cutting.
        phrases = sorted({w for w in [*ui_words, *force_fake] if CJK_CHAR.search(w)}, key=lambda w: -len(w))
        self._phrases = [_bounded(w) for w in phrases]
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
        for pattern in self._phrases:
            for m in pattern.finditer(text):
                if free(m.start(), m.end()):
                    hit = self._offlist(m.group())
                    spans.append((m.start(), m.end(), hit.shown, hit))
        # Chinese words: only the stretches nothing above has taken are cut into words,
        # so no leftover character of a longer word stays readable.
        gaps, pos = [], 0
        for s, e in sorted((s, e) for s, e, _, _ in spans):
            if s > pos:
                gaps.append((pos, s))
            pos = max(pos, e)
        gaps.append((pos, len(text)))
        for gap_start, gap_end in gaps:
            for start, end in _cjk_spans(text, gap_start, gap_end):
                hit = self._offlist(text[start:end])
                spans.append((start, end, hit.shown, hit))

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
        common = self.common_zh if CJK_CHAR.search(token) else self.common
        rank = common.rank(token)
        if card == "full":
            return Hit(token, token, KNOW, "offlist", rank=rank)
        lower = token.lower()
        if card != "blank" and lower not in self.force_fake and (token in common or lower in self.ui_words):
            return Hit(token, token, KNOW, "offlist", rank=rank)
        return Hit(token, fake(token), NONE, "offlist", rank=rank)


def common_word_limit(persona: Persona, config: dict) -> int:
    """His own vocabulary size from the test, or the default for his English level
    when he did not take it (engine-design.md 4.1)."""
    if persona.vocab_size:
        return int(persona.vocab_size)
    top_n = config["words"]["top_n"]
    return top_n.get(persona.english, max(top_n.values()))


def chinese_word_limit(persona: Persona, config: dict) -> int:
    """How many of the most common Chinese words he knows, from his Chinese level on
    the card (native when the card does not say)."""
    top_n = config["words"].get("top_n_zh") or {"native": 50_000}
    return top_n.get(persona.chinese, max(top_n.values()))


def build_vocabulary(persona: Persona, config: dict) -> Vocabulary:
    words = config["words"]
    top_n = common_word_limit(persona, config)
    return Vocabulary(
        persona,
        CommonWords.from_wordfreq(top_n),
        data_terms=words["data_terms"],
        harness_terms=[config["platform"]["harness_button_text"]],
        force_fake=words["force_fake"],
        ui_words=[*words.get("ui_words", []), *words.get("ui_words_zh", [])],
        common_zh=CommonWords.from_wordfreq(chinese_word_limit(persona, config), lang="zh"),
    )
