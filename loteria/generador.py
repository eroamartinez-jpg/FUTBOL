"""Generador de jugadas.

Ninguna combinación tiene más probabilidad de salir que otra. Lo único que
sí se puede mejorar en un juego con premio mayor compartido (Baloto,
Revancha, MiLoto) es **cuánto te toca si ganas**: si eliges combinaciones que
poca gente juega, en caso de acertar compartes el acumulado con menos
personas. Por eso el generador:

1. Elige al azar de forma uniforme (cada combinación con la misma
   probabilidad, como el sorteo).
2. Descarta las combinaciones que mucha gente juega: todas ≤31 (fechas de
   cumpleaños), secuencias, progresiones, números muy agrupados, todas del
   mismo lado del tiquete o combinaciones que ya ganaron.

En el chance el premio es fijo (no se comparte), así que ahí ningún número
es mejor que otro y simplemente se genera uno al azar.
"""
from __future__ import annotations

import secrets
from collections import Counter

import numpy as np

from .juegos import JuegoLoto

_rng = np.random.default_rng(secrets.randbits(64))


def motivos_popular(combo: list[int], juego: JuegoLoto, ganadoras: set[tuple] | None = None) -> list[str]:
    """Razones por las que una combinación probablemente la juega mucha gente."""
    c = sorted(combo)
    motivos = []
    if max(c) <= 31:
        motivos.append("todos los números son ≤31 (parecen fechas)")
    racha = mejor = 1
    for a, b in zip(c, c[1:]):
        racha = racha + 1 if b == a + 1 else 1
        mejor = max(mejor, racha)
    if mejor >= 3:
        motivos.append(f"{mejor} números consecutivos")
    difs = {b - a for a, b in zip(c, c[1:])}
    if len(difs) == 1:
        motivos.append("progresión aritmética")
    if max(Counter(x // 10 for x in c).values()) >= 4:
        motivos.append("4+ números en la misma decena")
    if max(Counter(x % 10 for x in c).values()) >= 3:
        motivos.append("3+ números con la misma terminación")
    if all(x % 2 == 0 for x in c) or all(x % 2 == 1 for x in c):
        motivos.append("todos pares o todos impares")
    if ganadoras and tuple(c) in ganadoras:
        motivos.append("ya salió ganadora (mucha gente la repite)")
    return motivos


def generar_loto(juego: JuegoLoto, cantidad: int = 1, ganadoras: set[tuple] | None = None,
                 rng: np.random.Generator | None = None) -> list[dict]:
    rng = rng or _rng
    jugadas, vistas = [], set()
    while len(jugadas) < cantidad:
        combo = sorted((rng.choice(juego.n, juego.k, replace=False) + 1).tolist())
        if tuple(combo) in vistas or motivos_popular(combo, juego, ganadoras):
            continue
        vistas.add(tuple(combo))
        extra = int(rng.integers(1, juego.extra + 1)) if juego.extra else None
        jugadas.append({"numeros": combo, "extra": extra})
    return jugadas


def generar_chance(cantidad: int = 1, rng: np.random.Generator | None = None) -> list[str]:
    rng = rng or _rng
    return [f"{int(rng.integers(0, 10_000)):04d}" for _ in range(cantidad)]
