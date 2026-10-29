"""Libro de apuestas (paper trading): registro, liquidación y métricas de P&L."""
from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from futbol.bot.markets import bet_won
from futbol.bot.strategy import BetSignal


class Ledger:
    def __init__(self, initial_bankroll: float):
        self.initial_bankroll = float(initial_bankroll)
        self.bets: list[dict] = []

    # --- estado -----------------------------------------------------------
    @property
    def bankroll(self) -> float:
        """Banca liquidada: inicial + P&L de las apuestas cerradas."""
        return self.initial_bankroll + sum(b["pnl"] for b in self.bets if b["status"] != "open")

    @property
    def available(self) -> float:
        """Banca menos lo que está comprometido en apuestas abiertas."""
        return self.bankroll - sum(b["stake"] for b in self.bets if b["status"] == "open")

    def open_bets(self) -> list[dict]:
        return [b for b in self.bets if b["status"] == "open"]

    # --- operaciones ------------------------------------------------------
    def place(self, signal: BetSignal) -> dict:
        bet = {"bet_id": len(self.bets) + 1, **asdict(signal), "status": "open", "pnl": 0.0}
        self.bets.append(bet)
        return bet

    def settle(self, bet: dict, home_goals: int, away_goals: int) -> dict:
        won = bet_won(bet["market"], bet["selection"], int(home_goals), int(away_goals))
        bet["status"] = "won" if won else "lost"
        bet["pnl"] = round(bet["stake"] * (bet["odds"] - 1.0), 2) if won else -bet["stake"]
        bet["score"] = f"{int(home_goals)}-{int(away_goals)}"
        return bet

    # --- persistencia -----------------------------------------------------
    def save(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(
            {"initial_bankroll": self.initial_bankroll, "bets": self.bets}, indent=2, ensure_ascii=False))

    @classmethod
    def load(cls, path: str | Path) -> "Ledger":
        data = json.loads(Path(path).read_text())
        ledger = cls(data["initial_bankroll"])
        ledger.bets = data["bets"]
        return ledger

    # --- métricas ---------------------------------------------------------
    def summary(self) -> dict:
        settled = [b for b in self.bets if b["status"] in ("won", "lost")]
        staked = sum(b["stake"] for b in settled)
        pnl = sum(b["pnl"] for b in settled)
        won = sum(1 for b in settled if b["status"] == "won")

        curve, peak, max_dd = self.initial_bankroll, self.initial_bankroll, 0.0
        for b in settled:
            curve += b["pnl"]
            peak = max(peak, curve)
            max_dd = max(max_dd, (peak - curve) / peak if peak > 0 else 0.0)

        # CLV (closing line value): si cogimos mejor cuota que la de cierre,
        # le ganamos al mercado. Es el mejor indicador de habilidad a largo
        # plazo porque tiene mucha menos varianza que el P&L.
        clv = [b["odds"] / b["closing_odds"] - 1.0 for b in settled if b.get("closing_odds")]
        return {
            "bets": len(settled),
            "open": len(self.open_bets()),
            "won": won,
            "hit_rate": won / len(settled) if settled else None,
            "staked": round(staked, 2),
            "pnl": round(pnl, 2),
            "yield": pnl / staked if staked else None,
            "roi_bankroll": pnl / self.initial_bankroll,
            "bankroll": round(self.bankroll, 2),
            "max_drawdown": max_dd,
            "avg_odds": sum(b["odds"] for b in settled) / len(settled) if settled else None,
            "avg_edge": sum(b["edge"] for b in settled) / len(settled) if settled else None,
            "avg_clv": sum(clv) / len(clv) if clv else None,
            "beat_closing_pct": sum(1 for c in clv if c > 0) / len(clv) if clv else None,
        }
