"""CLI de pronóstico de un partido con todos los mercados pedidos, filtrado
por confianza real (75%-100%, validada por backtest, ver evaluate.py).

El dataset incluye varias ligas y torneos (ver --list-competitions); cada
uno tiene su propio modelo. Si el nombre de los dos equipos identifica una
única competición en común no hace falta indicarla; si no, usa --competition.

Uso:
    python -m futbol.predict "Equipo local" "Equipo visitante"
    python -m futbol.predict "Equipo local" "Equipo visitante" --competition "La Liga"
    python -m futbol.predict --list-competitions
    python -m futbol.predict --list-teams --competition "Liga F"
"""
from __future__ import annotations

import argparse
import sys

from futbol.config import CONFIDENCE_MAX, CONFIDENCE_MIN
from futbol.models.calibration import GOAL_LINES, TEAM_STAT_LINES
from futbol.models.player_shots import project_team_players
from futbol.models.poisson_markets import line_probabilities
from futbol.pipeline import CompetitionPipeline, build_all_pipelines, find_team_competitions

FutbolPipeline = CompetitionPipeline  # alias usado en las firmas de abajo

SIDE_LABEL = {"over": "más de", "under": "menos de"}
STAT_LABEL = {
    "corners": "corners", "cards": "tarjetas",
    "shots": "tiros totales", "shots_on_target": "tiros a puerta",
}


def _pct(p: float) -> str:
    return f"{p * 100:.1f}%"


def _best_calibrated_pick(pipeline: FutbolPipeline, family: str, probs: dict[str, float]) -> dict | None:
    side, raw = max(probs.items(), key=lambda kv: kv[1])
    calibrated = pipeline.calibrate(raw, family)
    if calibrated >= CONFIDENCE_MIN:
        return {"side": side, "raw_prob": raw, "prob": min(calibrated, CONFIDENCE_MAX)}
    return None


def _best_line_pick(pipeline: FutbolPipeline, family: str, mu: float, lines: list[float]) -> dict | None:
    best = None
    for line in lines:
        probs = line_probabilities(mu, [line])[line]
        side, raw = max(probs.items(), key=lambda kv: kv[1])
        calibrated = pipeline.calibrate(raw, family)
        if best is None or calibrated > best["prob"]:
            best = {"line": line, "side": side, "raw_prob": raw, "prob": min(calibrated, CONFIDENCE_MAX)}
    if best and best["prob"] >= CONFIDENCE_MIN:
        return best
    return None


def predict_match(pipeline: FutbolPipeline, home_team: str, away_team: str) -> dict:
    dc = pipeline.dixon_coles
    if home_team not in dc.teams_ or away_team not in dc.teams_:
        known = ", ".join(sorted(dc.teams_))
        raise ValueError(
            f"Equipo desconocido. Equipos disponibles en el dataset:\n{known}"
        )

    markets = dc.markets(home_team, away_team)

    report: dict = {"home_team": home_team, "away_team": away_team, "markets": {}}

    report["markets"]["marcador_mas_probable"] = {
        "score": markets["most_likely_score"],
        "prob": markets["most_likely_score_prob"],
        "calibrated_prob": pipeline.calibrate(markets["most_likely_score_prob"], "dixon_coles"),
        "top5": markets["top_scorelines"],
        "goles_esperados": {"local": markets["lambda_home"], "visitante": markets["lambda_away"]},
    }

    report["markets"]["1x2"] = _best_calibrated_pick(pipeline, "dixon_coles", markets["1x2"])
    report["markets"]["btts"] = _best_calibrated_pick(pipeline, "dixon_coles", markets["btts"])

    goles_picks = {}
    for line in GOAL_LINES:
        pick = _best_calibrated_pick(pipeline, "dixon_coles", markets["total_goals"][line])
        if pick:
            goles_picks[line] = pick
    report["markets"]["goles_over_under"] = goles_picks

    home_form = pipeline.team_form.loc[home_team]
    away_form = pipeline.team_form.loc[away_team]

    team_stats = {}
    for stat, mdl in pipeline.poisson_models.items():
        mu_home = mdl.predict_mean(True, home_form, away_form)
        mu_away = mdl.predict_mean(False, away_form, home_form)
        pick_home = _best_line_pick(pipeline, "poisson_market", mu_home, TEAM_STAT_LINES[stat])
        pick_away = _best_line_pick(pipeline, "poisson_market", mu_away, TEAM_STAT_LINES[stat])
        team_stats[stat] = {
            "mu_home": mu_home, "mu_away": mu_away,
            "pick_home": pick_home, "pick_away": pick_away,
        }
    report["markets"]["team_stats"] = team_stats

    mu_shots_home = team_stats["shots"]["mu_home"]
    mu_shots_away = team_stats["shots"]["mu_away"]
    mu_sot_home = team_stats["shots_on_target"]["mu_home"]
    mu_sot_away = team_stats["shots_on_target"]["mu_away"]

    home_players = project_team_players(
        pipeline.player_form, home_team, home_form["roll_shots_for"],
        home_form["roll_shots_on_target_for"], mu_shots_home, mu_sot_home,
    )
    away_players = project_team_players(
        pipeline.player_form, away_team, away_form["roll_shots_for"],
        away_form["roll_shots_on_target_for"], mu_shots_away, mu_sot_away,
    )
    for players in (home_players, away_players):
        for pl in players:
            pl["shots_pick"] = _best_line_pick(
                pipeline, "poisson_market", pl["proj_shots"], [0.5, 1.5, 2.5, 3.5])
            pl["sot_pick"] = _best_line_pick(
                pipeline, "poisson_market", pl["proj_shots_on_target"], [0.5, 1.5, 2.5])

    report["markets"]["jugadores"] = {"local": home_players, "visitante": away_players}
    return report


