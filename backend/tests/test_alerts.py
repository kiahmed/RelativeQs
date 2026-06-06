"""Tests for breadth-shift alerts (offline — no Resend, no Supabase, no network)."""
import pytest

from app import alerts


def _breadth(state: str, status: str = "ok"):
    return {
        "status": status,
        "breadth_state": state,
        "equal_weight_pct": 0.55,
        "cap_weight_pct": 0.61,
        "advancers": 55,
        "measured": 100,
    }


@pytest.fixture(autouse=True)
def _reset_state():
    alerts._last_breadth_state = None
    yield
    alerts._last_breadth_state = None


@pytest.fixture
def captured(monkeypatch):
    calls = []

    async def fake_dispatch(previous, current, breadth):
        calls.append((previous, current))

    monkeypatch.setattr(alerts, "_dispatch", fake_dispatch)
    return calls


@pytest.mark.asyncio
async def test_first_observation_seeds_silently(captured):
    await alerts.check_breadth_and_alert(_breadth("broad"))
    assert captured == []
    assert alerts._last_breadth_state == "broad"


@pytest.mark.asyncio
async def test_no_alert_when_state_unchanged(captured):
    await alerts.check_breadth_and_alert(_breadth("broad"))
    await alerts.check_breadth_and_alert(_breadth("broad"))
    assert captured == []


@pytest.mark.asyncio
async def test_alert_fires_on_state_flip(captured):
    await alerts.check_breadth_and_alert(_breadth("broad"))
    await alerts.check_breadth_and_alert(_breadth("narrow"))
    assert captured == [("broad", "narrow")]
    assert alerts._last_breadth_state == "narrow"


@pytest.mark.asyncio
async def test_ignores_warming_up_and_unknown(captured):
    await alerts.check_breadth_and_alert(_breadth("broad", status="warming_up"))
    await alerts.check_breadth_and_alert(_breadth("unknown"))
    await alerts.check_breadth_and_alert({})
    assert captured == []
    assert alerts._last_breadth_state is None


def test_email_html_renders_states():
    html = alerts._email_html("broad", "narrow", _breadth("narrow"))
    assert "Narrow participation" in html
    assert "Broad participation" in html
    assert "equal-weight" in html
