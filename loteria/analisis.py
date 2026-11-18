"""Análisis estadístico del historial y backtest de estrategias de "predicción".

La pregunta que responde este módulo es empírica: ¿hay algún patrón en los
sorteos reales que permita acertar más de lo que da el azar? Para eso:

1. `prueba_uniformidad` mide si algunos números salen más de lo esperado
   (p-valor por Monte Carlo, simulando historias de sorteos justos).
2. `backtest` juega, sorteo a sorteo y sin mirar el futuro, las estrategias
   populares (números calientes, fríos, atrasados...) y compara cuántos
   números acierta cada una contra el valor teórico del azar.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from .juegos import JuegoLoto

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "loterias"
COLS = ["n1", "n2", "n3", "n4", "n5"]


def cargar_historial(juego: str = "baloto") -> pd.DataFrame:
    df = pd.read_csv(DATA_DIR / f"{juego}.csv", parse_dates=["fecha"])
    return df.sort_values("fecha").reset_index(drop=True)


def matriz(df: pd.DataFrame) -> np.ndarray:
    return df[COLS].to_numpy(dtype=int)


def frecuencias(df: pd.DataFrame, juego: JuegoLoto) -> pd.DataFrame:
    m = matriz(df)
    conteo = np.bincount(m.ravel(), minlength=juego.n + 1)[1:]
    esperado = len(df) * juego.k / juego.n
    ultimo = {}
    for i, fila in enumerate(m):
        for x in fila:
            ultimo[x] = i
    atraso = [len(df) - 1 - ultimo.get(x, -1) for x in range(1, juego.n + 1)]
    return pd.DataFrame({
        "numero": range(1, juego.n + 1),
        "veces": conteo,
        "esperado": round(esperado, 1),
        "desviacion": conteo - esperado,
        "sorteos_sin_salir": atraso,
    }).sort_values("veces", ascending=False).reset_index(drop=True)


def _chi2(conteo: np.ndarray, esperado: float) -> float:
    return float(((conteo - esperado) ** 2 / esperado).sum())


def prueba_uniformidad(df: pd.DataFrame, juego: JuegoLoto, simulaciones: int = 2000,
                       semilla: int = 7) -> dict:
    """¿Las frecuencias observadas son compatibles con un sorteo justo?

    Devuelve el estadístico chi-cuadrado observado y la fracción de historias
    simuladas (con sorteos 100% aleatorios del mismo tamaño) que dan un valor
    igual o mayor. p-valor alto => las diferencias entre números son las que
    produce el puro azar.
    """
    m = matriz(df)
    n_sorteos = len(m)
    esperado = n_sorteos * juego.k / juego.n
    obs = _chi2(np.bincount(m.ravel(), minlength=juego.n + 1)[1:], esperado)

    rng = np.random.default_rng(semilla)
    mayores = 0
    for _ in range(simulaciones):
        sim = np.argsort(rng.random((n_sorteos, juego.n)), axis=1)[:, : juego.k]
        if _chi2(np.bincount(sim.ravel(), minlength=juego.n), esperado) >= obs:
            mayores += 1
    res = {"sorteos": n_sorteos, "chi2": obs, "p_valor": (mayores + 1) / (simulaciones + 1)}

    if juego.extra and "superbalota" in df:
        c = np.bincount(df["superbalota"].to_numpy(), minlength=juego.extra + 1)[1:]
        e = n_sorteos / juego.extra
        obs_sb = _chi2(c, e)
        mayores = sum(
            _chi2(np.bincount(rng.integers(0, juego.extra, n_sorteos), minlength=juego.extra), e) >= obs_sb
            for _ in range(simulaciones)
        )
        res["chi2_superbalota"] = obs_sb
        res["p_valor_superbalota"] = (mayores + 1) / (simulaciones + 1)
    return res


# --- Estrategias de "predicción" que se suelen vender -----------------------------
def _conteo(pasado: np.ndarray, n: int) -> np.ndarray:
    return np.bincount(pasado.ravel(), minlength=n + 1)[1:].astype(float)


def _top(puntaje: np.ndarray, k: int, rng) -> np.ndarray:
    # desempate aleatorio para no favorecer números bajos
    ruido = rng.random(len(puntaje)) * 1e-6
    return np.argsort(-(puntaje + ruido))[:k] + 1


def est_aleatoria(pasado, juego, rng):
    return rng.choice(juego.n, juego.k, replace=False) + 1


def est_calientes(pasado, juego, rng, ventana=30):
    return _top(_conteo(pasado[-ventana:], juego.n), juego.k, rng)


def est_frias(pasado, juego, rng, ventana=30):
    return _top(-_conteo(pasado[-ventana:], juego.n), juego.k, rng)


def est_atrasados(pasado, juego, rng):
    atraso = np.full(juego.n, len(pasado), dtype=float)
    for i, fila in enumerate(pasado):
        atraso[fila - 1] = len(pasado) - 1 - i
    return _top(atraso, juego.k, rng)


def est_mas_frecuentes_historico(pasado, juego, rng):
    return _top(_conteo(pasado, juego.n), juego.k, rng)


def est_repetir_ultimo(pasado, juego, rng):
    return pasado[-1]


ESTRATEGIAS = {
    "aleatoria": est_aleatoria,
    "calientes (últimos 30)": est_calientes,
    "fríos (últimos 30)": est_frias,
    "atrasados": est_atrasados,
    "más frecuentes histórico": est_mas_frecuentes_historico,
    "repetir el último sorteo": est_repetir_ultimo,
}


@dataclass
class ResultadoBacktest:
    estrategia: str
    jugadas: int
    aciertos_medios: float
    error_estandar: float
    con_3_o_mas: float  # sorteos con 3+ aciertos, promedio por pasada


def backtest(df: pd.DataFrame, juego: JuegoLoto, calentamiento: int = 50,
             repeticiones: int = 20, semilla: int = 11) -> tuple[list[ResultadoBacktest], float]:
    """Walk-forward: en cada sorteo t cada estrategia elige con los sorteos < t.

    Se repite `repeticiones` veces (cambian los desempates/azar) para estabilizar.
    Devuelve los resultados y los aciertos esperados por puro azar (k*k/n).
    """
    m = matriz(df)
    rng = np.random.default_rng(semilla)
    resultados = []
    for nombre, f in ESTRATEGIAS.items():
        aciertos = []
        for _ in range(repeticiones):
            for t in range(calentamiento, len(m)):
                jugada = set(f(m[:t], juego, rng).tolist())
                aciertos.append(len(jugada & set(m[t].tolist())))
        a = np.array(aciertos)
        resultados.append(ResultadoBacktest(
            nombre, len(a), float(a.mean()),
            float(a.std(ddof=1) / np.sqrt(len(a) / repeticiones)),  # SE por sorteos independientes
            (a >= 3).sum() / repeticiones,
        ))
    return resultados, juego.aciertos_esperados()
