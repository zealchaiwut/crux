"""Citation-aware synthesiser: calls the Claude API to produce Source rows with citations."""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from .types import Plan, Source

logger = logging.getLogger(__name__)

_VALID_KINDS = frozenset({"book", "article", "youtube"})

# ---------------------------------------------------------------------------
# Claude API prompt (committed alongside the implementation per AC8)
# ---------------------------------------------------------------------------

SYNTHESISER_PROMPT = """\
You are a research assistant that produces structured, citation-grounded evidence rows.

You will receive:
1. A research plan with a mechanism and prior knowledge.
2. A list of source excerpts, each with: kind (book/article/youtube), title, url, and claim \
(a sentence taken verbatim from the source document).

Your task:
- For each excerpt, produce a concise factual claim statement and a verbatim or \
minimally-paraphrased citation drawn directly from the provided claim text.
- Cite ONLY from the supplied source text. Do NOT invent, extrapolate, or paraphrase beyond \
what is present in the provided claim.
- OMIT any item for which you cannot provide a citation that is directly grounded in the \
provided source text.
- If no item can be verified, return an empty JSON array.

Return a JSON array (no markdown fences, raw JSON only) where every element has exactly \
these fields:
  kind    — one of: book | article | youtube
  title   — the source title (non-empty)
  url     — the source URL (non-empty, valid URL)
  claim   — a concise factual claim statement (non-empty)
  citation — a verbatim or minimally-paraphrased quote from the source text that supports \
the claim (non-empty)
"""

# ---------------------------------------------------------------------------
# CitationSynthesiser
# ---------------------------------------------------------------------------


class CitationSynthesiser:
    """Calls the Claude API to produce citation-grounded Source rows.

    Parameters
    ----------
    client:
        An ``anthropic.Anthropic`` client instance.  If omitted, a default
        client is created (requires ``ANTHROPIC_API_KEY`` in the environment).
    model:
        Claude model ID to use.
    max_tokens:
        Maximum tokens for the API response.
    """

    def __init__(
        self,
        client: Any = None,
        model: str = "claude-sonnet-4-6",
        max_tokens: int = 4096,
    ) -> None:
        if client is None:
            import anthropic
            client = anthropic.Anthropic()
        self._client = client
        self._model = model
        self._max_tokens = max_tokens

    def synthesise(self, plan: Plan, candidates: list[dict]) -> list[Source]:
        """Return validated Source rows for the given candidates.

        Parameters
        ----------
        plan:
            The research Plan (mechanism + prior) that governs the research loop.
        candidates:
            List of dicts with keys ``kind``, ``title``, ``url``, ``claim``.

        Returns
        -------
        list[Source]
            Only rows that pass all schema validations are returned; rows with
            missing, empty, or invalid fields are dropped with a WARNING log.
        """
        prompt = self._build_prompt(plan, candidates)
        message = self._client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        raw_text = message.content[0].text
        rows = self._parse_response(raw_text)
        return self._validate_rows(rows)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_prompt(self, plan: Plan, candidates: list[dict]) -> str:
        excerpts_json = json.dumps(candidates, indent=2, ensure_ascii=False)
        return (
            f"{SYNTHESISER_PROMPT}\n\n"
            f"Research Plan:\n"
            f"  Mechanism: {plan.mechanism}\n"
            f"  Prior: {plan.prior}\n\n"
            f"Source excerpts:\n{excerpts_json}"
        )

    def _parse_response(self, text: str) -> list[dict]:
        text = text.strip()
        # Strip accidental markdown fences
        if text.startswith("```"):
            text = re.sub(r"^```[^\n]*\n?", "", text)
            text = re.sub(r"\n?```$", "", text.rstrip())
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            logger.warning("CitationSynthesiser: failed to parse Claude response as JSON: %s", exc)
            return []
        if not isinstance(data, list):
            logger.warning("CitationSynthesiser: Claude response is not a JSON array")
            return []
        return data

    def _validate_rows(self, rows: list[dict]) -> list[Source]:
        valid: list[Source] = []
        for row in rows:
            if not isinstance(row, dict):
                logger.warning("CitationSynthesiser: dropping non-dict row: %r", row)
                continue

            kind = row.get("kind", "")
            title = row.get("title", "")
            url = row.get("url", "")
            claim = row.get("claim", "")
            citation = row.get("citation", "")

            if kind not in _VALID_KINDS:
                logger.warning(
                    "CitationSynthesiser: dropping row with invalid kind=%r (url=%r)", kind, url
                )
                continue
            if not title or not title.strip():
                logger.warning(
                    "CitationSynthesiser: dropping row with empty title (kind=%r, url=%r)", kind, url
                )
                continue
            if not _is_valid_url(url):
                logger.warning(
                    "CitationSynthesiser: dropping row with invalid url=%r (kind=%r)", url, kind
                )
                continue
            if not claim or not claim.strip():
                logger.warning(
                    "CitationSynthesiser: dropping row with empty claim (kind=%r, url=%r)", kind, url
                )
                continue
            if not citation or not citation.strip():
                logger.warning(
                    "CitationSynthesiser: dropping row — citation is missing or empty "
                    "(kind=%r, url=%r, claim=%r)", kind, url, claim
                )
                continue

            valid.append(
                Source(kind=kind, title=title, url=url, claim=claim, citation=citation)
            )
        return valid


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _is_valid_url(url: str) -> bool:
    return bool(re.match(r"^https?://\S+", url or ""))
