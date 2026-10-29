"""Estrategia de confluencia: cada indicador vota CALL (+) o PUT (-).

El puntaje se normaliza a [-1, 1] y se modula por la fuerza de tendencia
(ADX): en mercados laterales la confianza baja, porque los indicadores de
tendencia dan muchas señales falsas ahí.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from . import indicators as ind

WARMUP = 60  # velas necesarias para que los indicadores se estabilicen

# Peso de cada voto en el puntaje total.
WEIGHTS = {
    "ema_cross": 1.5,   # EMA 9 vs EMA 21
    "ema_trend": 1.0,   # precio vs EMA 50
    "macd": 1.0,        # signo del histograma MACD
    "macd_slope": 0.5,  # histograma creciendo / decreciendo
    "rsi": 1.0,         # RSI de lado alcista/bajista sin sobreextensión
    "stoch": 0.5,       # %K vs %D
    "bollinger": 0.5,   # precio vs media de Bollinger
}


@dataclass
class Signal:
    asset: str
    direction: str          # "CALL", "PUT" o "NEUTRAL"
    confidence: float       # 0-100
    score: float            # -1..1
    adx: float
    rsi: float
    last_close: float
    last_time: pd.Timestamp
    reasons: list[str] = field(default_factory=list)


def score_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Calcula puntaje, dirección y confianza para cada vela de `df`.

    `df` necesita columnas open/high/low/close indexadas por tiempo. El valor
    de la fila i solo depende de las velas <= i, así que se puede usar tal
    cual para backtest.
    """
    close = df["close"]
    e9, e21, e50 = ind.ema(close, 9), ind.ema(close, 21), ind.ema(close, 50)
    m = ind.macd(close)
    r = ind.rsi(close)
    st = ind.stochastic(df)
    bb = ind.bollinger(close)
    a = ind.adx(df)

    votes = pd.DataFrame(index=df.index)
    votes["ema_cross"] = np.sign(e9 - e21)
    votes["ema_trend"] = np.sign(close - e50)
    votes["macd"] = np.sign(m["hist"])
    votes["macd_slope"] = np.sign(m["hist"].diff())
    # RSI: alcista entre 50 y 70, bajista entre 30 y 50; en extremos no vota
    # (el precio ya está sobreextendido y es más probable un rebote).
    votes["rsi"] = np.select([(r > 50) & (r < 70), (r < 50) & (r > 30)], [1.0, -1.0], 0.0)
    votes["stoch"] = np.sign(st["k"] - st["d"])
    votes["bollinger"] = np.sign(close - bb["mid"])
    votes = votes.fillna(0.0)

    total = sum(WEIGHTS.values())
    score = sum(votes[k] * w for k, w in WEIGHTS.items()) / total
    # ADX < 15: lateral, la confianza cae a la mitad; ADX >= 30: plena.
    adx_factor = np.clip(0.5 + (a - 15) / 30, 0.5, 1.0)
    confidence = (score.abs() * adx_factor * 100).round(1)

    out = pd.DataFrame({
        "score": score,
        "confidence": confidence,
        "direction": np.where(score > 0, "CALL", np.where(score < 0, "PUT", "NEUTRAL")),
        "adx": a,
        "rsi": r,
    }, index=df.index)
    out.iloc[:WARMUP, out.columns.get_loc("confidence")] = 0.0
    out.iloc[:WARMUP, out.columns.get_loc("direction")] = "NEUTRAL"
    out.attrs["votes"] = votes
    return out


def latest_signal(asset: str, df: pd.DataFrame) -> Signal:
    frame = score_frame(df)
    last = frame.iloc[-1]
    votes = frame.attrs["votes"].iloc[-1]
    reasons = [f"{k}:{'+' if v > 0 else '-'}" for k, v in votes.items() if v != 0]
    return Signal(
        asset=asset,
        direction=str(last["direction"]),
        confidence=float(last["confidence"]),
        score=float(last["score"]),
        adx=float(last["adx"]),
        rsi=float(last["rsi"]),
        last_close=float(df["close"].iloc[-1]),
        last_time=df.index[-1],
        reasons=reasons,
    )
