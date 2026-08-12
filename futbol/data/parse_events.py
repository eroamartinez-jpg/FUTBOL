"""Convierte eventos StatsBomb en tablas planas por partido y por jugador.

Definiciones adoptadas (documentadas en el README):
- Tiros totales: todos los eventos "Shot" (incluye penaltis, excluye ninguno).
- Tiros a puerta: eventos "Shot" cuyo outcome es Goal, Saved o Saved To Post.
- Corners: eventos "Pass" con pass.type == "Corner".
- Tarjetas amarillas/rojas: eventos "Bad Behaviour" o "Foul Committed" con
  campo card. "Second Yellow" cuenta como roja.
"""
from __future__ import annotations

from collections import defaultdict

import pandas as pd

_ON_TARGET_OUTCOMES = {"Goal", "Saved", "Saved To Post"}
_RED_CARD_NAMES = {"Red Card", "Second Yellow"}


def _card_kind(card_name: str) -> str | None:
    if card_name == "Yellow Card":
        return "yellow"
    if card_name in _RED_CARD_NAMES:
        return "red"
    return None


def parse_match_events(match_meta: dict, events: list[dict]) -> tuple[dict, list[dict]]:
    """Devuelve (fila_partido, filas_jugador) para un partido StatsBomb."""
    match_id = match_meta["match_id"]
    home_name = match_meta["home_team"]["home_team_name"]
    away_name = match_meta["away_team"]["away_team_name"]

    team_stats: dict[str, dict[str, int]] = defaultdict(
        lambda: {"shots": 0, "shots_on_target": 0, "corners": 0, "yellow": 0, "red": 0}
    )
    # jugador -> equipo, tiros, tiros a puerta
    player_stats: dict[int, dict] = {}
    player_team: dict[int, str] = {}

    def _ensure_player(player_id: int, player_name: str, team_name: str) -> None:
        player_team[player_id] = team_name
        if player_id not in player_stats:
            player_stats[player_id] = {
                "player_id": player_id,
                "player_name": player_name,
                "team": team_name,
                "shots": 0,
                "shots_on_target": 0,
            }

    for ev in events:
        etype = ev["type"]["name"]
        team_name = ev.get("team", {}).get("name")

        if etype == "Starting XI":
            for entry in ev.get("tactics", {}).get("lineup", []):
                p = entry["player"]
                _ensure_player(p["id"], p["name"], team_name)

        elif etype == "Substitution":
            repl = ev.get("substitution", {}).get("replacement")
            if repl:
                _ensure_player(repl["id"], repl["name"], team_name)

        elif etype == "Shot":
            player = ev.get("player")
            outcome = ev.get("shot", {}).get("outcome", {}).get("name")
            team_stats[team_name]["shots"] += 1
            on_target = outcome in _ON_TARGET_OUTCOMES
            if on_target:
                team_stats[team_name]["shots_on_target"] += 1
            if player:
                _ensure_player(player["id"], player["name"], team_name)
                player_stats[player["id"]]["shots"] += 1
                if on_target:
                    player_stats[player["id"]]["shots_on_target"] += 1

        elif etype == "Pass":
            if ev.get("pass", {}).get("type", {}).get("name") == "Corner":
                team_stats[team_name]["corners"] += 1

        elif etype in ("Bad Behaviour", "Foul Committed"):
            card = ev.get(
                "bad_behaviour" if etype == "Bad Behaviour" else "foul_committed", {}
            ).get("card")
            if card:
                kind = _card_kind(card["name"])
                if kind:
                    team_stats[team_name][kind] += 1

    home = team_stats[home_name]
    away = team_stats[away_name]

    match_row = {
        "match_id": match_id,
        "date": match_meta["match_date"],
        "competition": match_meta["competition"]["competition_name"],
        "season": match_meta["season"]["season_name"],
        "home_team": home_name,
        "away_team": away_name,
        "home_goals": match_meta["home_score"],
        "away_goals": match_meta["away_score"],
        "home_shots": home["shots"],
        "away_shots": away["shots"],
        "home_shots_on_target": home["shots_on_target"],
        "away_shots_on_target": away["shots_on_target"],
        "home_corners": home["corners"],
        "away_corners": away["corners"],
        "home_yellow": home["yellow"],
        "away_yellow": away["yellow"],
        "home_red": home["red"],
        "away_red": away["red"],
    }

    player_rows = []
    for pid, stats in player_stats.items():
        team = stats["team"]
        is_home = team == home_name
        player_rows.append(
            {
                "match_id": match_id,
                "date": match_meta["match_date"],
                "player_id": pid,
                "player_name": stats["player_name"],
                "team": team,
                "opponent": away_name if is_home else home_name,
                "is_home": is_home,
                "shots": stats["shots"],
                "shots_on_target": stats["shots_on_target"],
            }
        )

    return match_row, player_rows


def build_tables(matches_meta: list[dict], events_by_match: dict[int, list[dict]]) -> tuple[pd.DataFrame, pd.DataFrame]:
    match_rows = []
    player_rows = []
    for meta in matches_meta:
        mid = meta["match_id"]
        events = events_by_match.get(mid)
        if not events:
            continue
        match_row, p_rows = parse_match_events(meta, events)
        match_rows.append(match_row)
        player_rows.extend(p_rows)

    matches_df = pd.DataFrame(match_rows).sort_values("date").reset_index(drop=True)
    players_df = pd.DataFrame(player_rows)
    if not players_df.empty:
        players_df = players_df.sort_values("date").reset_index(drop=True)
    return matches_df, players_df
