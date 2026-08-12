import pandas as pd
import pytest

from futbol.pipeline import _build_one, find_team_competitions
from futbol.predict import resolve_pipeline


def _matches_for(competition: str, teams: list[str], match_id_start: int) -> pd.DataFrame:
    rows = []
    match_id = match_id_start
    start = pd.Timestamp("2024-01-01")
    for round_ in range(8):
        home, away = (teams[0], teams[1]) if round_ % 2 == 0 else (teams[1], teams[0])
        rows.append({
            "match_id": match_id, "date": start + pd.Timedelta(days=match_id),
            "competition": competition,
            "home_team": home, "away_team": away,
            "home_goals": 2, "away_goals": 1,
            "home_shots": 10, "away_shots": 8,
            "home_shots_on_target": 5, "away_shots_on_target": 3,
            "home_corners": 6, "away_corners": 4,
            "home_yellow": 1, "away_yellow": 2,
            "home_red": 0, "away_red": 0,
        })
        match_id += 1
    return pd.DataFrame(rows)


_EMPTY_PLAYERS = pd.DataFrame(columns=[
    "match_id", "date", "player_id", "player_name", "team", "opponent",
    "is_home", "shots", "shots_on_target",
])


@pytest.fixture
def two_competition_pipelines():
    liga_a = _matches_for("Liga A", ["Alpha", "Beta"], match_id_start=0)
    liga_b = _matches_for("Liga B", ["Gamma", "Delta"], match_id_start=100)

    pipelines = {
        "Liga A": _build_one("Liga A", liga_a, _EMPTY_PLAYERS, run_backtest=False),
        "Liga B": _build_one("Liga B", liga_b, _EMPTY_PLAYERS, run_backtest=False),
    }
    return pipelines


def test_find_team_competitions(two_competition_pipelines):
    assert find_team_competitions(two_competition_pipelines, "Alpha") == ["Liga A"]
    assert find_team_competitions(two_competition_pipelines, "Gamma") == ["Liga B"]
    assert find_team_competitions(two_competition_pipelines, "No Existe") == []


def test_resolve_pipeline_same_competition(two_competition_pipelines):
    pipeline = resolve_pipeline(two_competition_pipelines, "Alpha", "Beta", competition=None)
    assert pipeline.competition == "Liga A"


def test_resolve_pipeline_cross_competition_raises(two_competition_pipelines):
    with pytest.raises(ValueError, match="no pueden enfrentarse"):
        resolve_pipeline(two_competition_pipelines, "Alpha", "Gamma", competition=None)


def test_resolve_pipeline_unknown_team_raises(two_competition_pipelines):
    with pytest.raises(ValueError, match="desconocido"):
        resolve_pipeline(two_competition_pipelines, "Fantasma", "Beta", competition=None)


def test_resolve_pipeline_explicit_competition_overrides(two_competition_pipelines):
    pipeline = resolve_pipeline(two_competition_pipelines, "Alpha", "Beta", competition="Liga A")
    assert pipeline.competition == "Liga A"

    with pytest.raises(ValueError, match="desconocida"):
        resolve_pipeline(two_competition_pipelines, "Alpha", "Beta", competition="Liga Z")
