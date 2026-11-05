"""Señal (edge), tamaño de posición (Kelly fraccional) y límites de riesgo."""
from __future__ import annotations

from dataclasses import dataclass, field

from futbol.bot.odds import fair_probabilities


@dataclass
class StrategyConfig:
    # Señal: valor esperado mínimo por unidad apostada (0.05 = +5% EV).
    min_edge: float = 0.05
    min_model_prob: float = 0.20
    min_odds: float = 1.40
    max_odds: float = 5.00
    # Si el modelo se aleja más que esto de la probabilidad justa del
    # mercado, se asume error del modelo (lesiones, rotaciones, datos
    # viejos...) y no se apuesta. El mercado suele saber más que un Poisson.
    max_disagreement: float = 0.15
    # Sizing: fracción de Kelly (1.0 = Kelly completo, muy volátil).
    kelly_fraction: float = 0.25
    max_stake_pct: float = 0.03
    # Riesgo: tope de exposición total por jornada/fecha.
    max_round_exposure_pct: float = 0.15
    max_bets_per_match: int = 1
    markets: tuple[str, ...] = field(default=("1x2", "ou2.5"))


@dataclass
class BetSignal:
    date: str
    home_team: str
    away_team: str
    market: str
    selection: str
    odds: float
    model_prob: float
    fair_prob: float | None
    edge: float
    kelly: float
    stake: float = 0.0
    closing_odds: float | None = None
    competition: str = ""


def expected_value(prob: float, odds: float) -> float:
    """EV por unidad apostada: p * cuota - 1."""
    return prob * odds - 1.0


def kelly_fraction(prob: float, odds: float) -> float:
    """Fracción óptima de Kelly para una cuota decimal (0 si no hay valor)."""
    b = odds - 1.0
    return max(0.0, (prob * odds - 1.0) / b) if b > 0 else 0.0


def stake_for(prob: float, odds: float, bankroll: float, cfg: StrategyConfig) -> float:
    pct = min(cfg.kelly_fraction * kelly_fraction(prob, odds), cfg.max_stake_pct)
    return round(max(0.0, bankroll * pct), 2)


def find_value_bets(date: str, home_team: str, away_team: str,
                    model_probs: dict[str, dict[str, float]],
                    market_odds: dict[str, dict[str, float]],
                    bankroll: float, cfg: StrategyConfig,
                    closing_odds: dict[str, dict[str, float]] | None = None) -> list[BetSignal]:
    """Compara modelo vs cuotas de un partido y devuelve las mejores apuestas."""
    signals = []
    for market in cfg.markets:
        odds = market_odds.get(market)
        probs = model_probs.get(market)
        if not odds or not probs:
            continue
        complete = set(odds) == set(probs)
        fair = fair_probabilities(odds) if complete else {}
        for sel, o in odds.items():
            p = probs.get(sel)
            if p is None or not (cfg.min_odds <= o <= cfg.max_odds) or p < cfg.min_model_prob:
                continue
            edge = expected_value(p, o)
            if edge < cfg.min_edge:
                continue
            fp = fair.get(sel)
            if fp is not None and abs(p - fp) > cfg.max_disagreement:
                continue
            close = (closing_odds or {}).get(market, {}).get(sel)
            signals.append(BetSignal(
                date=date, home_team=home_team, away_team=away_team, market=market,
                selection=sel, odds=o, model_prob=p, fair_prob=fp, edge=edge,
                kelly=kelly_fraction(p, o), stake=stake_for(p, o, bankroll, cfg),
                closing_odds=close,
            ))
    signals.sort(key=lambda s: -s.edge)
    return [s for s in signals[:cfg.max_bets_per_match] if s.stake > 0]


def apply_exposure_limit(signals: list[BetSignal], bankroll: float, cfg: StrategyConfig) -> list[BetSignal]:
    """Escala los stakes de una jornada para no superar la exposición máxima."""
    cap = bankroll * cfg.max_round_exposure_pct
    total = sum(s.stake for s in signals)
    if total > cap > 0:
        factor = cap / total
        for s in signals:
            s.stake = round(s.stake * factor, 2)
    return [s for s in signals if s.stake > 0]
