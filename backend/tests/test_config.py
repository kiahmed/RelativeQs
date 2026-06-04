import importlib
import os

import app.config as config_module


def reload_config():
    """Reload the config module so class attributes re-read os.environ."""
    return importlib.reload(config_module)


def test_defaults_include_core_etfs():
    """With no override, the universe defaults must include QQQ/MAGS/IGV."""
    s = config_module.settings
    for ticker in ("QQQ", "MAGS", "IGV"):
        assert ticker in s.ETF_UNIVERSE


def test_target_defaults_to_qqq():
    assert config_module.settings.PREDICTION_TARGET == "QQQ"


def test_universe_is_list_of_upper_stripped_strings():
    s = config_module.settings
    assert isinstance(s.ETF_UNIVERSE, list)
    assert all(isinstance(t, str) for t in s.ETF_UNIVERSE)
    assert all(t == t.strip().upper() for t in s.ETF_UNIVERSE)


def test_universe_parses_from_env(monkeypatch):
    """ETF_UNIVERSE parses comma-separated env, upper-casing and stripping."""
    monkeypatch.setenv("ETF_UNIVERSE", " qqq, smh ,spy,, igv ")
    monkeypatch.setenv("PREDICTION_TARGET", "spy")
    try:
        reloaded = reload_config()
        assert reloaded.settings.ETF_UNIVERSE == ["QQQ", "SMH", "SPY", "IGV"]
        # empty segments dropped
        assert "" not in reloaded.settings.ETF_UNIVERSE
        # target upper-cased
        assert reloaded.settings.PREDICTION_TARGET == "SPY"
    finally:
        monkeypatch.delenv("ETF_UNIVERSE", raising=False)
        monkeypatch.delenv("PREDICTION_TARGET", raising=False)
        reload_config()


def test_numeric_defaults():
    s = config_module.settings
    assert s.LEAD_LAG_MAX_LAG == 15
    assert s.LEAD_LAG_MIN_BARS == 45
    assert s.LEAD_LAG_CORR_THRESHOLD == 0.25
    assert s.PROJECTION_HORIZON_MINUTES == 15
    assert s.YAHOO_MIN_FETCH_INTERVAL_SECONDS == 60.0
    assert s.HISTORY_RETENTION_DAYS == 7


def test_parsing_expression_directly():
    """The parsing expression itself, exercised independently of the module."""
    raw = "QQQ, mags ,igv,,"
    parsed = [t.strip().upper() for t in raw.split(",") if t.strip()]
    assert parsed == ["QQQ", "MAGS", "IGV"]
