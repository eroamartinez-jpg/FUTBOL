from datetime import datetime, timezone

import numpy as np
import pandas as pd

from pocket_bot.backtest import backtest, breakeven_rate
from pocket_bot.data import SyntheticSource, candles_to_frame
from pocket_bot.indicators import rsi
from pocket_bot.scanner import scan
from pocket_bot.strategy import latest_signal, score_frame
from pocket_bot.timing import entry_window, next_candle_open


def _trend(n=300, slope=0.001, noise=0.0002, seed=0):
    rng = np.random.default_rng(seed)
    close = 1 + np.cumsum(slope + rng.normal(0, noise, n))
    open_ = np.concatenate([[close[0]], close[:-1]])
    idx = pd.date_range("2026-01-01", periods=n, freq="60s", tz="UTC")
    return pd.DataFrame({"open": open_, "close": close,
                         "high": np.maximum(open_, close) + 1e-4,
                         "low": np.minimum(open_, close) - 1e-4}, index=idx)


def test_uptrend_gives_call_and_downtrend_put():
    assert latest_signal("X", _trend(slope=0.001)).direction == "CALL"
    assert latest_signal("X", _trend(slope=-0.001)).direction == "PUT"


def test_score_is_causal():
    df = _trend(seed=3)
    full = score_frame(df)["score"]
    partial = score_frame(df.iloc[:200])["score"]
    pd.testing.assert_series_equal(full.iloc[:200], partial)


def test_rsi_bounds():
    r = rsi(_trend(noise=0.002)["close"]).iloc[1:]
    assert r.between(0, 100).all()


def test_breakeven():
    assert abs(breakeven_rate(1.0) - 0.5) < 1e-12
    assert abs(breakeven_rate(0.92) - 1 / 1.92) < 1e-12


def test_backtest_wins_on_clean_trend_and_delay_shifts_entry():
    df = _trend(slope=0.001, noise=0.00005)
    res = backtest(df, payout=0.9, min_confidence=50)
    assert res.trades > 100 and res.win_rate > 0.9 and res.edge
    assert backtest(df, 0.9, 1, 50, delay_candles=1).trades == res.trades - 1


def test_next_candle_open_and_entry_window():
    now = datetime(2026, 1, 1, 12, 0, 30, tzinfo=timezone.utc)
    assert next_candle_open(now, 60) == datetime(2026, 1, 1, 12, 1, tzinfo=timezone.utc)
    w = entry_window(60, expiry_candles=2, now=now, tz="UTC")
    assert (w.entry.hour, w.entry.minute, w.entry.second) == (12, 1, 0)
    assert (w.expiry.hour, w.expiry.minute) == (12, 3)
    assert w.seconds_left == 30 and w.duration_s == 120
    # Con menos de 5 s de margen salta a la vela siguiente.
    late = datetime(2026, 1, 1, 12, 0, 57, tzinfo=timezone.utc)
    assert entry_window(60, now=late, tz="UTC").entry.minute == 2


def test_candles_to_frame_accepts_epoch_and_iso():
    rows = [{"time": 1_700_000_060, "open": 1, "high": 2, "low": 0.5, "close": 1.5},
            {"time": 1_700_000_000, "open": 1, "high": 2, "low": 0.5, "close": 1.2}]
    df = candles_to_frame(rows)
    assert df.index.is_monotonic_increasing and len(df) == 2
    iso = candles_to_frame([{"time": "2026-01-01T00:00:00Z", "open": 1, "high": 1,
                             "low": 1, "close": 1}])
    assert iso.index[0] == pd.Timestamp("2026-01-01", tz="UTC")


def test_scan_synthetic_covers_assets_with_payout_filter():
    src = SyntheticSource()
    opps = scan(src, min_payout=85, min_trades=5)
    assert {o.signal.asset for o in opps} == set(src.assets(85))
    for o in opps:
        if o.recommended:
            assert o.stats.win_rate > o.stats.breakeven
