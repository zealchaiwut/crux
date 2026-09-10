"""Tests for issue #196: Promote hardcoded 4000-char truncation to a named constant.

AC coverage:
  AC1 – CRUX_BULK_SOURCE_CHARS is a module-level constant in app.bulk_stages
  AC2 – content_summary truncates source_text to CRUX_BULK_SOURCE_CHARS characters
  AC3 – content_summary_sync truncates source_text to CRUX_BULK_SOURCE_CHARS characters
  AC4 – The constant default value is 4000 (preserving existing behaviour)
"""
from unittest.mock import patch


# ============================================================================
# AC1: CRUX_BULK_SOURCE_CHARS exists as a module-level constant
# ============================================================================


def test_crux_bulk_source_chars_exists():
    """AC1: app.bulk_stages exposes a module-level CRUX_BULK_SOURCE_CHARS constant."""
    import app.bulk_stages as bulk_stages

    assert hasattr(bulk_stages, "CRUX_BULK_SOURCE_CHARS"), (
        "CRUX_BULK_SOURCE_CHARS must be defined at module level in app.bulk_stages"
    )


def test_crux_bulk_source_chars_is_int():
    """AC1: CRUX_BULK_SOURCE_CHARS is an integer."""
    import app.bulk_stages as bulk_stages

    assert isinstance(bulk_stages.CRUX_BULK_SOURCE_CHARS, int)


# ============================================================================
# AC4: Default value preserves existing behaviour (4000)
# ============================================================================


def test_crux_bulk_source_chars_default_is_4000():
    """AC4: Default value of CRUX_BULK_SOURCE_CHARS is 4000, matching old hardcoded limit."""
    import app.bulk_stages as bulk_stages

    assert bulk_stages.CRUX_BULK_SOURCE_CHARS == 4000


# ============================================================================
# AC2: content_summary_sync uses the constant for truncation
# ============================================================================


def test_content_summary_sync_truncates_to_constant():
    """AC2: content_summary_sync truncates source_text to CRUX_BULK_SOURCE_CHARS chars."""
    import app.bulk_stages as bulk_stages

    long_text = "x" * 10_000

    with patch("app.bulk_stages.call_bulk_stage_sync") as mock_call:
        mock_call.return_value = {"summary": "ok"}
        bulk_stages.content_summary_sync(long_text, "Title")

        user_arg = mock_call.call_args[0][1]
        # The source text portion must not exceed CRUX_BULK_SOURCE_CHARS characters
        source_portion = user_arg.split("Source text:\n", 1)[1]
        assert len(source_portion) <= bulk_stages.CRUX_BULK_SOURCE_CHARS


def test_content_summary_sync_respects_modified_constant():
    """AC2: content_summary_sync uses the constant dynamically — a smaller limit is honoured."""
    import app.bulk_stages as bulk_stages

    long_text = "a" * 500
    original = bulk_stages.CRUX_BULK_SOURCE_CHARS

    try:
        bulk_stages.CRUX_BULK_SOURCE_CHARS = 100
        with patch("app.bulk_stages.call_bulk_stage_sync") as mock_call:
            mock_call.return_value = {"summary": "ok"}
            bulk_stages.content_summary_sync(long_text, "Title")

            user_arg = mock_call.call_args[0][1]
            source_portion = user_arg.split("Source text:\n", 1)[1]
            assert len(source_portion) <= 100
    finally:
        bulk_stages.CRUX_BULK_SOURCE_CHARS = original


# ============================================================================
# AC3: content_summary (async) uses the constant for truncation
# ============================================================================


def test_content_summary_async_truncates_to_constant():
    """AC3: content_summary (async) truncates source_text to CRUX_BULK_SOURCE_CHARS chars."""
    import asyncio

    import app.bulk_stages as bulk_stages

    long_text = "y" * 10_000

    async def run():
        with patch("app.bulk_stages.call_bulk_stage") as mock_call:
            import asyncio as _asyncio

            async def _fake(*a, **kw):
                return {"summary": "ok"}

            mock_call.side_effect = _fake
            await bulk_stages.content_summary(long_text, "Title")
            return mock_call.call_args[0][1]

    user_arg = asyncio.run(run())
    source_portion = user_arg.split("Source text:\n", 1)[1]
    assert len(source_portion) <= bulk_stages.CRUX_BULK_SOURCE_CHARS


def test_content_summary_async_respects_modified_constant():
    """AC3: content_summary (async) uses the constant dynamically — a smaller limit is honoured."""
    import asyncio

    import app.bulk_stages as bulk_stages

    long_text = "b" * 500
    original = bulk_stages.CRUX_BULK_SOURCE_CHARS

    async def run():
        with patch("app.bulk_stages.call_bulk_stage") as mock_call:
            import asyncio as _asyncio

            async def _fake(*a, **kw):
                return {"summary": "ok"}

            mock_call.side_effect = _fake
            await bulk_stages.content_summary(long_text, "Title")
            return mock_call.call_args[0][1]

    try:
        bulk_stages.CRUX_BULK_SOURCE_CHARS = 100
        user_arg = asyncio.run(run())
        source_portion = user_arg.split("Source text:\n", 1)[1]
        assert len(source_portion) <= 100
    finally:
        bulk_stages.CRUX_BULK_SOURCE_CHARS = original
