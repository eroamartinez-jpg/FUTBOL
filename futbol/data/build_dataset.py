"""Orquesta la descarga y el parseo de todas las competiciones configuradas.

Los eventos crudos de StatsBomb pesan ~3MB por partido; con muchas
competiciones eso son varios GB. Por defecto, tras parsear cada competición
se borran sus JSON de eventos (ya están resumidos en matches.csv /
player_match.csv) para no agotar el disco. Usa --keep-raw-events si quieres
conservarlos (por ejemplo para depurar el parser sin volver a descargar).

Uso:
    python -m futbol.data.build_dataset
    python -m futbol.data.build_dataset --keep-raw-events
"""
from __future__ import annotations

import argparse

import pandas as pd

from futbol.config import COMPETITIONS, PROCESSED_DIR, RAW_DIR
from futbol.data.parse_events import build_tables
from futbol.data.statsbomb_client import download_events_bulk, get_matches


def main() -> None:
    parser = argparse.ArgumentParser(description="Descarga y procesa el dataset de StatsBomb Open Data.")
    parser.add_argument("--keep-raw-events", action="store_true",
                         help="No borra los JSON de eventos descargados tras procesarlos")
    args = parser.parse_args()

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

        if not args.keep_raw_events:
            events_dir = RAW_DIR / "events"
            for mid in match_ids:
                path = events_dir / f"{mid}.json"
                path.unlink(missing_ok=True)

    matches_df = pd.concat(all_matches, ignore_index=True).sort_values("date").reset_index(drop=True)
    players_df = pd.concat(all_players, ignore_index=True).sort_values("date").reset_index(drop=True)

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    matches_path = PROCESSED_DIR / "matches.csv"
    players_path = PROCESSED_DIR / "player_match.csv"
    matches_df.to_csv(matches_path, index=False)
    players_df.to_csv(players_path, index=False)
    print(f"\nGuardado {matches_path} ({len(matches_df)} filas)")
    print(f"Guardado {players_path} ({len(players_df)} filas)")
    print(f"\nCompeticiones: {matches_df['competition'].nunique()}")
    print(matches_df.groupby("competition")["match_id"].count().to_string())


if __name__ == "__main__":
    main()
