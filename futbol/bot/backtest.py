"""Backtest walk-forward del bot sobre un histórico con cuotas reales.

Para cada fecha del calendario: reentrena el modelo solo con partidos
anteriores (cada `refit_every_days`), genera las señales de esa fecha con
la banca del momento, aplica los límites de riesgo y liquida con el
resultado real. Así el P&L que sale es el que habría tenido el bot de
haber operado en vivo esa temporada (con la cuota elegida como precio de
entrada; usar `--book PS` o `Avg` es más realista que `Max`).
"""
from __future__ import annotations

import pandas as pd

from futbol.bot.data import played, row_odds
from futbol.bot.ledger import Ledger
from futbol.bot.markets import model_probabilities
from futbol.bot.model import fit_model, team_match_counts
from futbol.bot.strategy import StrategyConfig, apply_exposure_limit, find_value_bets


def run_backtest(df: pd.DataFrame, cfg: StrategyConfig, book: str = "PS",
                 initial_bankroll: float = 1000.0, warmup_matches: int = 80,
                 min_team_matches: int = 4, refit_every_days: int = 7,
                 progress: bool = False) -> Ledger:
    df = played(df).sort_values("date", kind="stable")
    ledger = Ledger(initial_bankroll)
    # Un modelo por competición (no mezclar ligas), reentrenado cada semana.
    models: dict[str, tuple] = {}

    for date, day in df.groupby(df["date"].dt.normalize()):
        bankroll = ledger.bankroll
        signals, rows = [], []
        for comp, comp_day in day.groupby("competition"):
            history = df[(df["competition"] == comp) & (df["date"] < date)]
            if len(history) < warmup_matches:
                continue
            cached = models.get(comp)
            if cached is None or (date - cached[1]).days >= refit_every_days:
                recent = history[history["date"] >= date - pd.Timedelta(days=540)]
                cached = (fit_model(history, as_of=date), date, team_match_counts(recent))
                models[comp] = cached
                if progress:
                    print(f"  {date.date()} [{comp}] banca {ledger.bankroll:9.2f}  apuestas {len(ledger.bets)}")
            model, _, counts = cached

            for _, row in comp_day.iterrows():
                h, a = row["home_team"], row["away_team"]
                if counts.get(h, 0) < min_team_matches or counts.get(a, 0) < min_team_matches:
                    continue
                odds = row_odds(row, book)
                if not odds:
                    continue
                for s in find_value_bets(str(date.date()), h, a, model_probabilities(model, h, a), odds,
                                         bankroll, cfg, closing_odds=row_odds(row, book, closing=True)):
                    s.competition = comp
                    signals.append(s)
                    rows.append(row)

        signals = apply_exposure_limit(signals, bankroll, cfg)
        by_match = {(r["home_team"], r["away_team"]): r for r in rows}
        for s in signals:
            r = by_match[(s.home_team, s.away_team)]
            ledger.settle(ledger.place(s), r["home_goals"], r["away_goals"])
    return ledger
