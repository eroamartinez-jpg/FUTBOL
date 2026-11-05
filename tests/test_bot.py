import numpy as np
import pandas as pd
import pytest

from futbol.bot.backtest import run_backtest
from futbol.bot.data import row_odds
from futbol.bot.ledger import Ledger
from futbol.bot.markets import bet_won
from futbol.bot.odds import fair_probabilities, overround
from futbol.bot.strategy import (BetSignal, StrategyConfig, apply_exposure_limit, expected_value,
                                 find_value_bets, kelly_fraction)


def test_overround_and_fair_probabilities():
    odds = {"home": 2.0, "draw": 3.4, "away": 3.8}
    assert overround(odds) == pytest.approx(0.5 + 1 / 3.4 + 1 / 3.8 - 1)
    fair = fair_probabilities(odds)
    assert sum(fair.values()) == pytest.approx(1.0)
    assert fair["home"] > fair["draw"] > fair["away"]


def test_kelly_and_ev():
    assert expected_value(0.55, 2.0) == pytest.approx(0.10)
    assert kelly_fraction(0.55, 2.0) == pytest.approx(0.10)
    assert kelly_fraction(0.40, 2.0) == 0.0


def test_bet_settlement():
    assert bet_won("1x2", "home", 2, 1)
    assert bet_won("1x2", "draw", 1, 1)
    assert not bet_won("1x2", "away", 0, 0)
    assert bet_won("ou2.5", "over", 2, 1)
    assert bet_won("ou2.5", "under", 1, 1)
    assert bet_won("btts", "yes", 1, 3)
    assert bet_won("btts", "no", 0, 3)


def test_find_value_bets_filters_and_sizes():
    cfg = StrategyConfig(min_edge=0.05, max_disagreement=0.2, kelly_fraction=0.25, max_stake_pct=0.03)
    probs = {"1x2": {"home": 0.55, "draw": 0.25, "away": 0.20}}
    odds = {"1x2": {"home": 2.10, "draw": 3.40, "away": 4.00}}
    bets = find_value_bets("2025-01-01", "A", "B", probs, odds, 1000.0, cfg)
    assert len(bets) == 1 and bets[0].selection == "home"
    # Kelly completo = (0.55*2.1-1)/1.1 = 0.1409 -> 1/4 = 3.5%, tope 3%
    assert bets[0].stake == pytest.approx(30.0)


def test_disagreement_with_market_blocks_bet():
    cfg = StrategyConfig(max_disagreement=0.10)
    probs = {"1x2": {"home": 0.70, "draw": 0.20, "away": 0.10}}
    odds = {"1x2": {"home": 3.0, "draw": 3.2, "away": 2.4}}  # mercado ve al local en ~32%
    assert find_value_bets("d", "A", "B", probs, odds, 1000.0, cfg) == []


def test_exposure_limit_scales_stakes():
    cfg = StrategyConfig(max_round_exposure_pct=0.05)
    sigs = [BetSignal("d", f"H{i}", f"A{i}", "1x2", "home", 2.0, 0.6, 0.5, 0.2, 0.2, stake=30.0)
            for i in range(4)]
    out = apply_exposure_limit(sigs, 1000.0, cfg)
    assert sum(s.stake for s in out) == pytest.approx(50.0)


def test_ledger_pnl_and_drawdown(tmp_path):
    ledger = Ledger(100.0)
    b1 = ledger.place(BetSignal("d", "A", "B", "1x2", "home", 2.5, 0.5, 0.4, 0.25, 0.1, stake=10.0,
                                closing_odds=2.2))
    b2 = ledger.place(BetSignal("d", "C", "D", "ou2.5", "over", 2.0, 0.6, 0.5, 0.2, 0.1, stake=10.0))
    assert ledger.available == pytest.approx(80.0)
    ledger.settle(b1, 0, 1)
    ledger.settle(b2, 2, 2)
    s = ledger.summary()
    assert s["pnl"] == pytest.approx(0.0)
    assert s["max_drawdown"] == pytest.approx(0.10)
    assert s["avg_clv"] == pytest.approx(2.5 / 2.2 - 1)
    path = tmp_path / "l.json"
    ledger.save(path)
    assert Ledger.load(path).summary() == s


def test_row_odds_football_data_columns():
    row = pd.Series({"PSH": 2.1, "PSD": 3.3, "PSA": 3.6, "P>2.5": 1.9, "P<2.5": 1.95,
                     "PSCH": 2.0, "PSCD": 3.4, "PSCA": 3.8})
    assert row_odds(row, "PS") == {"1x2": {"home": 2.1, "draw": 3.3, "away": 3.6},
                                   "ou2.5": {"over": 1.9, "under": 1.95}}
    assert row_odds(row, "PS", closing=True) == {"1x2": {"home": 2.0, "draw": 3.4, "away": 3.8}}
    generic = pd.Series({"odds_home": 1.9, "odds_draw": 3.5, "odds_away": 4.0, "odds_over25": 1.8,
                         "odds_under25": float("nan")})
    assert row_odds(generic, "B365") == {"1x2": {"home": 1.9, "draw": 3.5, "away": 4.0},
                                         "ou2.5": {"over": 1.8}}


