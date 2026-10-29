"""Backtest walk-forward de la estrategia sobre el historial de un activo.

Sirve para no confiar a ciegas en la señal: un activo solo se recomienda si,
en sus propias velas recientes, las señales con confianza >= umbral acertaron
más que el porcentaje de equilibrio que exige su payout.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .strategy import score_frame


@dataclass
class BacktestResult:
    trades: int
    wins: int
    win_rate: float          # 0-1
    breakeven: float         # 0-1, win rate mínimo para no perder dinero
    expectancy: float        # ganancia media por unidad apostada

    @property
    def edge(self) -> bool:
        return self.trades > 0 and self.win_rate > self.breakeven


def breakeven_rate(payout: float) -> float:
    """Con payout p (0.92 = 92%), se gana p y se pierde 1: equilibrio = 1/(1+p)."""
    return 1.0 / (1.0 + payout)


def backtest(
    df: pd.DataFrame,
    payout: float = 0.85,
    expiry_candles: int = 1,
    min_confidence: float = 60.0,
    delay_candles: int = 0,
) -> BacktestResult:
    """`delay_candles` = velas que pasan entre el cierre de la vela que da la
    señal y la entrada real (0 = se entra en cuanto cierra; 1 = se espera a
    la apertura de la siguiente vela completa, típico al operar a mano)."""
    frame = score_frame(df)
    close = df["close"].to_numpy()
    n = len(df)
    # Señal en el cierre de la vela i -> entra en ~close[i + delay] y sale en
    # el cierre de la vela i + delay + expiry_candles.
    idx = np.arange(max(n - expiry_candles - delay_candles, 0))
    conf = frame["confidence"].to_numpy()[idx]
    direction = frame["direction"].to_numpy()[idx]
    take = (conf >= min_confidence) & (direction != "NEUTRAL")
    entry = close[idx + delay_candles][take]
    exit_ = close[idx + delay_candles + expiry_candles][take]
    sign = np.where(direction[take] == "CALL", 1.0, -1.0)
    move = (exit_ - entry) * sign
    # Empate (precio igual) en Pocket Option devuelve la apuesta: no cuenta.
    decided = move != 0
    wins = int((move[decided] > 0).sum())
    trades = int(decided.sum())
    win_rate = wins / trades if trades else 0.0
    expectancy = (win_rate * payout - (1 - win_rate)) if trades else 0.0
    return BacktestResult(trades, wins, win_rate, breakeven_rate(payout), expectancy)