def _print_pick(label: str, pick: dict | None, side_map: dict | None = None) -> None:
    if not pick:
        print(f"  {label}: sin pronóstico de alta confianza (<{_pct(CONFIDENCE_MIN)})")
        return
    side = pick["side"]
    side_txt = side_map.get(side, side) if side_map else side
    line_txt = f" {pick['line']}" if "line" in pick else ""
    print(f"  {label}: {side_txt}{line_txt}  ->  confianza {_pct(pick['prob'])}")


def print_report(report: dict) -> None:
    m = report["markets"]
    print(f"\n=== Pronóstico: {report['home_team']} vs {report['away_team']} ===")
    print(f"(solo se muestran mercados con probabilidad REAL calibrada >= {_pct(CONFIDENCE_MIN)})\n")

    sc = m["marcador_mas_probable"]
    ge = sc["goles_esperados"]
    print(f"Goles esperados: {report['home_team']} {ge['local']:.2f} - {ge['visitante']:.2f} {report['away_team']}")
    print(f"Marcador más probable: {sc['score']} (probabilidad real ~{_pct(sc['calibrated_prob'])} "
          f"-> por debajo del umbral de {_pct(CONFIDENCE_MIN)}; en fútbol NINGÚN marcador exacto alcanza "
          f"ese nivel de confianza. Top 5 más probables:")
    for s in sc["top5"]:
        print(f"    {s['score']}: {_pct(s['prob'])}")

    print("\nResultado (1X2):")
    _print_pick(" ", m["1x2"], {"home_win": f"gana {report['home_team']}",
                                 "draw": "empate", "away_win": f"gana {report['away_team']}"})

    print("\nAmbos equipos marcan (BTTS):")
    _print_pick(" ", m["btts"], {"yes": "sí", "no": "no"})

    print("\nTotal de goles:")
    if m["goles_over_under"]:
        for line, pick in m["goles_over_under"].items():
            _print_pick(f" línea {line}", pick, SIDE_LABEL)
    else:
        print(f"  sin pronóstico de alta confianza (<{_pct(CONFIDENCE_MIN)})")

    print("\nEstadísticas por equipo (corners, tarjetas, tiros, tiros a puerta):")
    for stat, data in m["team_stats"].items():
        label = STAT_LABEL[stat]
        print(f" {label} esperados: {report['home_team']} {data['mu_home']:.2f} | "
              f"{report['away_team']} {data['mu_away']:.2f}")
        _print_pick(f"   {report['home_team']}", data["pick_home"], SIDE_LABEL)
        _print_pick(f"   {report['away_team']}", data["pick_away"], SIDE_LABEL)

    print("\nTop 3 jugadores por tiros esperados:")
    for side_key, team_name in (("local", report["home_team"]), ("visitante", report["away_team"])):
        print(f"  {team_name}:")
        players = m["jugadores"][side_key]
        if not players:
            print("    (sin datos suficientes de plantilla)")
            continue
        for pl in players:
            print(f"    {pl['player_name']}: tiros esperados {pl['proj_shots']:.2f}, "
                  f"a puerta {pl['proj_shots_on_target']:.2f} "
                  f"(muestra: {pl['matches_played']} partidos)")
            _print_pick("      tiros", pl["shots_pick"], SIDE_LABEL)
            _print_pick("      tiros a puerta", pl["sot_pick"], SIDE_LABEL)


