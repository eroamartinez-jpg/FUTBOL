"""Reglas y probabilidades EXACTAS de los juegos de azar colombianos.

Todas las probabilidades de este módulo son combinatoria pura: no dependen de
ningún historial. En un sorteo bien hecho (esferas o generador certificado y
auditado por Coljuegos/Supersalud) cada combinación tiene exactamente la
misma probabilidad, así que estas cifras son el techo de lo que cualquier
"predicción" puede lograr.

Los planes de premios de chance son los publicados por los operadores
(4 cifras directo 4.500x, etc.). Pueden cambiar: verifícalos con tu operador.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import comb


@dataclass(frozen=True)
class JuegoLoto:
    """Juego tipo loto: elegir `k` números de 1..`n` (+ opcional balota extra 1..`extra`)."""

    nombre: str
    n: int
    k: int
    extra: int = 0  # tamaño del bombo de la balota adicional (0 = no tiene)

    @property
    def combinaciones(self) -> int:
        return comb(self.n, self.k) * max(self.extra, 1)

    def prob_aciertos(self, aciertos: int, extra_acertada: bool | None = None) -> float:
        """P(acertar exactamente `aciertos` números principales [y la extra sí/no])."""
        p = comb(self.k, aciertos) * comb(self.n - self.k, self.k - aciertos) / comb(self.n, self.k)
        if self.extra and extra_acertada is not None:
            p *= (1 / self.extra) if extra_acertada else (1 - 1 / self.extra)
        return p

    def aciertos_esperados(self) -> float:
        """Media de números principales acertados por boleta: k*k/n."""
        return self.k * self.k / self.n

    def tabla_categorias(self) -> list[tuple[str, float]]:
        filas = []
        for a in range(self.k, -1, -1):
            if self.extra:
                for sb in (True, False):
                    filas.append((f"{a}+{1 if sb else 0}", self.prob_aciertos(a, sb)))
            else:
                filas.append((f"{a}", self.prob_aciertos(a)))
        return filas


BALOTO = JuegoLoto("Baloto", n=43, k=5, extra=16)
REVANCHA = JuegoLoto("Revancha", n=43, k=5, extra=16)
MILOTO = JuegoLoto("MiLoto", n=39, k=5)

JUEGOS_LOTO = {"baloto": BALOTO, "revancha": REVANCHA, "miloto": MILOTO}


# --- Chance --------------------------------------------------------------
# Pago por cada peso apostado (premio neto antes de impuestos/retención).
PLAN_CHANCE = {
    "4_directo": 4500,      # 4 cifras en su orden
    "4_combinado": 208,     # 4 cifras en cualquier orden (número con 4 cifras distintas)
    "3_directo": 400,       # 3 últimas cifras en su orden
    "3_combinado": 83,      # 3 últimas cifras en cualquier orden (3 cifras distintas)
    "2_directo": 50,        # 2 últimas cifras
    "1_directo": 5,         # última cifra
}


def permutaciones_distintas(numero: str) -> int:
    """Cuántos números distintos se forman reordenando las cifras de `numero`."""
    from collections import Counter
    from math import factorial

    total = factorial(len(numero))
    for c in Counter(numero).values():
        total //= factorial(c)
    return total


def chance_modalidades(numero: str) -> list[dict]:
    """Probabilidad, pago y valor esperado por peso de cada modalidad para `numero`.

    `numero` es el número de 4 cifras que se juega (p. ej. "0724").
    El resultado de chance es un número de 4 cifras 0000-9999 equiprobable.
    """
    if len(numero) != 4 or not numero.isdigit():
        raise ValueError("El chance se juega con un número de 4 cifras, p. ej. 0724")
    filas = []

    def fila(modalidad, prob, pago):
        filas.append({
            "modalidad": modalidad,
            "probabilidad": prob,
            "uno_en": 1 / prob,
            "paga_por_peso": pago,
            "retorno_esperado": prob * pago,  # pesos que vuelven, en promedio, por peso apostado
        })

    fila("4 cifras directo", 1 / 10_000, PLAN_CHANCE["4_directo"])
    if permutaciones_distintas(numero) == 24:
        fila("4 cifras combinado", 24 / 10_000, PLAN_CHANCE["4_combinado"])
    fila("3 cifras directo", 1 / 1_000, PLAN_CHANCE["3_directo"])
    if permutaciones_distintas(numero[-3:]) == 6:
        fila("3 cifras combinado", 6 / 1_000, PLAN_CHANCE["3_combinado"])
    fila("2 cifras", 1 / 100, PLAN_CHANCE["2_directo"])
    fila("1 cifra (uña)", 1 / 10, PLAN_CHANCE["1_directo"])
    return filas


# --- Loterías tradicionales (Bogotá, Medellín, Boyacá, Cruz Roja, ...) ----------
def loteria_mayor(series: int) -> dict:
    """Probabilidad del premio mayor de una lotería tradicional.

    Número de 4 cifras (10.000) x `series` emitidas (varía por lotería y sorteo,
    típicamente entre 100 y 500; consulta el plan de premios del sorteo).
    """
    total = 10_000 * series
    return {"billetes_posibles": total, "probabilidad": 1 / total}
