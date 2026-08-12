import pandas as pd

from futbol.features.team_form import add_rolling_features, to_long_format


def _matches_df() -> pd.DataFrame:
    rows = []
    teams = ["A", "B", "C", "D"]
    match_id = 0
    start = pd.Timestamp("2024-01-01")
    for round_ in range(3):
        for i in range(0, len(teams), 2):
            rows.append({
                "match_id": match_id, "date": start + pd.Timedelta(days=match_id),
                "home_team": teams[i], "away_team": teams[i + 1],
                "home_goals": 2, "away_goals": 1,
                "home_shots": 10, "away_shots": 8,
                "home_shots_on_target": 5, "away_shots_on_target": 3,
                "home_corners": 6, "away_corners": 4,
                "home_yellow": 1, "away_yellow": 2,
                "home_red": 0, "away_red": 0,
            })
            match_id += 1
    return pd.DataFrame(rows)


def test_to_long_format_has_two_rows_per_match():
    matches = _matches_df()
    long_df = to_long_format(matches)
    assert len(long_df) == 2 * len(matches)
    assert set(long_df["team"]) == {"A", "B", "C", "D"}


def test_rolling_features_have_no_leakage_on_first_appearance():
    matches = _matches_df()
    long_df = to_long_format(matches)
    long_df = add_rolling_features(long_df, window=5, min_periods=1)

    first_rows = long_df.sort_values("date").groupby("team").head(1)
    assert first_rows["roll_goals_for"].isna().all()


def test_rolling_features_use_only_past_matches():
    matches = _matches_df()
    long_df = to_long_format(matches)
    long_df = add_rolling_features(long_df, window=5, min_periods=1)

    team_a = long_df[long_df["team"] == "A"].sort_values("date").reset_index(drop=True)
    # A siempre marca 2 goles como local en los datos sintéticos; la media
    # móvil de su 2º partido debe ser exactamente el resultado del 1º (2.0).
    assert team_a.loc[1, "roll_goals_for"] == 2.0
