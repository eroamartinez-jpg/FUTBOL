"""Features de forma por equipo: formato largo, medias móviles sin fuga y Elo.

Todas las medias móviles usadas para ENTRENAR se calculan con `shift(1)` antes
del `rolling`, de modo que la fila del partido X solo ve partidos anteriores a X.
Para PREDECIR un partido futuro se usa `latest_team_form`, que promedia los
últimos `window` partidos ya jugados (equivalente a la media móvil que le
tocaría al próximo partido de ese equipo).
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

STAT_PAIRS = {
    "goals": ("home_goals", "away_goals"),
    "shots": ("home_shots", "away_shots"),
    "shots_on_target": ("home_shots_on_target", "away_shots_on_target"),
    "corners": ("home_corners", "away_corners"),
    "yellow": ("home_yellow", "away_yellow"),
    "red": ("home_red", "away_red"),
}
STAT_NAMES = list(STAT_PAIRS.keys())


def to_long_format(matches_df: pd.DataFrame) -> pd.DataFrame:
    """Una fila por equipo y partido (perspectiva del equipo)."""
    rows = []
    for _, m in matches_df.iterrows():
        home = {"match_id": m["match_id"], "date": m["date"], "team": m["home_team"],
                "opponent": m["away_team"], "is_home": True}
        away = {"match_id": m["match_id"], "date": m["date"], "team": m["away_team"],
                "opponent": m["home_team"], "is_home": False}
        for stat, (home_col, away_col) in STAT_PAIRS.items():
            home[f"{stat}_for"] = m[home_col]
            home[f"{stat}_against"] = m[away_col]
            away[f"{stat}_for"] = m[away_col]
            away[f"{stat}_against"] = m[home_col]
        home["cards_for"] = home["yellow_for"] + home["red_for"]
        home["cards_against"] = home["yellow_against"] + home["red_against"]
        away["cards_for"] = away["yellow_for"] + away["red_for"]
        away["cards_against"] = away["yellow_against"] + away["red_against"]
        rows.append(home)
        rows.append(away)

    long_df = pd.DataFrame(rows)
    long_df["date"] = pd.to_datetime(long_df["date"])
    return long_df.sort_values(["date", "match_id"]).reset_index(drop=True)


def _rolling_stat_cols() -> list[str]:
    cols = []
    for stat in STAT_NAMES + ["cards"]:
        cols.append(f"{stat}_for")
        cols.append(f"{stat}_against")
    return cols


def add_rolling_features(long_df: pd.DataFrame, window: int, min_periods: int) -> pd.DataFrame:
    """Añade columnas roll_<stat>_for / roll_<stat>_against (sin fuga de datos)."""
    long_df = long_df.sort_values(["team", "date", "match_id"]).reset_index(drop=True)
    cols = _rolling_stat_cols()

    grouped = long_df.groupby("team", sort=False)
    for col in cols:
        shifted = grouped[col].shift(1)
        long_df[f"roll_{col}"] = (
            shifted.groupby(long_df["team"])
            .rolling(window=window, min_periods=min_periods)
            .mean()
            .reset_index(level=0, drop=True)
        )
    long_df["matches_played"] = grouped.cumcount()
    return long_df.sort_values(["date", "match_id"]).reset_index(drop=True)


def add_opponent_features(long_df: pd.DataFrame) -> pd.DataFrame:
    """Añade, a cada fila (equipo, partido), las columnas roll_* del rival
    en ese mismo partido (prefijo opp_), útiles como features de un GLM.
    """
    cols = [f"roll_{c}" for c in _rolling_stat_cols()]
    mirror = long_df[["match_id", "team"] + cols].rename(
        columns={"team": "opponent", **{c: f"opp_{c}" for c in cols}}
    )
    return long_df.merge(mirror, on=["match_id", "opponent"], how="left")


def latest_team_form(long_df: pd.DataFrame, window: int) -> pd.DataFrame:
    """Forma actual de cada equipo (media de sus últimos `window` partidos jugados).

    Es la feature a usar para predecir el PRÓXIMO partido de cada equipo.
    """
    cols = _rolling_stat_cols()
    recent = long_df.sort_values(["team", "date"]).groupby("team", sort=False).tail(window)
    agg = recent.groupby("team")[cols].mean()
    counts = long_df.groupby("team").size().rename("matches_played")
    agg = agg.join(counts)
    agg.columns = [f"roll_{c}" if c != "matches_played" else c for c in agg.columns]
    return agg


# --- Elo (metodología World Football Elo Ratings, eloratings.net) ---

def _mov_multiplier(goal_diff: int) -> float:
    gd = abs(goal_diff)
    if gd <= 1:
        return 1.0
    if gd == 2:
        return 1.5
    return (11 + gd) / 8


def compute_elo(matches_df: pd.DataFrame, k: float = 32.0, home_adv: float = 60.0,
                 base_rating: float = 1500.0) -> tuple[pd.DataFrame, dict[str, float]]:
    """Devuelve (matches_df con pre_elo_home/pre_elo_away, ratings finales por equipo)."""
    ratings: dict[str, float] = {}
    pre_home, pre_away = [], []

    for _, m in matches_df.sort_values(["date", "match_id"]).iterrows():
        h, a = m["home_team"], m["away_team"]
        elo_h = ratings.get(h, base_rating)
        elo_a = ratings.get(a, base_rating)
        pre_home.append(elo_h)
        pre_away.append(elo_a)

        expected_h = 1.0 / (1.0 + 10 ** (-((elo_h + home_adv) - elo_a) / 400.0))
        gd = int(m["home_goals"]) - int(m["away_goals"])
        if gd > 0:
            score_h = 1.0
        elif gd == 0:
            score_h = 0.5
        else:
            score_h = 0.0

        delta = k * _mov_multiplier(gd) * (score_h - expected_h)
        ratings[h] = elo_h + delta
        ratings[a] = elo_a - delta

    out = matches_df.sort_values(["date", "match_id"]).reset_index(drop=True).copy()
    out["pre_elo_home"] = pre_home
    out["pre_elo_away"] = pre_away
    return out, ratings
