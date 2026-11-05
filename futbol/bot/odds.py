"""Utilidades de cuotas decimales: probabilidad implícita y margen de la casa."""
from __future__ import annotations


def implied_probability(odds: float) -> float:
    """Probabilidad implícita de una cuota decimal (incluye el margen)."""
    if odds <= 1.0:
        raise ValueError(f"cuota decimal inválida: {odds}")
    return 1.0 / odds


def overround(odds: dict[str, float]) -> float:
    """Margen de la casa en un mercado completo: suma de implícitas - 1.

    Ej.: 1X2 a 2.00 / 3.40 / 3.80 -> 0.5 + 0.294 + 0.263 - 1 = 5.7%.
    """
    return sum(implied_probability(o) for o in odds.values()) - 1.0


def fair_probabilities(odds: dict[str, float]) -> dict[str, float]:
    """Probabilidades "justas" del mercado quitando el margen (proporcional).

    Sirve como referencia del consenso del mercado: si el modelo se aleja
    mucho de esto, lo más probable es que el que se equivoque sea el modelo.
    """
    implied = {k: implied_probability(o) for k, o in odds.items()}
    total = sum(implied.values())
    return {k: p / total for k, p in implied.items()}
