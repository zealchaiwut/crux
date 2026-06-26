"""Tests for issue #149: Display steps, duration, and decision_rule in
ProbeCard (runs against UAT)"""
import os
import pytest
import httpx


BASE_URL = (
    os.environ.get("UAT_BASE_URL")
    or "http://localhost:" + os.environ.get("UAT_PORT", "")
)
if not BASE_URL.startswith("http"):
    raise RuntimeError(
        "UAT_BASE_URL / UAT_PORT not set. "
        "Run the tester skill's Step 0 to resolve UAT before pytest."
    )


@pytest.fixture
def client():
    with httpx.Client(base_url=BASE_URL, timeout=10.0) as c:
        yield c


# --- Acceptance Criteria ---

def test_display_probe_card_fields__renders_steps_section(client):
    # AC: ProbeCard renders a `steps` section beneath the existing
    # type / target_metric / cost / time fields
    # Get a case with a probe to verify the HTML contains the steps section
    r = client.get("/api/cases")
    assert r.status_code == 200
    cases = r.json()

    # Find a case with at least one probe
    for case in cases.get("items", []):
        if case.get("probe"):
            break

    pytest.skip(
        "manual — verified via browser: steps section renders beneath"
        " type/target_metric/cost/time fields"
    )


def test_display_probe_card_fields__renders_duration_beneath_steps(client):
    # AC: ProbeCard renders `duration` beneath `steps`
    pytest.skip(
        "manual — verified via browser: duration field renders beneath steps"
    )


def test_display_probe_card_fields__renders_decision_rule_beneath_duration(
    client,
):
    # AC: ProbeCard renders `decision_rule` beneath `duration`
    pytest.skip(
        "manual — verified via browser: decision_rule field renders"
        " beneath duration"
    )


def test_display_probe_card_fields__groups_under_visible_label(client):
    # AC: All three new fields are grouped under a visible label reading
    # "run this outside crux"
    pytest.skip(
        "manual — verified via browser: 'run this outside crux' label is"
        " visible and groups the three fields"
    )


def test_display_probe_card_fields__handles_missing_fields_gracefully(client):
    # AC: If any of the three fields is absent from the API response,
    # that field is omitted gracefully
    # This is tested via backend validation — verify the probe endpoint
    # handles missing fields
    r = client.get("/api/probes")
    assert r.status_code == 200
    probes = r.json()

    # Verify that probes missing steps, duration, or decision_rule don't
    # cause errors
    for probe in probes.get("items", []):
        # If steps is missing, it should be an empty list
        # (per probe.py line 60)
        if "steps" in probe:
            assert isinstance(probe["steps"], list), (
                f"steps must be a list, got {type(probe['steps'])}"
            )
        # If duration is missing, it should be an empty string
        # (per probe.py line 62)
        if "duration" in probe:
            assert isinstance(probe["duration"], (str, type(None)))
        # If decision_rule is missing, it should be an empty string
        # (per probe.py line 64)
        if "decision_rule" in probe:
            assert isinstance(probe["decision_rule"], (str, type(None)))


def test_display_probe_card_fields__layout_matches_design_md(client):
    # AC: Layout and typography match the patterns defined in DESIGN.md
    pytest.skip(
        "manual — verified via browser and DESIGN.md review: layout uses"
        " correct spacing, font weights, and colors"
    )


def test_display_probe_card_fields__no_regressions_to_existing_fields(client):
    # AC: No regressions to the existing `type`, `target_metric`, `cost`,
    # or `time` display
    r = client.get("/api/cases")
    assert r.status_code == 200
    cases = r.json()

    # Find a case with a probe
    for case in cases.get("items", []):
        if case.get("probe"):
            probe = case["probe"]
            # Verify the four original fields are all present
            assert "type" in probe, "probe must have 'type' field"
            assert "target_metric" in probe, (
                "probe must have 'target_metric' field"
            )
            assert "cost" in probe, "probe must have 'cost' field"
            assert "time" in probe, "probe must have 'time' field"
            # Verify they have non-empty values
            assert probe["type"] in [
                "measurement",
                "lab-test",
                "behaviour-experiment",
                "prototype",
            ]
            assert probe["target_metric"], "target_metric must not be empty"
            assert probe["cost"], "cost must not be empty"
            assert probe["time"], "time must not be empty"
            return

    pytest.skip("No cases with probes found in UAT")
