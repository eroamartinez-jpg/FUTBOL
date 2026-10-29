"""Escaneo de activos: señal + backtest + hora de entrada por activo."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import pandas as pd

from .backtest import BacktestResult, backtest
from .data import CandleSource
from .strategy import WARMUP, Signal, latest_signal
from .timing import EntryWindow, entry_window


@dataclass
class Opportunity:
    signal: Signal
    payout: int
    stats: BacktestResult
    window: EntryWindow
    recommended: bool


def delay_for(df: pd.DataFrame, period_s: int, entry: datetime) -> int:
    """Velas completas entre el cierre de la última vela y la entrada."""
    last_close = df.index[-1] + pd.Timedelta(seconds=period_s)
    return max(int(round((pd.Timestamp(entry) - last_close).total_seconds() / period_s)), 0)


def scan(
    source: CandleSource,
    period_s: int = 60,
    expiry_candles: int = 1,
    min_payout: int = 80,
    min_confidence: float = 60.0,
    min_trades: int = 20,
    count: int = 500,
    max_assets: int | None = None,
    tz: str | None = None,
    immediate: bool = False,
    on_error=None,
) -> list[Opportunity]:
    assets = sorted(source.assets(min_payout).items(), key=lambda kv: -kv[1])
    if max_assets:
        assets = assets[:max_assets]
    st = source.server_time()
    now = datetime.fromtimestamp(st, timezone.utc) if st else datetime.now(timezone.utc)

    out: list[Opportunity] = []
    for asset, payout in assets:
        try:
            df = source.candles(asset, period_s, count)
        except Exception as exc:  # un activo caído no debe tumbar el escaneo
            if on_error:
                on_error(asset, exc)
            continue
        if len(df) < WARMUP + 10:
            continue
        window = entry_window(period_s, expiry_candles, now=now, tz=tz, immediate=immediate)
        delay = 0 if immediate else delay_for(df, period_s, window.entry)
        stats = backtest(df, payout / 100, expiry_candles, min_confidence, delay)
        sig = latest_signal(asset, df)
        recommended = (
            sig.direction != "NEUTRAL"
            and sig.confidence >= min_confidence
            and stats.trades >= min_trades
            and stats.edge
        )
        out.append(Opportunity(sig, payout, stats, window, recommended))

    out.sort(key=lambda o: (o.recommended, o.stats.expectancy if o.recommended else 0,
                            o.signal.confidence), reverse=True)
    return out
