import re
from typing import Any

_SEPARATORS = re.compile(r"[\s_-]+")


def term_alternatives(term: Any) -> list[str]:
    """A required output term is a phrase or a list of equivalent phrases."""
    values = term if isinstance(term, list) else [term]
    if any(
        not isinstance(item, (str, int, float)) or isinstance(item, bool)
        for item in values
    ):
        raise ValueError("Required output terms must be text or numbers")
    alternatives = [str(item).strip() for item in values if str(item).strip()]
    if not alternatives:
        raise ValueError("Required output terms must be non-empty text")
    return alternatives


def term_label(term: Any) -> str:
    return " | ".join(term_alternatives(term))


def _normalize(text: str) -> str:
    return _SEPARATORS.sub(" ", text.casefold()).strip()


def missing_output_terms(terms: list[Any], output: str) -> list[str]:
    """Case-insensitive match that treats spaces, hyphens, and underscores alike."""
    normalized = _normalize(output)
    return [
        term_label(term) for term in terms
        if not any(_normalize(item) in normalized for item in term_alternatives(term))
    ]


def output_term_pattern(term: Any) -> str:
    """JavaScript-compatible regex equivalent to missing_output_terms matching."""
    alternatives = (
        r"[\s_-]+".join(re.escape(word)
                        for word in _SEPARATORS.split(item) if word)
        for item in term_alternatives(term)
    )
    return "(?i)(?:" + "|".join(alternatives) + ")"
