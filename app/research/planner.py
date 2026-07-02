from __future__ import annotations

import re
from typing import Callable

from .types import Plan, SearchQuery

LLMCallable = Callable[[str], str]


class LLMQueryPlanner:
    """Query planner that uses an injected LLM callable to generate search queries."""

    def __init__(self, llm: LLMCallable) -> None:
        self._llm = llm

    def plan(self, plan: Plan) -> list[SearchQuery]:
        if not plan.mechanism and not plan.prior:
            return []
        prompt = (
            f"Generate search queries to research the following:\n"
            f"Mechanism: {plan.mechanism}\n"
            f"Prior knowledge: {plan.prior}\n"
            f"Return one search query per line."
        )
        response = self._llm(prompt)
        # Strip common list markers ("- ", "* ", "1. ") the model prepends so
        # they don't pollute the search query text.
        lines = []
        for line in response.splitlines():
            cleaned = re.sub(r"^\s*(?:[-*•]|\d+[.)])\s+", "", line).strip()
            if cleaned:
                lines.append(cleaned)
        if not lines:
            return []
        return [SearchQuery(query=line) for line in lines]
