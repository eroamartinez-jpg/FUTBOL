"""Features de forma por jugador: tiros y tiros a puerta por partido.

Igual que en team_form: las columnas roll_* usadas para entrenar están
desplazadas (shift) para no ver el propio partido; `latest_player_form` da
la forma actual (para predecir el próximo partido de cada jugador).
"""
from __future__ import annotations

import pandas as pd

from futbol.config import MIN_PLAYER_HISTORY, PLAYER_ROLLING_WINDOW


def add_rolling_player_features(players_df: pd.DataFrame,
                                 window: int = PLAYER_ROLLING_WINDOW,
                                 min_periods: int = MIN_PLAYER_HISTORY) -> pd.DataFrame:
    df = players_df.sort_values(["player_id", "date", "match_id"]).reset_index(drop=True)
    df["date"] = pd.to_datetime(df["date"])

    grouped = df.groupby("player_id", sort=False)
    for col in ("shots", "shots_on_target"):
        shifted = grouped[col].shift(1)
        df[f"roll_{col}"] = (
            shifted.groupby(df["player_id"])
            .rolling(window=window, min_periods=min_periods)
            .mean()
            .reset_index(level=0, drop=True)
        )
    df["player_matches_played"] = grouped.cumcount()
    return df.sort_values(["date", "match_id"]).reset_index(drop=True)


def latest_player_form(players_df: pd.DataFrame, window: int = PLAYER_ROLLING_WINDOW) -> pd.DataFrame:
    """Última forma conocida de cada jugador: media de tiros/tiros a puerta
    en sus últimos `window` partidos, más el equipo con el que jugó el último partido.
    """
    df = players_df.sort_values(["player_id", "date"])
    recent = df.groupby("player_id", sort=False).tail(window)
    agg = recent.groupby("player_id").agg(
        roll_shots=("shots", "mean"),
        roll_shots_on_target=("shots_on_target", "mean"),
        player_matches_played=("shots", "count"),
    )
    last_team = df.groupby("player_id").tail(1).set_index("player_id")[["player_name", "team"]]
    return agg.join(last_team)
