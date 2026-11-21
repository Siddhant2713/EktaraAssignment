import re
from html import unescape

_PUNCTUATION = str.maketrans(
    {"‘": "'", "’": "'", "“": '"', "”": '"', "–": "-", "—": "-", " ": " "}
)


def norm(text: str) -> str:
    """Make text comparable: decode entities, straighten quotes, ignore case and whitespace."""
    return " ".join(unescape(text).translate(_PUNCTUATION).casefold().split())


def has_word(text: str, word: str) -> bool:
    """Whole-word match, so 'sam' does not match inside 'samuel'. (?<!\\w) also copes with names like 'j.b.'."""
    return re.search(rf"(?<!\w){re.escape(word)}(?!\w)", text) is not None
