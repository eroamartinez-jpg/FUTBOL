"""Modelo Dixon-Coles (Poisson bivariante con corrección de marcadores bajos).

Referencia: Dixon, M.J. and Coles, S.G. (1997), "Modelling Association
Football Scores and Inefficiencies in the Betting Market".

lambda_home = exp(mu + attack_home - defense_away + home_adv)
lambda_away = exp(mu + attack_away - defense_home)

tau(x,y) corrige la probabilidad de los marcadores 0-0, 1-0, 0-1 y 1-1,
donde la independencia Poisson simple se ajusta peor a los datos reales.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.stats import poisson


def _tau(x: int, y: int, lam: float, mu: float, rho: float) -> float:
    if x == 0 and y == 0:
        return 1 - lam * mu * rho
    if x == 0 and y == 1:
        return 1 + lam * rho
    if x == 1 and y == 0:
        return 1 + mu * rho
    if x == 1 and y == 1:
        return 1 - rho
    return 1.0


class DixonColes:
    def __init__(self, max_goals: int = 10, half_life_days: float = 180.0):
        self.max_goals = max_goals
        self.half_life_days = half_life_days
        self.teams_: list[str] = []
        self.attack_: dict[str, float] = {}
        self.defense_: dict[str, float] = {}
        self.home_adv_: float = 0.0
        self.rho_: float = 0.0
        self.mu_: float = 0.0

    def _weights(self, dates: pd.Series) -> np.ndarray:
        max_date = dates.max()
        age_days = (max_date - dates).dt.days.to_numpy()
        xi = math.log(2) / self.half_life_days
        return np.exp(-xi * age_days)

    def fit(self, matches_df: pd.DataFrame) -> "DixonColes":
        df = matches_df.copy()
        df["date"] = pd.to_datetime(df["date"])
        teams = sorted(set(df["home_team"]) | set(df["away_team"]))
        self.teams_ = teams
        n = len(teams)
        idx = {t: i for i, t in enumerate(teams)}

        weights = self._weights(df["date"])
        home_idx = df["home_team"].map(idx).to_numpy()
        away_idx = df["away_team"].map(idx).to_numpy()
        hg = df["home_goals"].to_numpy(dtype=float)
        ag = df["away_goals"].to_numpy(dtype=float)

        # x0: attack=0, defense=0, home_adv=0.2, rho=0, mu(base rate)=0.3
        x0 = np.concatenate([np.zeros(n), np.zeros(n), [0.2, 0.0, 0.3]])

        def unpack(x):
            attack = x[:n]
            defense = x[n:2 * n]
            home_adv, rho, mu = x[2 * n], x[2 * n + 1], x[2 * n + 2]
            return attack, defense, home_adv, rho, mu

        def neg_log_lik(x):
            attack, defense, home_adv, rho, mu = unpack(x)
            lam = np.exp(mu + attack[home_idx] - defense[away_idx] + home_adv)
            m = np.exp(mu + attack[away_idx] - defense[home_idx])
            lam = np.clip(lam, 1e-6, None)
            m = np.clip(m, 1e-6, None)

            ll = poisson.logpmf(hg, lam) + poisson.logpmf(ag, m)
            tau_vals = np.array([
                _tau(int(x_), int(y_), l_, m_, rho)
                for x_, y_, l_, m_ in zip(hg, ag, lam, m)
            ])
            tau_vals = np.clip(tau_vals, 1e-10, None)
            ll = ll + np.log(tau_vals)
            # penalización leve L2 para estabilidad numérica (identificabilidad)
            penalty = 1e-3 * (np.sum(attack ** 2) + np.sum(defense ** 2))
            return -np.sum(weights * ll) + penalty

        # restricción de identificabilidad: media de ataques = 0
        constraints = [{
            "type": "eq",
            "fun": lambda x: np.sum(x[:n]),
        }]

        res = minimize(neg_log_lik, x0, method="SLSQP", constraints=constraints,
                        options={"maxiter": 300, "ftol": 1e-9})

        attack, defense, home_adv, rho, mu = unpack(res.x)
        self.attack_ = dict(zip(teams, attack))
        self.defense_ = dict(zip(teams, defense))
        self.home_adv_ = float(home_adv)
        self.rho_ = float(rho)
        self.mu_ = float(mu)
        self._fit_result = res
        return self

    def expected_goals(self, home_team: str, away_team: str) -> tuple[float, float]:
        a_h = self.attack_.get(home_team, 0.0)
        d_h = self.defense_.get(home_team, 0.0)
        a_a = self.attack_.get(away_team, 0.0)
        d_a = self.defense_.get(away_team, 0.0)
        lam = math.exp(self.mu_ + a_h - d_a + self.home_adv_)
        mu = math.exp(self.mu_ + a_a - d_h)
        return lam, mu

    def scoreline_matrix(self, home_team: str, away_team: str) -> np.ndarray:
        lam, mu = self.expected_goals(home_team, away_team)
        n = self.max_goals + 1
        home_probs = poisson.pmf(np.arange(n), lam)
        away_probs = poisson.pmf(np.arange(n), mu)
        matrix = np.outer(home_probs, away_probs)
        for x in range(2):
            for y in range(2):
                matrix[x, y] *= _tau(x, y, lam, mu, self.rho_)
        matrix = np.clip(matrix, 0, None)
        matrix /= matrix.sum()
        return matrix

    def markets(self, home_team: str, away_team: str) -> dict:
        matrix = self.scoreline_matrix(home_team, away_team)
        n = matrix.shape[0]

        # marcador más probable
        flat_idx = np.argmax(matrix)
        best_h, best_a = divmod(flat_idx, n)

        home_win = np.tril(matrix, -1).sum()
        draw = np.trace(matrix)
        away_win = np.triu(matrix, 1).sum()

        totals = {}
        total_goals_probs = np.zeros(2 * n - 1)
        for i in range(n):
            for j in range(n):
                total_goals_probs[i + j] += matrix[i, j]
        for line in [0.5, 1.5, 2.5, 3.5, 4.5, 5.5]:
            over = total_goals_probs[math.floor(line) + 1:].sum()
            under = total_goals_probs[: math.floor(line) + 1].sum()
            totals[line] = {"over": float(over), "under": float(under)}

        btts_yes = matrix[1:, 1:].sum()
        btts_no = 1 - btts_yes

        # distribución de marcadores más probables (top 5)
        pairs = [((i, j), matrix[i, j]) for i in range(n) for j in range(n)]
        pairs.sort(key=lambda p: -p[1])
        top_scorelines = [{"score": f"{i}-{j}", "prob": float(p)} for (i, j), p in pairs[:5]]

        return {
            "lambda_home": self.expected_goals(home_team, away_team)[0],
            "lambda_away": self.expected_goals(home_team, away_team)[1],
            "most_likely_score": f"{best_h}-{best_a}",
            "most_likely_score_prob": float(matrix[best_h, best_a]),
            "top_scorelines": top_scorelines,
            "1x2": {"home_win": float(home_win), "draw": float(draw), "away_win": float(away_win)},
            "total_goals": totals,
            "btts": {"yes": float(btts_yes), "no": float(btts_no)},
        }
