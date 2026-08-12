"""Exporta los modelos ya ajustados (todas las competiciones) a un JSON
compacto que un motor de predicción en JavaScript puede consumir sin
backend: coeficientes de Dixon-Coles, coeficientes de las Poisson de
equipo + la forma actual de cada equipo, las cuotas de tiro de cada
jugador, y los puntos de la calibración isotónica (para reproducir
`IsotonicRegression.predict` con interpolación lineal en el navegador).

Uso:
    python -m futbol.export_web [ruta_salida.json]
"""
from __future__ import annotations

import json
import pathlib
import sys

from futbol.config import CONFIDENCE_MIN, MIN_PLAYER_HISTORY, ROOT_DIR
from futbol.models.calibration import GOAL_LINES, TEAM_STAT_LINES
from futbol.models.poisson_markets import STAT_TARGETS
from futbol.pipeline import build_all_pipelines

TEAM_FORM_COLS = [f"roll_{stat}_{side}" for stat in STAT_TARGETS for side in ("for", "against")]


def _export_competition(pipeline) -> dict:
    dc = pipeline.dixon_coles

    poisson_models = {}
    for stat, mdl in pipeline.poisson_models.items():
        poisson_models[stat] = {
            "coef": mdl.model.coef_.tolist(),
            "intercept": float(mdl.model.intercept_),
        }

    team_form = {}
    for team in dc.teams_:
        if team not in pipeline.team_form.index:
            continue
        row = pipeline.team_form.loc[team]
        team_form[team] = {col: float(row[col]) for col in TEAM_FORM_COLS if col in row}

    players = []
    pf = pipeline.player_form
    eligible = pf[pf["player_matches_played"] >= MIN_PLAYER_HISTORY]
    for _, row in eligible.iterrows():
        team = row["team"]
        tf = team_form.get(team)
        if not tf or tf.get("roll_shots_for", 0) <= 0:
            continue
        shots_share = float(row["roll_shots"]) / tf["roll_shots_for"]
        sot_share = float(row["roll_shots_on_target"]) / max(tf.get("roll_shots_on_target_for", 1e-6), 1e-6)
        players.append({
            "name": row["player_name"],
            "team": team,
            "matches": int(row["player_matches_played"]),
            "shots_share": shots_share,
            "sot_share": sot_share,
        })

    calibrators = {}
    for family, iso in pipeline.calibrators.items():
        calibrators[family] = {
            "x": iso.X_thresholds_.tolist(),
            "y": iso.y_thresholds_.tolist(),
        }

    return {
        "competition": pipeline.competition,
        "n_matches": int(len(pipeline.matches_df)),
        "teams": sorted(dc.teams_),
        "dixon_coles": {
            "attack": {t: float(v) for t, v in dc.attack_.items()},
            "defense": {t: float(v) for t, v in dc.defense_.items()},
            "home_adv": dc.home_adv_,
            "rho": dc.rho_,
            "mu": dc.mu_,
            "max_goals": dc.max_goals,
        },
        "poisson_models": poisson_models,
        "team_form": team_form,
        "players": players,
        "calibrators": calibrators,
    }


def main() -> None:
    out_path = sys.argv[1] if len(sys.argv) > 1 else str(ROOT_DIR / "web" / "model_data.json")

    pipelines = build_all_pipelines(run_backtest=True)
    data = {
        "confidence_min": CONFIDENCE_MIN,
        "goal_lines": GOAL_LINES,
        "team_stat_lines": TEAM_STAT_LINES,
        "stat_targets": STAT_TARGETS,
        "competitions": [_export_competition(p) for _, p in sorted(pipelines.items())],
    }

    path = pathlib.Path(out_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, separators=(",", ":"))

    size_kb = path.stat().st_size / 1024
    print(f"Guardado {path} ({size_kb:.0f} KB, {len(data['competitions'])} competiciones)")


if __name__ == "__main__":
    main()
