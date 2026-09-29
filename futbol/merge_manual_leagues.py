"""Integra las ligas nuevas (futbol/data/manual_leagues_2026_data.py) al
banco web/live_leagues.json.

No hay datos reales de tarjetas/tiros/tiros a puerta/corners para estas
ligas (los agentes de investigación solo relevaron la tabla de posiciones
real: PJ/PG/PE/PP/GF/GC). Esos 4 campos se ESTIMAN a partir de una base
real (el promedio observado en las 1595 equipos ya existentes en el banco:
cards=1.95, shots=13.1, sot=5.35, corners=5.4) escalada por el nivel de
ataque del equipo relativo a su liga (su GF/partido vs. el promedio de esa
liga, con una raíz cuadrada para amortiguar — un equipo que anota el doble
del promedio de su liga no necesariamente remata el doble, remata ~40% más)
y clampeada a un rango razonable. Se documenta así, explícitamente, en vez
de simular una precisión que no existe.

Jugadores: sin datos reales tampoco, se usan 3 placeholders genéricos por
equipo ("Jugador ofensivo N"), igual convención que ya usa el banco
original para sus equipos menos conocidos, con tiros proporcionales a la
estimación de tiros del equipo.

Uso:
    python -m futbol.merge_manual_leagues
"""
from __future__ import annotations

import json
import math

from futbol.config import ROOT_DIR
from futbol.data.manual_leagues_2026_data import NEW_LEAGUES, UEFA_NATIONS_LEAGUE

LIVE_PATH = ROOT_DIR / "web" / "live_leagues.json"

BASE_CARDS = 1.95
BASE_SHOTS = 13.1
BASE_SOT = 5.35
BASE_CORNERS = 5.4

PLAYER_SHOT_SHARES = [0.20, 0.15, 0.12]  # top-3 como fracción de los tiros del equipo
SOT_RATIO = BASE_SOT / BASE_SHOTS


def estimate_stats(gf_per_game: float, league_avg_per_team: float) -> dict:
    ratio = math.sqrt(max(gf_per_game, 0.05) / max(league_avg_per_team, 0.05))
    ratio = max(0.6, min(ratio, 1.8))  # amortiguado, sin extremos irreales
    shots = round(BASE_SHOTS * ratio, 1)
    sot = round(shots * SOT_RATIO, 1)
    corners = round(BASE_CORNERS * ratio, 1)
    # Tarjetas: sin relación clara con el nivel de ataque, se deja en la
    # base observada para todos los equipos (no hay señal real para variarla).
    cards = BASE_CARDS
    return {"cards": cards, "shots": shots, "sot": sot, "corners": corners}


def make_players(team_shots: float) -> list[dict]:
    return [
        {"name": f"Jugador ofensivo {i+1}", "shots": round(team_shots * share, 1),
         "sot": round(team_shots * share * SOT_RATIO, 1)}
        for i, share in enumerate(PLAYER_SHOT_SHARES)
    ]


def build_league_entry(name: str, group: str, teams: list[tuple]) -> tuple[dict, dict]:
    total_gf = sum(t[5] for t in teams)
    total_pj = sum(t[1] for t in teams)
    league_avg_per_team = total_gf / total_pj if total_pj else 1.35

    league_meta = {
        "name": name, "group": group,
        "prior_avg_goals": round(league_avg_per_team * 2, 2),
        "league_avg_per_team": league_avg_per_team,
        "n_teams_seen": len(teams),
        "n_matches_seen_approx": total_pj,
    }

    team_entries = {}
    for team_name, pj, pg, pe, pp, gf, gc in teams:
        gf_per_game = gf / pj if pj else league_avg_per_team
        stats = estimate_stats(gf_per_game, league_avg_per_team)
        team_entries[team_name] = {
            "league": name, "pj": pj, "pg": pg, "pe": pe, "pp": pp, "gf": gf, "gc": gc,
            **stats,
            "players": make_players(stats["shots"]),
        }
    return league_meta, team_entries


def main() -> None:
    data = json.loads(LIVE_PATH.read_text(encoding="utf-8"))
    existing_names = {l["name"] for l in data["leagues"]}

    added_leagues, added_teams = 0, 0
    for name, info in NEW_LEAGUES.items():
        if name in existing_names:
            print(f"ya existe, se omite: {name}")
            continue
        league_meta, team_entries = build_league_entry(name, info["group"], info["teams"])
        data["leagues"].append(league_meta)
        data["teams"].update(team_entries)
        added_leagues += 1
        added_teams += len(team_entries)
        print(f"+ {name}: {len(team_entries)} equipos (avg/equipo={league_meta['league_avg_per_team']:.2f})")

    # UEFA Nations League: selecciones, no clubes; mismo tratamiento
    nl_name = "UEFA Nations League 2026-27 (selecciones)"
    if nl_name not in existing_names:
        league_meta, team_entries = build_league_entry(nl_name, UEFA_NATIONS_LEAGUE["group"], UEFA_NATIONS_LEAGUE["teams"])
        data["leagues"].append(league_meta)
        data["teams"].update(team_entries)
        added_leagues += 1
        added_teams += len(team_entries)
        print(f"+ {nl_name}: {len(team_entries)} selecciones (avg/equipo={league_meta['league_avg_per_team']:.2f})")

    LIVE_PATH.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    print(f"\nTotal agregado: {added_leagues} ligas/competiciones, {added_teams} equipos/selecciones.")
    print(f"Total banco ahora: {len(data['leagues'])} ligas, {len(data['teams'])} equipos.")


if __name__ == "__main__":
    main()
