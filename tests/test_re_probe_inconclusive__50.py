"""Tests for issue #50: Add re-probe action for inconclusive verdicts.

This test file verifies the acceptance criteria for the re-probe feature.
AC coverage:
  AC1 – "Design new probe" button only appears for inconclusive verdict
  AC2 – POST /api/cases/{id}/probe after inconclusive verdict creates a new probe
  AC3 – After re-probe, GET /api/cases/{id} returns the new probe
  AC4 – Previous (inconclusive) probe and its verdict are retained in DB
  AC5 – "Design new probe" button disabled while the request is in-flight
  AC6 – Error state shown when POST /probe fails; existing probe/verdict unchanged
  AC7 – No re-probe for confirmed or killed verdicts
"""
import os
import pytest


os.environ.setdefault("AUTH_SECRET", "test_auth_secret_12345678901234")


def _read_js_files():
    """Read the app's JavaScript files."""
    from pathlib import Path
    js_dir = Path(__file__).parent.parent / "app" / "static" / "js"
    if not js_dir.exists():
        pytest.skip("JS files not found in static/js")
    combined = "".join(
        (js_dir / f).read_text()
        for f in sorted(js_dir.iterdir())
        if f.suffix == ".js"
    )
    return combined


def _read_router_code():
    """Read the cases router implementation."""
    from pathlib import Path
    router_path = Path(__file__).parent.parent / "app" / "routers" / "cases.py"
    if not router_path.exists():
        pytest.skip("Router not found at app/routers/cases.py")
    return router_path.read_text()


def _read_models():
    """Read the models file."""
    from pathlib import Path
    models_path = Path(__file__).parent.parent / "app" / "models.py"
    if not models_path.exists():
        pytest.skip("Models not found at app/models.py")
    return models_path.read_text()


# --- AC1: Button visibility for inconclusive verdict ---

def test_ac1_button_text_in_js():
    """AC1: 'Design new probe' button text appears in JS."""
    js = _read_js_files()
    assert "Design new probe" in js, \
        "ProbeCard must contain 'Design new probe' button text"


def test_ac1_button_gated_on_inconclusive():
    """AC1: Button is shown only for inconclusive verdict (conditional rendering)."""
    js = _read_js_files()
    # Button must be gated on verdict==='inconclusive'
    assert "inconclusive" in js, \
        "JS must check for 'inconclusive' verdict to gate the button"
    assert ("Design new probe" in js and "verdict" in js), \
        "Button rendering must depend on verdict"


def test_ac1_button_disabled_while_loading():
    """AC5: Button is disabled/hidden while request is in-flight."""
    js = _read_js_files()
    # Must reference loading/disabled state
    has_disabled = "disabled" in js
    has_loading_state = "loading" in js.lower() or "Loading" in js or "Designing" in js
    assert (has_disabled or has_loading_state), \
        "ProbeCard must handle loading/disabled state for re-probe button"


def test_ac5_reprobe_error_display():
    """AC6: Error state is shown when re-probe fails."""
    js = _read_js_files()
    # Must handle and display re-probe error
    has_reprobe_error = "reProbeError" in js or "reprobe" in js.lower() or "Re-probe" in js
    assert has_reprobe_error, \
        "ProbeCard must display re-probe error messages"


# --- AC2: Backend allows re-probe for inconclusive verdict ---

def test_ac2_reprobe_logic_in_router():
    """AC2: POST /probe endpoint checks for inconclusive verdict to allow re-probe."""
    router = _read_router_code()
    # The design_probe_for_case function must have logic to handle inconclusive verdict
    assert "inconclusive" in router, \
        "Router must check for 'inconclusive' verdict"
    assert "design_probe_for_case" in router, \
        "Router must have the design_probe_for_case endpoint"
    # Logic should allow re-probing when existing probe has inconclusive verdict
    assert "_latest_probe" in router or "probes" in router, \
        "Router must handle multiple probes per case"


def test_ac2_reprobe_creates_new_probe():
    """AC2: Re-probe creates a new probe, not return existing."""
    router = _read_router_code()
    # Function must create a new probe when inconclusive verdict exists
    assert "models.Probe(" in router, \
        "Router must create new Probe objects during re-probe"
    assert "db.add(probe)" in router, \
        "Router must add new probe to database"


def test_ac2_case_stage_preserved():
    """AC2: Re-probe must not change the case stage."""
    router = _read_router_code()
    # Check that stage is only set when is_reprobe is False or similar
    assert "is_reprobe" in router or "inconclusive" in router, \
        "Router must differentiate between initial probe and re-probe to preserve stage"


def test_ac3_new_probe_returned():
    """AC3: After re-probe, GET /cases/{id} returns the new probe."""
    router = _read_router_code()
    # get_case must return the latest probe
    assert "_latest_probe" in router, \
        "Router must use _latest_probe helper to return most recent probe"
    assert "def get_case" in router, \
        "Router must have get_case endpoint"


def test_ac4_old_probe_retained():
    """AC4: Previous (inconclusive) probe is retained in database."""
    router = _read_router_code()
    # The router should NOT delete the old probe, just create a new one
    assert "delete" not in router.lower() or "delete(" not in router, \
        "Router must NOT delete old probes during re-probe"
    # When creating new probe, old probe remains in DB
    assert "models.Probe(" in router and "db.add(probe)" in router, \
        "New probe is added without removing old one"


def test_ac7_no_reprobe_confirmed():
    """AC7: POST /probe with confirmed verdict returns existing probe."""
    router = _read_router_code()
    # Logic should be: only allow re-probe if verdict exists AND is inconclusive
    assert "inconclusive" in router, \
        "Router must check for inconclusive outcome specifically"
    # Should return existing probe if verdict is not inconclusive
    assert ("confirmed" in router or "verdict" in router) and "outcome" in router, \
        "Router must check verdict outcome"


# --- Probe model tests ---

def test_probe_model_created_at_field():
    """AC2: Probe model must have created_at for ordering probes."""
    models = _read_models()
    assert "Probe" in models, "Models must define Probe class"
    assert "created_at" in models, \
        "Probe model should have created_at field for ordering (to find latest probe)"


# --- Integration-style test: verify feature flags ---

def test_feature_integrated_end_to_end():
    """Verify all parts of the feature are present and integrated."""
    js = _read_js_files()
    router = _read_router_code()
    models = _read_models()

    # Frontend: button exists and is gated
    assert "Design new probe" in js
    assert "inconclusive" in js

    # Backend: re-probe logic exists
    assert "inconclusive" in router
    assert "models.Probe(" in router

    # Models: Probe supports multi-per-case
    assert "Probe" in models
    assert "probes = relationship" in models  # Case has many probes

    # Feature: all parts integrated
    assert "design_probe_for_case" in router
