import os
import sys

PORT: int = int(os.environ.get("PORT", "7001"))
ENV: str = os.environ.get("ENV", "development")

_raw_secret = os.environ.get("AUTH_SECRET", "")
if not _raw_secret:
    print(
        "FATAL: AUTH_SECRET environment variable is required and must be at least 16 characters long.",
        file=sys.stderr,
    )
    sys.exit(1)
if len(_raw_secret) < 16:
    print(
        f"FATAL: AUTH_SECRET must be at least 16 characters long (got {len(_raw_secret)}).",
        file=sys.stderr,
    )
    sys.exit(1)

AUTH_SECRET: str = _raw_secret

# §11: research engine selection — "custom" (default) or "fallback".
# Switch without any code change: set RESEARCH_ENGINE=fallback in the environment.
RESEARCH_ENGINE: str = os.environ.get("RESEARCH_ENGINE", "custom")

# LLM provider selection (issue #189).
# CRUX_LLM_PROVIDER: "groq" | "anthropic_api" | "claude_cli" | "" (default, uses settings_store)
CRUX_LLM_PROVIDER: str = os.environ.get("CRUX_LLM_PROVIDER", "")
CRUX_JUDGMENT_MODEL: str = os.environ.get("CRUX_JUDGMENT_MODEL", "openai/gpt-oss-120b")
CRUX_BULK_MODEL: str = os.environ.get("CRUX_BULK_MODEL", "llama-3.1-8b-instant")

_VALID_LLM_PROVIDERS = {"", "groq", "anthropic_api", "claude_cli"}


def _validate_llm_provider_config(provider: str, groq_key: str) -> None:
    """Validate LLM provider env vars; call sys.exit(1) with a readable message on failure."""
    if provider not in _VALID_LLM_PROVIDERS:
        print(
            f"FATAL: Unknown CRUX_LLM_PROVIDER '{provider}'. "
            "Accepted values: groq, anthropic_api, claude_cli",
            file=sys.stderr,
        )
        sys.exit(1)
    if provider == "groq" and not groq_key:
        print(
            "FATAL: GROQ_API_KEY is required when CRUX_LLM_PROVIDER=groq",
            file=sys.stderr,
        )
        sys.exit(1)


_validate_llm_provider_config(CRUX_LLM_PROVIDER, os.environ.get("GROQ_API_KEY", ""))
