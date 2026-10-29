"""CLI del bot de apuestas de valor (paper trading, sin dinero real).

Uso:
    # 1. Backtest sobre temporadas pasadas (CSV de football-data.co.uk)
    python -m futbol.bot backtest --data E0_2324.csv E0_2425.csv --book PS

    # 2. Crear el libro de apuestas con una banca simulada
    python -m futbol.bot init --ledger mi_bot.json --bankroll 1000

    # 3. Escanear próximos partidos con sus cuotas y registrar las apuestas
    python -m futbol.bot scan --history E0_2425.csv E0_2526.csv \\
        --fixtures fixtures.csv --book B365 --ledger mi_bot.json --place

    # 4. Tras los partidos, liquidar con los resultados y ver el rendimiento
    python -m futbol.bot settle --ledger mi_bot.json --results E0_2526.csv
    python -m futbol.bot report --ledger mi_bot.json
"""
from __future__ import annotations

import argparse
import sys

import pandas as pd

from futbol.bot.backtest import run_backtest
from futbol.bot.data import BOOK_PREFIXES, load_matches, played, row_odds
from futbol.bot.ledger import Ledger
from futbol.bot.markets import MARKET_SELECTIONS, model_probabilities
from futbol.bot.model import fit_model, team_match_counts
from futbol.bot.strategy import StrategyConfig, apply_exposure_limit, find_value_bets


def _pct(x: float | None) -> str:
    return "-" if x is None else f"{x * 100:.1f}%"


def _add_strategy_args(p: argparse.ArgumentParser) -> None:
    d = StrategyConfig()
    p.add_argument("--book", default="PS", choices=list(BOOK_PREFIXES),
                   help="Casa cuyas cuotas se usan como precio (default: PS = Pinnacle)")
    p.add_argument("--min-edge", type=float, default=d.min_edge, help="EV mínimo (0.05 = +5%%)")
    p.add_argument("--min-odds", type=float, default=d.min_odds)
    p.add_argument("--max-odds", type=float, default=d.max_odds)
    p.add_argument("--max-disagreement", type=float, default=d.max_disagreement,
                   help="Diferencia máxima modelo vs probabilidad justa del mercado")
    p.add_argument("--kelly", type=float, default=d.kelly_fraction, help="Fracción de Kelly")
    p.add_argument("--max-stake", type=float, default=d.max_stake_pct, help="Stake máx. por apuesta (%% banca)")
    p.add_argument("--max-exposure", type=float, default=d.max_round_exposure_pct,
                   help="Exposición máx. por jornada (%% banca)")
    p.add_argument("--markets", nargs="+", default=list(d.markets), choices=list(MARKET_SELECTIONS))


def _config(args) -> StrategyConfig:
    return StrategyConfig(
        min_edge=args.min_edge, min_odds=args.min_odds, max_odds=args.max_odds,
        max_disagreement=args.max_disagreement, kelly_fraction=args.kelly,
        max_stake_pct=args.max_stake, max_round_exposure_pct=args.max_exposure,
        markets=tuple(args.markets),
    )


def print_summary(s: dict, initial: float) -> None:
    print(f"\nApuestas liquidadas: {s['bets']}  (abiertas: {s['open']})")
    print(f"Acierto:             {_pct(s['hit_rate'])}  ({s['won']} ganadas)")
    print(f"Cuota media:         {s['avg_odds']:.2f}" if s["avg_odds"] else "Cuota media:         -")
    print(f"Edge medio estimado: {_pct(s['avg_edge'])}")
    print(f"Total apostado:      {s['staked']:.2f}")
    print(f"P&L:                 {s['pnl']:+.2f}")
    print(f"Yield (P&L/apostado): {_pct(s['yield'])}")
    print(f"Banca:               {initial:.2f} -> {s['bankroll']:.2f}  ({_pct(s['roi_bankroll'])})")
    print(f"Máx. drawdown:       {_pct(s['max_drawdown'])}")
    if s["avg_clv"] is not None:
        print(f"CLV medio:           {_pct(s['avg_clv'])}  (le ganó a la cuota de cierre en "
              f"{_pct(s['beat_closing_pct'])} de las apuestas)")


def cmd_backtest(args) -> None:
    df = load_matches(args.data)
    print(f"Partidos: {len(played(df))}  |  {df['date'].min().date()} -> {df['date'].max().date()}  "
          f"|  casa: {args.book}")
    ledger = run_backtest(df, _config(args), book=args.book, initial_bankroll=args.bankroll,
                          warmup_matches=args.warmup, progress=args.verbose)
    print_summary(ledger.summary(), ledger.initial_bankroll)
    by_market = pd.DataFrame(ledger.bets)
    if not by_market.empty:
        g = by_market.groupby("market").agg(apuestas=("pnl", "size"), apostado=("stake", "sum"),
                                             pnl=("pnl", "sum"))
        g["yield"] = (g["pnl"] / g["apostado"]).map(_pct)
        print("\nPor mercado:\n" + g.round(2).to_string())
    if args.out:
        ledger.save(args.out)
        print(f"\nDetalle de cada apuesta guardado en {args.out}")


def cmd_init(args) -> None:
    Ledger(args.bankroll).save(args.ledger)
    print(f"Libro creado: {args.ledger} con banca simulada de {args.bankroll:.2f}")


