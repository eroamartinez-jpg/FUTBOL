"""Orquesta la descarga y el parseo de todas las competiciones configuradas.

Uso:
    python -m futbol.data.build_dataset
"""
from __future__ import annotations

import pandas as pd

from futbol.config import COMPETITIONS, PROCESSED_DIR
from futbol.data.parse_events import build_tables
from futbol.data.statsbomb_client import download_events_bulk, get_matches


def main() -> None:
    all_matches = []
    all_players = []

    for competition_id, season_id, label in COMPETITIONS:
        print(f"== {label} ==")
        matches_meta = get_matches(competition_id, season_id)
        match_ids = [m["match_id"] for m in matches_meta]
        events_by_match = download_events_bulk(match_ids)
        matches_df, players_df = build_tables(matches_meta, events_by_match)
        all_matches.append(matches_df)
        all_players.append(players_df)
        print(f"  partidos: {len(matches_df)}, filas jugador: {len(players_df)}")

    matches_df = pd.concat(all_matches, ignore_index=True).sort_values("date").reset_index(drop=True)
    players_df = pd.concat(all_players, ignore_index=True).sort_values("date").reset_index(drop=True)

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    matches_path = PROCESSED_DIR / "matches.csv"
    players_path = PROCESSED_DIR / "player_match.csv"
    matches_df.to_csv(matches_path, index=False)
    players_df.to_csv(players_path, index=False)
    print(f"Guardado {matches_path} ({len(matches_df)} filas)")
    print(f"Guardado {players_path} ({len(players_df)} filas)")


if __name__ == "__main__":
    main()
