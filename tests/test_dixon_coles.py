import numpy as np
import pandas as pd

from futbol.models.dixon_coles import DixonColes


def _synthetic_matches(n_rounds: int = 6, seed: int = 0) -> pd.DataFrame:
    """Liga sintética de 4 equipos donde 'Strong FC' domina claramente."""
    rng = np.random.default_rng(seed)
    teams = ["Strong FC", "Mid A", "Mid B", "Weak FC"]
    strength = {"Strong FC": 2.6, "Mid A": 1.3, "Mid B": 1.2, "Weak FC": 0.5}
    rows = []
    match_id = 0
    start = pd.Timestamp("2024-01-01")
    for r in range(n_rounds):
        for i, home in enumerate(teams):
            for away in teams:
                if home == away:
                    continue
                lam = max(strength[home] - strength[away] * 0.3 + 0.3, 0.1)
                mu = max(strength[away] - strength[home] * 0.3, 0.1)
                hg = rng.poisson(lam)
                ag = rng.poisson(mu)
                rows.append({
                    "match_id": match_id, "date": start + pd.Timedelta(days=match_id),
                    "home_team": home, "away_team": away,
                    "home_goals": hg, "away_goals": ag,
                })
                match_id += 1
    return pd.DataFrame(rows)


def test_scoreline_matrix_sums_to_one():
    matches = _synthetic_matches()
    dc = DixonColes(max_goals=10).fit(matches)
    matrix = dc.scoreline_matrix("Strong FC", "Weak FC")
    assert abs(matrix.sum() - 1.0) < 1e-6


def test_stronger_team_has_higher_expected_goals():
    matches = _synthetic_matches()
    dc = DixonColes().fit(matches)
    lam, mu = dc.expected_goals("Strong FC", "Weak FC")
    assert lam > mu

    lam2, mu2 = dc.expected_goals("Weak FC", "Strong FC")
    assert mu2 > lam2


def test_markets_probabilities_are_consistent():
    matches = _synthetic_matches()
    dc = DixonColes().fit(matches)
    markets = dc.markets("Strong FC", "Weak FC")

    total_1x2 = sum(markets["1x2"].values())
    assert abs(total_1x2 - 1.0) < 1e-6
    assert markets["1x2"]["home_win"] > markets["1x2"]["away_win"]

    for line, probs in markets["total_goals"].items():
        assert abs(probs["over"] + probs["under"] - 1.0) < 1e-6

    assert abs(markets["btts"]["yes"] + markets["btts"]["no"] - 1.0) < 1e-6
