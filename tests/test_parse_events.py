from futbol.data.parse_events import parse_match_events


def _match_meta():
    return {
        "match_id": 1,
        "match_date": "2024-01-01",
        "competition": {"competition_name": "Test League"},
        "season": {"season_name": "2023/2024"},
        "home_team": {"home_team_name": "Home FC"},
        "away_team": {"away_team_name": "Away FC"},
        "home_score": 2,
        "away_score": 0,
    }


def _events():
    return [
        {"type": {"name": "Starting XI"}, "team": {"name": "Home FC"}, "tactics": {
            "lineup": [{"player": {"id": 1, "name": "Striker A"}, "position": {"name": "Forward"}}]
        }},
        {"type": {"name": "Starting XI"}, "team": {"name": "Away FC"}, "tactics": {
            "lineup": [{"player": {"id": 2, "name": "Defender B"}, "position": {"name": "Defender"}}]
        }},
        {"type": {"name": "Shot"}, "team": {"name": "Home FC"}, "player": {"id": 1, "name": "Striker A"},
         "shot": {"outcome": {"name": "Goal"}}},
        {"type": {"name": "Shot"}, "team": {"name": "Home FC"}, "player": {"id": 1, "name": "Striker A"},
         "shot": {"outcome": {"name": "Off T"}}},
        {"type": {"name": "Shot"}, "team": {"name": "Away FC"}, "player": {"id": 2, "name": "Defender B"},
         "shot": {"outcome": {"name": "Saved"}}},
        {"type": {"name": "Pass"}, "team": {"name": "Home FC"},
         "pass": {"type": {"name": "Corner"}}},
        {"type": {"name": "Pass"}, "team": {"name": "Home FC"},
         "pass": {"type": {"name": "Corner"}}},
        {"type": {"name": "Foul Committed"}, "team": {"name": "Away FC"}, "player": {"id": 2, "name": "Defender B"},
         "foul_committed": {"card": {"name": "Yellow Card"}}},
        {"type": {"name": "Bad Behaviour"}, "team": {"name": "Home FC"}, "player": {"id": 1, "name": "Striker A"},
         "bad_behaviour": {"card": {"name": "Red Card"}}},
    ]


def test_parse_match_events_team_totals():
    match_row, player_rows = parse_match_events(_match_meta(), _events())

    assert match_row["home_shots"] == 2
    assert match_row["home_shots_on_target"] == 1  # solo el gol cuenta
    assert match_row["away_shots"] == 1
    assert match_row["away_shots_on_target"] == 1  # "Saved" cuenta como a puerta
    assert match_row["home_corners"] == 2
    assert match_row["away_corners"] == 0
    assert match_row["home_red"] == 1
    assert match_row["away_yellow"] == 1
    assert match_row["home_yellow"] == 0


def test_parse_match_events_player_rows():
    _, player_rows = parse_match_events(_match_meta(), _events())
    by_name = {p["player_name"]: p for p in player_rows}

    assert by_name["Striker A"]["shots"] == 2
    assert by_name["Striker A"]["shots_on_target"] == 1
    assert by_name["Striker A"]["team"] == "Home FC"
    assert by_name["Defender B"]["shots"] == 1
    assert by_name["Defender B"]["shots_on_target"] == 1
