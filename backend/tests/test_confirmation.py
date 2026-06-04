import pandas as pd

from app.core.confirmation import ConfirmationGate


def _lead_lag_ok(leader_symbol=None, lag=3, corr=0.6, beta=1.0,
                 confirmers=None, diverging=None, target="QQQ"):
    leader = None
    if leader_symbol is not None:
        leader = {
            "symbol": leader_symbol,
            "lag_minutes": lag,
            "corr": corr,
            "beta": beta,
        }
    return {
        "status": "ok",
        "bars_used": 240,
        "window_start": "2026-06-02T09:30:00",
        "window_end": "2026-06-02T13:30:00",
        "target": target,
        "entries": [],
        "leader": leader,
        "confirmers": list(confirmers or []),
        "diverging": list(diverging or []),
    }


def _score_ok(momentum, fragility=0.0, target="QQQ"):
    return {
        "status": "ok",
        "verdict": "continue",
        "score": 0.3,
        "probability_up": 0.6,
        "components": {
            "leadership": 0.4,
            "broadening": 0.3,
            "fragility": fragility,
        },
        "momentum_30m": dict(momentum),
    }


CONTRACT_KEYS = {
    "status", "state", "target_direction", "participation",
    "participating_count", "universe_count", "leaders_agree",
    "fragility", "message",
}


def test_confirmed_broad_aligned_rally():
    # QQQ up, the leader + confirmers + most peers up too.
    mom = {
        "QQQ": 0.004,
        "SMH": 0.005, "XLK": 0.004, "IGV": 0.003, "MAGS": 0.0035,
        "XLY": 0.002, "XLF": 0.0015, "XLI": 0.001, "IWM": 0.0008,
        "XLE": -0.0001, "XLP": -0.00005,  # one slightly negative, one flat
    }
    lead_lag = _lead_lag_ok(leader_symbol="SMH", confirmers=["XLY", "XLF"])
    score = _score_ok(mom, fragility=0.1)

    res = ConfirmationGate().compute(pd.DataFrame(), lead_lag, score)

    assert set(res) == CONTRACT_KEYS
    assert res["status"] == "ok"
    assert res["state"] == "confirmed"
    assert res["target_direction"] == "up"
    assert res["participation"] >= 0.55
    assert res["leaders_agree"] is True
    assert "confirmed" in res["message"]


def test_unconfirmed_narrow_move():
    # QQQ up, but the leader/confirmers and most peers are DOWN -> fade risk.
    mom = {
        "QQQ": 0.004,
        "SMH": -0.003, "XLK": -0.002, "IGV": -0.0025, "MAGS": -0.001,
        "XLY": -0.002, "XLF": -0.0015, "XLI": -0.001, "IWM": -0.0008,
        "XLE": -0.0009, "XLP": 0.0005,
    }
    lead_lag = _lead_lag_ok(leader_symbol="SMH", confirmers=["XLY", "XLF"])
    score = _score_ok(mom, fragility=0.1)

    res = ConfirmationGate().compute(pd.DataFrame(), lead_lag, score)

    assert res["status"] == "ok"
    assert res["state"] == "unconfirmed"
    assert res["target_direction"] == "up"
    assert res["participation"] < 0.55
    assert res["leaders_agree"] is False
    assert "fade risk" in res["message"]


def test_fragile_overrides():
    # Even with a broad aligned rally, high fragility flags fragile.
    mom = {
        "QQQ": 0.004,
        "SMH": 0.005, "XLK": 0.004, "IGV": 0.003, "MAGS": 0.0035,
        "XLY": 0.002, "XLF": 0.0015,
    }
    lead_lag = _lead_lag_ok(leader_symbol="SMH", confirmers=["XLY", "XLF"])
    score = _score_ok(mom, fragility=0.7)

    res = ConfirmationGate().compute(pd.DataFrame(), lead_lag, score)

    assert res["status"] == "ok"
    assert res["state"] == "fragile"
    assert res["fragility"] == 0.7
    assert "fragile" in res["message"]


def test_warming_up_when_score_not_ok():
    score = {
        "status": "warming_up",
        "verdict": "warming_up",
        "score": 0.0,
        "probability_up": 0.5,
        "components": {"leadership": 0.0, "broadening": 0.0, "fragility": 0.0},
        "momentum_30m": {},
    }
    lead_lag = _lead_lag_ok(leader_symbol=None)

    res = ConfirmationGate().compute(pd.DataFrame(), lead_lag, score)

    assert set(res) == CONTRACT_KEYS
    assert res["status"] == "warming_up"
    assert res["state"] == "unconfirmed"
    assert res["target_direction"] == "flat"


def test_no_leader_unconfirmed():
    # Direction up and broad participation, but no leader/confirmers -> not confirmed.
    mom = {
        "QQQ": 0.004,
        "SMH": 0.005, "XLK": 0.004, "IGV": 0.003,
    }
    lead_lag = _lead_lag_ok(leader_symbol=None, confirmers=[])
    score = _score_ok(mom, fragility=0.1)

    res = ConfirmationGate().compute(pd.DataFrame(), lead_lag, score)

    assert res["status"] == "ok"
    assert res["leaders_agree"] is False
    assert res["state"] == "unconfirmed"
