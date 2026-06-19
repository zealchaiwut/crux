"""Claim extractor: splits a source document into candidate factual claim strings."""
from __future__ import annotations

import re

from .types import SourceDocument

# Minimum characters for a sentence to be considered a candidate claim.
_MIN_CLAIM_LEN = 20


def _split_sentences(text: str) -> list[str]:
    """Split text into sentences on '. ', '! ', '? ' boundaries."""
    raw = re.split(r"(?<=[.!?])\s+", text.strip())
    return [s.strip() for s in raw if s.strip()]


def _is_factual_claim(sentence: str) -> bool:
    """Return True if the sentence looks like a discrete factual assertion."""
    if len(sentence) < _MIN_CLAIM_LEN:
        return False
    # Filter out questions
    if sentence.rstrip().endswith("?"):
        return False
    # Filter out imperatives / instructions (starts with a verb in command form)
    if re.match(r"^(Please|Note that|See |Click |Go to )", sentence, re.IGNORECASE):
        return False
    return True


class ClaimExtractor:
    """Splits a SourceDocument into a list of candidate factual claim strings.

    Purely rule-based — no network or API calls required.
    """

    def extract(self, doc: SourceDocument) -> list[str]:
        sentences = _split_sentences(doc.text)
        return [s for s in sentences if _is_factual_claim(s)]