def cmd_scan(args) -> None:
    history = played(load_matches(args.history))
    fixtures = load_matches([args.fixtures])
    fixtures = fixtures[fixtures["home_goals"].isna()] if "home_goals" in fixtures else fixtures
    ledger = Ledger.load(args.ledger) if args.ledger else Ledger(1000.0)
    cfg = _config(args)
    bankroll = ledger.available

    signals = []
    for comp, comp_fx in fixtures.groupby("competition"):
        comp_hist = history[history["competition"] == comp]
        if len(comp_hist) < 50:
            print(f"[{comp}] historial insuficiente ({len(comp_hist)} partidos), se omite")
            continue
        as_of = comp_fx["date"].min()
        model = fit_model(comp_hist, as_of=as_of)
        counts = team_match_counts(comp_hist[comp_hist["date"] >= as_of - pd.Timedelta(days=540)])
        for _, row in comp_fx.iterrows():
            h, a = row["home_team"], row["away_team"]
            if counts.get(h, 0) < 4 or counts.get(a, 0) < 4:
                print(f"[{comp}] {h} vs {a}: equipo sin historial suficiente, se omite")
                continue
            for s in find_value_bets(str(row["date"].date()), h, a, model_probabilities(model, h, a),
                                     row_odds(row, args.book), bankroll, cfg):
                s.competition = comp
                signals.append(s)

    signals = apply_exposure_limit(signals, bankroll, cfg)
    if not signals:
        print("Sin apuestas de valor en estos partidos con la estrategia actual.")
        return
    print(f"\nApuestas de valor (banca disponible {bankroll:.2f}):")
    for s in signals:
        fair = f"mercado {_pct(s.fair_prob)}" if s.fair_prob is not None else ""
        print(f"  {s.date} [{s.competition}] {s.home_team} vs {s.away_team}: {s.market} {s.selection} "
              f"@ {s.odds:.2f} | modelo {_pct(s.model_prob)} {fair} | edge {_pct(s.edge)} | stake {s.stake:.2f}")
    if args.place:
        for s in signals:
            ledger.place(s)
        ledger.save(args.ledger)
        print(f"\n{len(signals)} apuestas registradas (paper) en {args.ledger}")


def cmd_settle(args) -> None:
    ledger = Ledger.load(args.ledger)
    results = played(load_matches(args.results))
    results["day"] = results["date"].dt.strftime("%Y-%m-%d")
    index = {(r.day, r.home_team, r.away_team): r for r in results.itertuples()}
    n = 0
    for bet in ledger.open_bets():
        r = index.get((bet["date"], bet["home_team"], bet["away_team"]))
        if r is None:
            continue
        ledger.settle(bet, r.home_goals, r.away_goals)
        print(f"  {bet['home_team']} vs {bet['away_team']} {bet['score']}: {bet['market']} "
              f"{bet['selection']} -> {bet['status']} ({bet['pnl']:+.2f})")
        n += 1
    ledger.save(args.ledger)
    print(f"{n} apuestas liquidadas. Banca: {ledger.bankroll:.2f}")


def cmd_report(args) -> None:
    ledger = Ledger.load(args.ledger)
    print_summary(ledger.summary(), ledger.initial_bankroll)
    for b in ledger.open_bets():
        print(f"  abierta: {b['date']} {b['home_team']} vs {b['away_team']} {b['market']} "
              f"{b['selection']} @ {b['odds']:.2f} stake {b['stake']:.2f}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m futbol.bot",
                                     description="Bot de apuestas de valor (paper trading).")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("backtest", help="Simula el bot sobre temporadas pasadas con cuotas reales")
    p.add_argument("--data", nargs="+", required=True, help="CSV(s) de football-data.co.uk")
    p.add_argument("--bankroll", type=float, default=1000.0)
    p.add_argument("--warmup", type=int, default=80, help="Partidos de calentamiento por competición")
    p.add_argument("--out", help="Guarda el detalle de las apuestas en JSON")
    p.add_argument("-v", "--verbose", action="store_true")
    _add_strategy_args(p)
    p.set_defaults(func=cmd_backtest)

    p = sub.add_parser("init", help="Crea un libro de apuestas con banca simulada")
    p.add_argument("--ledger", required=True)
    p.add_argument("--bankroll", type=float, default=1000.0)
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("scan", help="Busca apuestas de valor en próximos partidos")
    p.add_argument("--history", nargs="+", required=True, help="CSV(s) con resultados pasados")
    p.add_argument("--fixtures", required=True, help="CSV de próximos partidos con cuotas")
    p.add_argument("--ledger", help="Libro de apuestas (para la banca y para --place)")
    p.add_argument("--place", action="store_true", help="Registra las apuestas en el libro")
    _add_strategy_args(p)
    p.set_defaults(func=cmd_scan)

    p = sub.add_parser("settle", help="Liquida apuestas abiertas con resultados reales")
    p.add_argument("--ledger", required=True)
    p.add_argument("--results", nargs="+", required=True)
    p.set_defaults(func=cmd_settle)

    p = sub.add_parser("report", help="Rendimiento del libro de apuestas")
    p.add_argument("--ledger", required=True)
    p.set_defaults(func=cmd_report)

    args = parser.parse_args(argv)
    if args.cmd == "scan" and args.place and not args.ledger:
        parser.error("--place requiere --ledger")
    args.func(args)


if __name__ == "__main__":
    sys.exit(main())
