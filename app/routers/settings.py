"""Settings API router.

GET  /api/settings               — current provider, budget, and spend.
PUT  /api/settings               — update provider and/or API USD budget.
POST /api/settings/reset-spend   — zero the accumulated API spend.

Persisted to a gitignored local file (app.settings_store). Secrets stay in .env;
this endpoint never reads or writes the API key — only reports whether it is set.
"""
from fastapi import APIRouter
from pydantic import BaseModel, field_validator

from app import settings_store
from app.claude_cli import api_key_present

router = APIRouter(prefix="/api")


class SettingsResponse(BaseModel):
    provider: str
    api_usd_budget: float
    api_usd_spent: float
    api_usd_remaining: float
    api_key_present: bool


class UpdateSettingsRequest(BaseModel):
    provider: str | None = None
    api_usd_budget: float | None = None

    @field_validator("provider")
    @classmethod
    def valid_provider(cls, v: str | None) -> str | None:
        if v is not None and v not in ("cli", "api"):
            raise ValueError("provider must be 'cli' or 'api'")
        return v

    @field_validator("api_usd_budget")
    @classmethod
    def non_negative_budget(cls, v: float | None) -> float | None:
        if v is not None and v < 0:
            raise ValueError("api_usd_budget must be >= 0")
        return v


def _view(s: dict) -> SettingsResponse:
    return SettingsResponse(
        provider=s["provider"],
        api_usd_budget=s["api_usd_budget"],
        api_usd_spent=s["api_usd_spent"],
        api_usd_remaining=settings_store.budget_remaining(s),
        api_key_present=api_key_present(),
    )


@router.get("/settings", response_model=SettingsResponse)
def get_settings():
    return _view(settings_store.get_settings())


@router.put("/settings", response_model=SettingsResponse)
def update_settings(req: UpdateSettingsRequest):
    s = settings_store.update_settings(
        provider=req.provider, api_usd_budget=req.api_usd_budget
    )
    return _view(s)


@router.post("/settings/reset-spend", response_model=SettingsResponse)
def reset_spend():
    return _view(settings_store.reset_spend())
