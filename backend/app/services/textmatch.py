import re
import unicodedata
from html import unescape

_PUNCTUATION = str.maketrans(
    {"‘": "'", "’": "'", "“": '"', "”": '"', "–": "-", "—": "-", " ": " "}
)


def norm(text: str) -> str:
    """Make text comparable: decode entities, straighten quotes, drop accents, ignore case and whitespace.

    Dropping accents makes "Täht" and "Taht" the same name (sites and models spell people both ways).
    """
    decomposed = unicodedata.normalize("NFKD", unescape(text).translate(_PUNCTUATION))
    plain = "".join(c for c in decomposed if not unicodedata.combining(c))
    return " ".join(plain.casefold().split())


def has_word(text: str, word: str) -> bool:
    """Whole-word match, so 'sam' does not match inside 'samuel'. (?<!\\w) also copes with names like 'j.b.'."""
    return re.search(rf"(?<!\w){re.escape(word)}(?!\w)", text) is not None
