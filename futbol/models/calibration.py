"""Backtest walk-forward y calibración de probabilidades.

Objetivo: verificar empíricamente que cuando el modelo dice "75% de
probabilidad" acierta de verdad ~75% de las veces (y no solo lo que asume
la Poisson teórica, que puede estar mal calibrada por sobredispersión en
corners/tarjetas/tiros). Se reentrena SOLO con partidos anteriores a cada
bloque evaluado, así los aciertos reportados son honestos (fuera de muestra).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import brier_score_loss

from futbol.config import CONFIDENCE_MIN, MIN_TEAM_HISTORY, TEAM_ROLLING_WINDOW
from futbol.features.team_form import add_opponent_features, add_rolling_features, to_long_format
from futbol.models.dixon_coles import DixonColes
from futbol.models.poisson_markets import STAT_TARGETS, TeamPoissonMarket, line_probabilities

GOAL_LINES = [1.5, 2.5, 3.5]
TEAM_STAT_LINES = {
    "corners": [2.5, 3.5, 4.5, 5.5, 6.5],
    "cards": [0.5, 1.5, 2.5, 3.5],
    "shots": [6.5, 9.5, 12.5, 15.5],
    "shots_on_target": [2.5, 3.5, 4.5, 5.5],
}


def _record_best(records: list, family: str, market: str, match_id, probs: dict[str, float],
                  actual_side: str) -> None:
    side, prob = max(probs.items(), key=lambda kv: kv[1])
    records.append({
        "match_id": match_id, "family": family, "market": market,
        "side": side, "raw_prob": prob, "outcome": int(side == actual_side),
    })


def _adaptive_backtest_params(n: int) -> tuple[int, int]:
    """Ajusta burn_in/refit_every al tamaño de la competición.

    Una liga de 380 partidos admite el esquema clásico (80/20). Un torneo
    de 31-64 partidos (Eurocopa, Copa América...) necesita una ventana de
    calentamiento y de reentrenamiento mucho más pequeña, o directamente no
    quedan partidos para evaluar.
    """
    burn_in = max(12, min(80, n // 3))
    refit_every = max(4, min(20, n // 8))
    return burn_in, refit_every


def walk_forward_backtest(matches_df: pd.DataFrame, burn_in: int | None = None,
                           refit_every: int | None = None) -> pd.DataFrame:
    matches_df = matches_df.copy()
    matches_df["date"] = pd.to_datetime(matches_df["date"])
    matches_df = matches_df.sort_values(["date", "match_id"]).reset_index(drop=True)

    if burn_in is None or refit_every is None:
        auto_burn_in, auto_refit_every = _adaptive_backtest_params(len(matches_df))
        burn_in = burn_in if burn_in is not None else auto_burn_in
        refit_every = refit_every if refit_every is not None else auto_refit_every

    if len(matches_df) < burn_in + 4:
        return pd.DataFrame(columns=["match_id", "family", "market", "side", "raw_prob", "outcome"])

    long_df = to_long_format(matches_df)
    long_df = add_rolling_features(long_df, TEAM_ROLLING_WINDOW, MIN_TEAM_HISTORY)
    long_df = add_opponent_features(long_df)
    long_df = long_df.set_index(["match_id", "team"])

    records: list[dict] = []
    n = len(matches_df)

    for start in range(burn_in, n, refit_every):
        train = matches_df.iloc[:start]
        block = matches_df.iloc[start:start + refit_every]
        if block.empty or train["home_team"].nunique() < 2:
            continue

        dc = DixonColes().fit(train)
        train_ids = set(train["match_id"])
        train_long = long_df.reset_index()
        train_long = train_long[train_long["match_id"].isin(train_ids)]
        poisson_models = {stat: TeamPoissonMarket(stat).fit(train_long) for stat in STAT_TARGETS}

        for _, m in block.iterrows():
            home, away, mid = m["home_team"], m["away_team"], m["match_id"]
            if home not in dc.teams_ or away not in dc.teams_:
                continue

            markets = dc.markets(home, away)
            actual_total = m["home_goals"] + m["away_goals"]
            actual_1x2 = "home_win" if m["home_goals"] > m["away_goals"] else (
                "away_win" if m["home_goals"] < m["away_goals"] else "draw")
            _record_best(records, "dixon_coles", "1x2", mid, markets["1x2"], actual_1x2)

            actual_btts = "yes" if (m["home_goals"] > 0 and m["away_goals"] > 0) else "no"
            _record_best(records, "dixon_coles", "btts", mid, markets["btts"], actual_btts)

            for line in GOAL_LINES:
                probs = markets["total_goals"][line]
                actual_side = "over" if actual_total > line else "under"
                _record_best(records, "dixon_coles", f"goals_{line}", mid, probs, actual_side)

            try:
                home_row = long_df.loc[(mid, home)]
                away_row = long_df.loc[(mid, away)]
            except KeyError:
                continue
            if home_row[[f"roll_{s}_for" for s in STAT_TARGETS]].isna().any():
                continue
            if away_row[[f"roll_{s}_for" for s in STAT_TARGETS]].isna().any():
                continue

            for stat in STAT_TARGETS:
                mdl = poisson_models[stat]
                mu_home = mdl.predict_mean(True, home_row, away_row)
                mu_away = mdl.predict_mean(False, away_row, home_row)
                if stat == "cards":
                    actual_home_val = m["home_yellow"] + m["home_red"]
                    actual_away_val = m["away_yellow"] + m["away_red"]
                else:
                    actual_home_val = m[f"home_{stat}"]
                    actual_away_val = m[f"away_{stat}"]
                for line in TEAM_STAT_LINES[stat]:
                    probs_h = line_probabilities(mu_home, [line])[line]
                    actual_side_h = "over" if actual_home_val > line else "under"
                    _record_best(records, "poisson_market", f"{stat}_home_{line}", mid, probs_h, actual_side_h)
                    probs_a = line_probabilities(mu_away, [line])[line]
                    actual_side_a = "over" if actual_away_val > line else "under"
                    _record_best(records, "poisson_market", f"{stat}_away_{line}", mid, probs_a, actual_side_a)

    return pd.DataFrame(records)


def fit_calibrators(backtest_df: pd.DataFrame) -> dict[str, IsotonicRegression]:
    calibrators = {}
    for family, grp in backtest_df.groupby("family"):
        iso = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
        iso.fit(grp["raw_prob"], grp["outcome"])
        calibrators[family] = iso
    return calibrators


def apply_calibration(raw_prob: float, family: str, calibrators: dict[str, IsotonicRegression]) -> float:
    if family not in calibrators:
        return raw_prob
    return float(calibrators[family].predict([raw_prob])[0])


def honest_calibration_report(backtest_df: pd.DataFrame, train_frac: float = 0.7) -> dict:
    """Divide el backtest en dos tramos temporales: ajusta el calibrador en el
    primero y mide el acierto real en el segundo (nunca visto por el
    calibrador), para que el hit-rate reportado no sea circular.
    """
    backtest_df = backtest_df.sort_values("match_id").reset_index(drop=True)
    cut = int(len(backtest_df) * train_frac)
    train_part = backtest_df.iloc[:cut]
    test_part = backtest_df.iloc[cut:]
    calibrators = fit_calibrators(train_part)

    report = {}
    for family, grp in test_part.groupby("family"):
        raw = grp["raw_prob"].to_numpy()
        y = grp["outcome"].to_numpy()
        calibrated = np.array([apply_calibration(p, family, calibrators) for p in raw])
        high_conf_mask = calibrated >= CONFIDENCE_MIN
        report[family] = {
            "n_test": len(grp),
            "brier_raw": float(brier_score_loss(y, raw)),
            "brier_calibrated": float(brier_score_loss(y, calibrated)),
            "n_high_confidence": int(high_conf_mask.sum()),
            "hit_rate_high_confidence": float(y[high_conf_mask].mean()) if high_conf_mask.any() else None,
        }
    return report


def evaluate_calibration(backtest_df: pd.DataFrame, calibrators: dict[str, IsotonicRegression] | None = None
                          ) -> dict:
    report = {}
    for family, grp in backtest_df.groupby("family"):
        raw = grp["raw_prob"].to_numpy()
        y = grp["outcome"].to_numpy()
        calibrated = raw if calibrators is None else np.array(
            [apply_calibration(p, family, calibrators) for p in raw]
        )
        high_conf_mask = calibrated >= CONFIDENCE_MIN
        report[family] = {
            "n": len(grp),
            "brier_raw": float(brier_score_loss(y, raw)),
            "brier_calibrated": float(brier_score_loss(y, calibrated)) if calibrators else None,
            "n_high_confidence": int(high_conf_mask.sum()),
            "hit_rate_high_confidence": float(y[high_conf_mask].mean()) if high_conf_mask.any() else None,
        }
    return report
