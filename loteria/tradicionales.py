"""Loterías tradicionales de Colombia (Bogotá, Medellín, Boyacá, Cruz Roja, ...).

Cada sorteo saca un número de 4 cifras (0000-9999) y una serie. Ese mismo
número de 4 cifras es el que usa el chance, así que este análisis sirve
también para el chance de cada lotería.

Datos: `data/loterias/loterias_tradicionales.json`, con la frecuencia de cada
cifra (0-9) en cada una de las 4 posiciones desde 2014 y los últimos
resultados de 15 loterías.

La pregunta es la misma que con Baloto: ¿hay alguna cifra que salga más de
lo que da el azar en alguna posición? Se responde con una prueba
chi-cuadrado por posición (p-valor por Monte Carlo) y, como se hacen 60
pruebas a la vez (15 loterías x 4 posiciones), se compara cuántas salen
"significativas" contra las ~3 que el azar produce por sí solo.
"""
from __future__ import annotations

import json
import secrets
from functools import lru_cache
from math import comb

import numpy as np

from .analisis import DATA_DIR

SIMULACIONES = 20_000


@lru_cache(maxsize=1)
def cargar_loterias() -> dict:
    with open(DATA_DIR / "loterias_tradicionales.json", encoding="utf-8") as f:
        return json.load(f)["loterias"]


def _chi2(conteos: np.ndarray) -> np.ndarray:
    esperado = conteos.sum(axis=-1, keepdims=True) / conteos.shape[-1]
    return ((conteos - esperado) ** 2 / esperado).sum(axis=-1)


def p_valores_posiciones(freq: list[list[int]], semilla: int = 3) -> list[float]:
    """p-valor (Monte Carlo) de que cada posición tenga cifras equiprobables."""
    rng = np.random.default_rng(semilla)
    n = int(sum(freq[0]))
    nulos = _chi2(rng.multinomial(n, [0.1] * 10, size=SIMULACIONES).astype(float))
    obs = _chi2(np.array(freq, dtype=float))
    return [float(((nulos >= o).sum() + 1) / (SIMULACIONES + 1)) for o in obs]


def resumen() -> list[dict]:
    filas = []
    for clave, d in cargar_loterias().items():
        freq = d["frecuencia_por_posicion"]
        p = p_valores_posiciones(freq)
        filas.append({
            "clave": clave,
            "nombre": d["nombre"],
            "dia": d["dia"],
            "premio_mayor": d["premio_mayor"],
            "sorteos": d["sorteos_en_estadistica"],
            "ultimo": d["ultimos_resultados"][0],
            "p_valores": p,
            "cifra_mas_frecuente": [int(np.argmax(f)) for f in freq],
        })
    return filas


def prueba_global(filas: list[dict]) -> dict:
    """Cuántas de las pruebas dan p<0.05 frente a las que da el azar."""
    ps = [p for f in filas for p in f["p_valores"]]
    pruebas = len(ps)
    return {
        "pruebas": pruebas,
        "significativas": sum(p < 0.05 for p in ps),
        "esperadas_por_azar": pruebas * 0.05,
        # Bonferroni: para afirmar un sesgo real hace falta p < 0.05 / pruebas
        "umbral_corregido": 0.05 / pruebas,
        "superan_umbral_corregido": sum(p < 0.05 / pruebas for p in ps),
        "p_minimo": min(ps),
        # probabilidad de ver al menos esas "significativas" si todo es azar
        "p_de_ver_tantas": float(sum(comb(pruebas, k) * 0.05**k * 0.95**(pruebas - k)
                                     for k in range(sum(p < 0.05 for p in ps), pruebas + 1))),
    }


def generar_numero(rng: np.random.Generator | None = None) -> str:
    """Número de 4 cifras al azar. Todos tienen probabilidad 1 en 10.000."""
    rng = rng or np.random.default_rng(secrets.randbits(64))
    return f"{int(rng.integers(0, 10_000)):04d}"
