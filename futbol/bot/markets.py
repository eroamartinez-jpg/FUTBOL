"""Mercados soportados por el bot: probabilidades del modelo y liquidación.

Claves de mercado / selección:
  - "1x2":   "home", "draw", "away"
  - "ou2.5": "over", "under"   (también "ou1.5" y "ou3.5")
  - "btts":  "yes", "no"
"""
from __future__ import annotations

from futbol.models.dixon_coles import DixonColes

OU_LINES = (1.5, 2.5, 3.5)
MARKET_SELECTIONS = {
    "1x2": ("home", "draw", "away"),
    "btts": ("yes", "no"),
    **{f"ou{line}": ("over", "under") for line in OU_LINES},
}


def model_probabilities(dc: DixonColes, home_team: str, away_team: str) -> dict[str, dict[str, float]]:
    m = dc.markets(home_team, away_team)
    out = {
        "1x2": {"home": m["1x2"]["home_win"], "draw": m["1x2"]["draw"], "away": m["1x2"]["away_win"]},
        "btts": dict(m["btts"]),
    }
    for line in OU_LINES:
        out[f"ou{line}"] = dict(m["total_goals"][line])
    return out


def bet_won(market: str, selection: str, home_goals: int, away_goals: int) -> bool:
    if market == "1x2":
        result = "home" if home_goals > away_goals else "away" if away_goals > home_goals else "draw"
        return selection == result
    if market == "btts":
        both = home_goals > 0 and away_goals > 0
        return both == (selection == "yes")
    if market.startswith("ou"):
        over = home_goals + away_goals > float(market[2:])
        return over == (selection == "over")
    raise ValueError(f"mercado desconocido: {market}")
