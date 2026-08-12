"""Proyección de tiros / tiros a puerta por jugador para un partido concreto.

Con pocos partidos por jugador (~20-30 en una temporada) un GLM por jugador
sobreajustaría. En su lugar se usa la "cuota de equipo" del jugador: su media
móvil de tiros dividida por la media móvil de tiros de su equipo, aplicada al
número de tiros que el modelo de equipo (TeamPoissonMarket) espera para ESE
partido concreto (que ya tiene en cuenta la fuerza del rival). Así el
pronóstico del jugador se ajusta partido a partido sin perder su patrón
individual de uso.
"""
from __future__ import annotations

import pandas as pd

from futbol.config import MIN_PLAYER_HISTORY
from futbol.models.poisson_markets import line_probabilities

PLAYER_SHOT_LINES = [0.5, 1.5, 2.5, 3.5]
PLAYER_SOT_LINES = [0.5, 1.5, 2.5]


def project_team_players(player_form: pd.DataFrame, team: str, team_roll_shots_for: float,
                          team_roll_sot_for: float, predicted_team_shots_mu: float,
                          predicted_team_sot_mu: float, top_n: int = 3,
                          min_history: int = MIN_PLAYER_HISTORY) -> list[dict]:
    """Proyecta tiros/tiros a puerta de los jugadores de `team` para este partido.

    `player_form` es la salida de features.player_form.latest_player_form.
    Se excluyen jugadores con menos de `min_history` partidos registrados
    (muestra demasiado pequeña para una media móvil fiable).
    Devuelve los `top_n` jugadores con más tiros esperados.
    """
    squad = player_form[
        (player_form["team"] == team) & (player_form["player_matches_played"] >= min_history)
    ].copy()
    if squad.empty:
        return []

    eps = 1e-6
    squad["shot_share"] = squad["roll_shots"] / max(team_roll_shots_for, eps)
    squad["sot_share"] = squad["roll_shots_on_target"] / max(team_roll_sot_for, eps)

    squad["proj_shots"] = (squad["shot_share"] * predicted_team_shots_mu).clip(lower=0.02)
    squad["proj_shots_on_target"] = (squad["sot_share"] * predicted_team_sot_mu).clip(lower=0.02)

    squad = squad.sort_values("proj_shots", ascending=False).head(top_n)

    results = []
    for _, row in squad.iterrows():
        results.append({
            "player_name": row["player_name"],
            "team": team,
            "matches_played": int(row["player_matches_played"]),
            "proj_shots": float(row["proj_shots"]),
            "proj_shots_on_target": float(row["proj_shots_on_target"]),
            "shots_lines": line_probabilities(row["proj_shots"], PLAYER_SHOT_LINES),
            "sot_lines": line_probabilities(row["proj_shots_on_target"], PLAYER_SOT_LINES),
        })
    return results
