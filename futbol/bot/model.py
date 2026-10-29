"""Ajusta el Dixon-Coles del proyecto sobre un histórico de resultados."""
from __future__ import annotations

import warnings

import pandas as pd

from futbol.models.dixon_coles import DixonColes


def fit_model(history: pd.DataFrame, as_of: pd.Timestamp | None = None,
              max_history_days: int = 540, half_life_days: float = 180.0) -> DixonColes:
    """Dixon-Coles con los partidos jugados ANTES de `as_of` (sin fuga de datos)."""
    df = history.dropna(subset=["home_goals", "away_goals"])
    if as_of is not None:
        df = df[df["date"] < as_of]
        df = df[df["date"] >= as_of - pd.Timedelta(days=max_history_days)]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return DixonColes(half_life_days=half_life_days).fit(df)


def team_match_counts(history: pd.DataFrame) -> pd.Series:
    return pd.concat([history["home_team"], history["away_team"]]).value_counts()
