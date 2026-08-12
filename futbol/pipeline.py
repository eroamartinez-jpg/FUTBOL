"""Construye, en memoria, todo lo necesario para predecir un partido.

El dataset mezcla ligas y torneos muy distintos (una liga femenina
doméstica no anota goles al mismo ritmo que un Mundial masculino, y la
"ventaja de local" de un club en su estadio no existe igual en un torneo de
selecciones a sede neutral). Por eso NO se ajusta un único modelo global:
se agrupa por la columna `competition` y se entrena un DixonColes + juego
de modelos Poisson + calibración independiente por cada una.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from futbol.config import (
    MIN_PLAYER_HISTORY,
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
class CompetitionPipeline:
    competition: str
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


# Alias por compatibilidad hacia atrás (nombre usado en versiones previas del CLI).
FutbolPipeline = CompetitionPipeline


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


def _build_one(competition: str, matches_df: pd.DataFrame, players_df: pd.DataFrame,
                run_backtest: bool) -> CompetitionPipeline | None:
    matches_df = matches_df.sort_values("date").reset_index(drop=True)
    if matches_df["home_team"].nunique() < 2 or len(matches_df) < 6:
        return None

    long_df = to_long_format(matches_df)
    long_df = add_rolling_features(long_df, TEAM_ROLLING_WINDOW, MIN_TEAM_HISTORY)
    long_df = add_opponent_features(long_df)
    team_form = latest_team_form(long_df, TEAM_ROLLING_WINDOW)

    match_ids = set(matches_df["match_id"])
    comp_players_df = players_df[players_df["match_id"].isin(match_ids)]
    players_feat = add_rolling_player_features(comp_players_df, PLAYER_ROLLING_WINDOW, MIN_PLAYER_HISTORY)
    player_form = latest_player_form(players_feat, PLAYER_ROLLING_WINDOW)

    dc = DixonColes().fit(matches_df)
    poisson_models = fit_all(long_df)

    calibrators = {}
    if run_backtest:
        backtest_df = walk_forward_backtest(matches_df)
        if not backtest_df.empty:
            calibrators = fit_calibrators(backtest_df)

    return CompetitionPipeline(
        competition=competition,
        matches_df=matches_df,
        players_df=comp_players_df,
        long_df=long_df,
        team_form=team_form,
        player_form=player_form,
        dixon_coles=dc,
        poisson_models=poisson_models,
        calibrators=calibrators,
    )


def build_all_pipelines(run_backtest: bool = True) -> dict[str, CompetitionPipeline]:
    """Devuelve {nombre_competición: CompetitionPipeline}, una por cada
    competición del dataset con suficientes partidos y equipos.
    """
    matches_df, players_df = load_processed_data()
    matches_df["date"] = pd.to_datetime(matches_df["date"])

    pipelines: dict[str, CompetitionPipeline] = {}
    for competition, comp_matches in matches_df.groupby("competition"):
        pipeline = _build_one(competition, comp_matches, players_df, run_backtest)
        if pipeline is not None:
            pipelines[competition] = pipeline
    return pipelines


def find_team_competitions(pipelines: dict[str, CompetitionPipeline], team: str) -> list[str]:
    """Competiciones en las que existe un equipo con ese nombre exacto."""
    return [name for name, p in pipelines.items() if team in p.dixon_coles.teams_]
