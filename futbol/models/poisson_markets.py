"""Regresión Poisson por equipo para corners, tarjetas, tiros y tiros a puerta.

Para cada estadística `stat` (corners, cards, shots, shots_on_target) se
entrena un modelo que predice el valor "for" (a favor) de un equipo en un
partido a partir de:
  - is_home
  - su propia media móvil de esa stat (a favor / en contra)
  - la media móvil del rival en esa stat (a favor / en contra)
Estas features ya están desplazadas en el tiempo (ver features/team_form.py),
por lo que no hay fuga de información del resultado del propio partido.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import poisson
from sklearn.linear_model import PoissonRegressor

STAT_TARGETS = ["corners", "cards", "shots", "shots_on_target"]


def _feature_cols(stat: str) -> list[str]:
    return [
        "is_home",
        f"roll_{stat}_for",
        f"roll_{stat}_against",
        f"opp_roll_{stat}_for",
        f"opp_roll_{stat}_against",
    ]


class TeamPoissonMarket:
    """Modelo Poisson de una estadística de equipo (p.ej. corners a favor)."""

    def __init__(self, stat: str, alpha: float = 0.5):
        if stat not in STAT_TARGETS:
            raise ValueError(f"stat desconocida: {stat}")
        self.stat = stat
        self.alpha = alpha
        self.model = PoissonRegressor(alpha=alpha, max_iter=500)
        self.feature_cols = _feature_cols(stat)

    def fit(self, long_df: pd.DataFrame) -> "TeamPoissonMarket":
        df = long_df.dropna(subset=self.feature_cols + [f"{self.stat}_for"]).copy()
        X = df[self.feature_cols].to_numpy(dtype=float)
        X[:, 0] = X[:, 0].astype(float)  # is_home ya es 0/1
        y = df[f"{self.stat}_for"].to_numpy(dtype=float)
        self.model.fit(X, y)
        self.n_train_ = len(df)
        return self

    def predict_mean(self, is_home: bool, own_form: pd.Series, opp_form: pd.Series) -> float:
        row = {
            "is_home": 1.0 if is_home else 0.0,
            f"roll_{self.stat}_for": own_form[f"roll_{self.stat}_for"],
            f"roll_{self.stat}_against": own_form[f"roll_{self.stat}_against"],
            f"opp_roll_{self.stat}_for": opp_form[f"roll_{self.stat}_for"],
            f"opp_roll_{self.stat}_against": opp_form[f"roll_{self.stat}_against"],
        }
        X = np.array([[row[c] for c in self.feature_cols]], dtype=float)
        return float(self.model.predict(X)[0])


def fit_all(long_df: pd.DataFrame) -> dict[str, TeamPoissonMarket]:
    return {stat: TeamPoissonMarket(stat).fit(long_df) for stat in STAT_TARGETS}


def line_probabilities(mu: float, lines: list[float]) -> dict[float, dict[str, float]]:
    """Para una media Poisson `mu`, probabilidad de over/under en cada línea."""
    out = {}
    for line in lines:
        threshold = int(np.floor(line))
        under = float(poisson.cdf(threshold, mu))
        over = 1.0 - under
        out[line] = {"over": over, "under": under}
    return out


def best_confident_pick(mu: float, lines: list[float], min_conf: float) -> dict | None:
    """Devuelve la línea/lado con mayor probabilidad si supera `min_conf`."""
    probs = line_probabilities(mu, lines)
    best = None
    for line, sides in probs.items():
        for side, p in sides.items():
            if best is None or p > best["prob"]:
                best = {"line": line, "side": side, "prob": p}
    if best and best["prob"] >= min_conf:
        return best
    return None
