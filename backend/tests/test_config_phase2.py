import app.config as config_module


def test_driver_symbols_default():
    """DRIVER_SYMBOLS defaults to the three engines under QQQ."""
    s = config_module.settings
    assert s.DRIVER_SYMBOLS == ["SMH", "IGV", "MAGS"]
    assert isinstance(s.DRIVER_SYMBOLS, list)
    assert all(t == t.strip().upper() for t in s.DRIVER_SYMBOLS)


def test_hitrate_horizons_parse_to_ints():
    """HITRATE_HORIZONS parses to a list of ints [5, 15, 30]."""
    s = config_module.settings
    assert s.HITRATE_HORIZONS == [5, 15, 30]
    assert all(isinstance(h, int) for h in s.HITRATE_HORIZONS)


def test_thresholds_are_floats():
    s = config_module.settings
    assert isinstance(s.CORR_COUPLED_THRESHOLD, float)
    assert isinstance(s.CORR_FRAGMENTED_THRESHOLD, float)
    assert isinstance(s.STABILITY_TRADEABLE_PERSISTENCE, float)
    assert s.CORR_COUPLED_THRESHOLD == 0.6
    assert s.CORR_FRAGMENTED_THRESHOLD == 0.3
    assert s.STABILITY_TRADEABLE_PERSISTENCE == 0.6


def test_backfill_defaults():
    s = config_module.settings
    assert s.HISTORY_BACKFILL_ENABLED is True
    assert s.HISTORY_BACKFILL_SOURCE in ("provider", "yahoo", "none")
    assert s.HISTORY_BACKFILL_SOURCE == "provider"
    assert isinstance(s.HISTORY_BACKFILL_DAYS, int) and s.HISTORY_BACKFILL_DAYS == 7
    assert isinstance(s.HISTORY_BACKFILL_MIN_SESSIONS, int)
    # retention should cover the backfill window so seeded days aren't expired early
    assert s.HISTORY_RETENTION_DAYS >= s.HISTORY_BACKFILL_DAYS


def test_int_window_and_sample_defaults():
    s = config_module.settings
    assert s.ATTRIBUTION_WINDOW == 30
    assert s.CORR_REGIME_WINDOW == 30
    assert s.STABILITY_LOOKBACK_DAYS == 5
    assert s.STABILITY_MIN_SESSIONS == 2
    assert s.STABILITY_LAG_TOLERANCE == 2
    assert s.HITRATE_MIN_SAMPLE == 30
    for v in (
        s.ATTRIBUTION_WINDOW,
        s.CORR_REGIME_WINDOW,
        s.STABILITY_LOOKBACK_DAYS,
        s.STABILITY_MIN_SESSIONS,
        s.STABILITY_LAG_TOLERANCE,
        s.HITRATE_MIN_SAMPLE,
    ):
        assert isinstance(v, int)