def _synthetic_season(seed=0, n_teams=12):
    """Liga sintética con fuerzas conocidas y cuotas ruidosas (con margen)."""
    rng = np.random.default_rng(seed)
    teams = [f"T{i}" for i in range(n_teams)]
    att = dict(zip(teams, rng.normal(0, 0.3, n_teams)))
    dfn = dict(zip(teams, rng.normal(0, 0.3, n_teams)))
    rows, day = [], pd.Timestamp("2024-08-01")
    fixtures = [(h, a) for h in teams for a in teams if h != a]
    rng.shuffle(fixtures)
    for i, (h, a) in enumerate(fixtures):
        lh, la = np.exp(0.25 + att[h] - dfn[a] + 0.25), np.exp(0.25 + att[a] - dfn[h])
        mh = np.random.default_rng(i).poisson(lh, 20000)
        ma = np.random.default_rng(i + 1).poisson(la, 20000)
        ph, pd_, pa = (mh > ma).mean(), (mh == ma).mean(), (mh < ma).mean()
        noisy = np.array([ph, pd_, pa]) * np.exp(rng.normal(0, 0.12, 3))
        noisy = noisy / noisy.sum() * 1.05
        rows.append({"date": day + pd.Timedelta(days=i // 6 * 7), "competition": "SYN",
                     "home_team": h, "away_team": a,
                     "home_goals": rng.poisson(lh), "away_goals": rng.poisson(la),
                     "PSH": 1 / noisy[0], "PSD": 1 / noisy[1], "PSA": 1 / noisy[2]})
    return pd.DataFrame(rows)


def test_backtest_runs_end_to_end_without_lookahead():
    df = _synthetic_season()
    cfg = StrategyConfig(markets=("1x2",), max_disagreement=0.25)
    ledger = run_backtest(df, cfg, book="PS", initial_bankroll=1000.0, warmup_matches=40,
                          refit_every_days=21)
    s = ledger.summary()
    assert s["bets"] > 0 and s["open"] == 0
    first_bet = min(pd.Timestamp(b["date"]) for b in ledger.bets)
    assert (df["date"] < first_bet).sum() >= 40
    assert s["bankroll"] == pytest.approx(1000.0 + s["pnl"])


def test_rushbet_team_mapping_and_kickoff():
    from datetime import date
    from futbol.bot.rushbet import map_team, parse_kickoff, to_fixtures
    known = ["Man United", "Nott'm Forest", "Ath Madrid", "Arsenal", "Brighton", "Sociedad"]
    assert map_team("Manchester United", known) == "Man United"
    assert map_team("Nottingham Forest", known) == "Nott'm Forest"
    assert map_team("Atlético de Madrid", known) == "Ath Madrid"
    assert map_team("Arsenal FC", known) == "Arsenal"
    assert map_team("Equipo Inventado", known) is None
    thu = date(2026, 10, 29)
    assert parse_kickoff("Sáb 09:00", thu) == date(2026, 10, 31)
    assert parse_kickoff("Hoy 14:00", thu) == thu
    assert parse_kickoff("2 nov", thu) == date(2026, 11, 2)
    assert parse_kickoff("sábado 31 de octubre", thu) == date(2026, 10, 31)
    assert parse_kickoff("8 de noviembre", thu) == date(2026, 11, 8)
    df, skipped = to_fixtures({"matches": [
        {"kickoff": "Sáb 09:00", "home_team": "Arsenal", "away_team": "Real Sociedad",
         "odds_home": 1.5, "odds_draw": 4.0, "odds_away": 6.0, "total_line": 2.5,
         "odds_over": 1.8, "odds_under": 2.0},
        {"home_team": "X", "away_team": "Arsenal", "odds_home": 2, "odds_draw": 3, "odds_away": 4}]},
        "E0", known, thu)
    assert len(df) == 1 and skipped == ["X vs Arsenal"]
    assert df.iloc[0]["away_team"] == "Sociedad" and df.iloc[0]["odds_over25"] == 1.8


def test_load_matches_parses_iso_and_football_data_dates(tmp_path):
    from futbol.bot.data import load_matches
    iso = tmp_path / "iso.csv"
    iso.write_text("date,home_team,away_team,odds_home\n2026-11-08,A,B,2.0\n2026-10-31,C,D,2.0\n")
    fd = tmp_path / "fd.csv"
    fd.write_text("Div,Date,HomeTeam,AwayTeam,FTHG,FTAG\nE0,08/11/2026,A,B,1,0\nE0,31/10/26,C,D,0,0\n")
    assert list(load_matches([iso])["date"].dt.strftime("%Y-%m-%d")) == ["2026-10-31", "2026-11-08"]
    assert list(load_matches([fd])["date"].dt.strftime("%Y-%m-%d")) == ["2026-10-31", "2026-11-08"]