def resolve_pipeline(pipelines: dict[str, CompetitionPipeline], home_team: str, away_team: str,
                      competition: str | None) -> CompetitionPipeline:
    if competition:
        if competition not in pipelines:
            known = "\n".join(f"  - {c}" for c in sorted(pipelines))
            raise ValueError(f"Competición desconocida '{competition}'. Disponibles:\n{known}")
        return pipelines[competition]

    home_comps = set(find_team_competitions(pipelines, home_team))
    away_comps = set(find_team_competitions(pipelines, away_team))
    common = home_comps & away_comps

    if not common:
        if not home_comps:
            raise ValueError(f"Equipo local desconocido: '{home_team}'. Prueba --list-teams.")
        if not away_comps:
            raise ValueError(f"Equipo visitante desconocido: '{away_team}'. Prueba --list-teams.")
        raise ValueError(
            f"'{home_team}' y '{away_team}' no comparten competición en el dataset "
            f"({', '.join(sorted(home_comps))} vs {', '.join(sorted(away_comps))}); no pueden enfrentarse."
        )
    if len(common) > 1:
        raise ValueError(
            f"Nombre ambiguo entre varias competiciones ({', '.join(sorted(common))}). "
            f"Usa --competition para elegir."
        )
    return pipelines[next(iter(common))]


def main() -> None:
    parser = argparse.ArgumentParser(description="Pronóstico de un partido de fútbol.")
    parser.add_argument("home_team", nargs="?", help="Equipo local (nombre exacto del dataset)")
    parser.add_argument("away_team", nargs="?", help="Equipo visitante (nombre exacto del dataset)")
    parser.add_argument("--competition", help="Nombre exacto de la competición (ver --list-competitions)")
    parser.add_argument("--list-teams", action="store_true", help="Lista los equipos disponibles y sale")
    parser.add_argument("--list-competitions", action="store_true",
                         help="Lista las competiciones disponibles y sale")
    parser.add_argument("--no-backtest", action="store_true",
                         help="Omite el backtest de calibración (más rápido, probabilidades sin calibrar)")
    args = parser.parse_args()

    list_only = args.list_competitions or args.list_teams
    pipelines = build_all_pipelines(run_backtest=not args.no_backtest and not list_only)

    if args.list_competitions:
        print("Competiciones disponibles:")
        for name, p in sorted(pipelines.items()):
            print(f"  - {name}  ({len(p.dixon_coles.teams_)} equipos, {len(p.matches_df)} partidos)")
        sys.exit(0)

    if args.list_teams:
        comps = [args.competition] if args.competition else sorted(pipelines)
        for comp in comps:
            if comp not in pipelines:
                print(f"Competición desconocida: {comp}", file=sys.stderr)
                sys.exit(1)
            print(f"\n{comp}:")
            for t in sorted(pipelines[comp].dixon_coles.teams_):
                print(f"  - {t}")
        sys.exit(0)

    if not (args.home_team and args.away_team):
        print("Uso: python -m futbol.predict \"Equipo local\" \"Equipo visitante\" "
              "[--competition NOMBRE]\n(--list-competitions / --list-teams para ver las opciones)",
              file=sys.stderr)
        sys.exit(1)

    try:
        pipeline = resolve_pipeline(pipelines, args.home_team, args.away_team, args.competition)
        report = predict_match(pipeline, args.home_team, args.away_team)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)

    print(f"[Competición: {pipeline.competition}]")
    print_report(report)


if __name__ == "__main__":
    main()
