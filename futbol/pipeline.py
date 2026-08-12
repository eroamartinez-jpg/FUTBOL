"""Construye, en memoria, todo lo necesario para predecir un partido:
datos procesados, features walk-forward, modelos ajustados y calibradores.
Se usa tanto desde predict.py como desde evaluate.py.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from futbol.config import (
    CONFIDENCE_MIN,
    MIN_TEAM_HISTORY,
    PLAYER_ROLLING_WINDOW,
    PROCESSED_DIR,
    TEAM_ROLLING_WINDOW,
)
from futbol.features.player_form import add_rolling_player_features, latest_player_form
from futbol.features.team_form import (
    add_opponent_features,
    add_rolling_features,
    latest_team_form,
    to_long_format,
)
from futbol.models.calibration import apply_calibration, fit_calibrators, walk_forward_backtest
from futbol.models.dixon_coles import DixonColes
from futbol.models.poisson_markets import fit_all


@dataclass
class FutbolPipeline:
    matches_df: pd.DataFrame
    players_df: pd.DataFrame
    long_df: pd.DataFrame
    team_form: pd.DataFrame
    player_form: pd.DataFrame
    dixon_coles: DixonColes
    poisson_models: dict
    calibrators: dict

    def calibrate(self, raw_prob: float, family: str) -> float:
        return apply_calibration(raw_prob, family, self.calibrators)


def load_processed_data() -> tuple[pd.DataFrame, pd.DataFrame]:
    matches_path = PROCESSED_DIR / "matches.csv"
    players_path = PROCESSED_DIR / "player_match.csv"
    if not matches_path.exists() or not players_path.exists():
        raise FileNotFoundError(
            "No se encontraron los datos procesados. Ejecuta primero:\n"
            "  python -m futbol.data.build_dataset"
        )
    matches_df = pd.read_csv(matches_path)
    players_df = pd.read_csv(players_path)
    return matches_df, players_df


def build_pipeline(run_backtest: bool = True) -> FutbolPipeline:
    matches_df, players_df = load_processed_data()
    matches_df["date"] = pd.to_datetime(matches_df["date"])

    long_df = to_long_format(matches_df)
    long_df = add_rolling_features(long_df, TEAM_ROLLING_WINDOW, MIN_TEAM_HISTORY)
    long_df = add_opponent_features(long_df)
    team_form = latest_team_form(long_df, TEAM_ROLLING_WINDOW)

    players_feat = add_rolling_player_features(players_df, PLAYER_ROLLING_WINDOW)
    player_form = latest_player_form(players_feat, PLAYER_ROLLING_WINDOW)

    dc = DixonColes().fit(matches_df)
    poisson_models = fit_all(long_df)

    calibrators = {}
    if run_backtest:
        backtest_df = walk_forward_backtest(matches_df)
        calibrators = fit_calibrators(backtest_df)

    return FutbolPipeline(
        matches_df=matches_df,
        players_df=players_df,
        long_df=long_df,
        team_form=team_form,
        player_form=player_form,
        dixon_coles=dc,
        poisson_models=poisson_models,
        calibrators=calibrators,
    )
