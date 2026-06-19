from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class ResearchConfig:
    max_fetches: int

    @classmethod
    def from_env(cls) -> ResearchConfig:
        return cls(max_fetches=int(os.environ.get("RESEARCH_MAX_FETCHES", "10")))
