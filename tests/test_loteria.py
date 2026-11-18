from math import comb

import numpy as np
import pytest

from loteria.analisis import backtest, cargar_historial, prueba_uniformidad
from loteria.generador import generar_chance, generar_loto, motivos_popular
from loteria.juegos import BALOTO, MILOTO, chance_modalidades, permutaciones_distintas


def test_probabilidades_exactas():
    assert BALOTO.combinaciones == comb(43, 5) * 16 == 15_401_568
    assert MILOTO.combinaciones == 575_757
    total = sum(p for _, p in BALOTO.tabla_categorias())
    assert total == pytest.approx(1.0)
    assert BALOTO.aciertos_esperados() == pytest.approx(25 / 43)


def test_chance_retorno_por_debajo_de_lo_apostado():
    filas = {f["modalidad"]: f for f in chance_modalidades("0724")}
    assert filas["4 cifras directo"]["retorno_esperado"] == pytest.approx(0.45)
    assert "4 cifras combinado" in filas
    assert all(f["retorno_esperado"] < 1 for f in filas.values())
    # con cifras repetidas no existe el combinado de 24 permutaciones
    assert "4 cifras combinado" not in {f["modalidad"] for f in chance_modalidades("1123")}
    assert permutaciones_distintas("1123") == 12


def test_filtro_de_combinaciones_populares():
    assert motivos_popular([1, 2, 3, 4, 5], BALOTO)
    assert motivos_popular([3, 7, 12, 19, 25], BALOTO)  # todas <= 31
    assert not motivos_popular([4, 17, 26, 33, 40], BALOTO)


def test_generadores():
    rng = np.random.default_rng(0)
    jugadas = generar_loto(BALOTO, 20, rng=rng)
    assert len({tuple(j["numeros"]) for j in jugadas}) == 20
    for j in jugadas:
        assert len(set(j["numeros"])) == 5 and 1 <= j["extra"] <= 16
        assert not motivos_popular(j["numeros"], BALOTO)
    assert all(len(n) == 4 and n.isdigit() for n in generar_chance(10, rng=rng))


def test_historial_real_es_consistente_con_azar():
    df = cargar_historial("baloto")
    assert len(df) > 300
    assert df[["n1", "n2", "n3", "n4", "n5"]].to_numpy().max() <= 43
    u = prueba_uniformidad(df, BALOTO, simulaciones=300)
    assert u["p_valor"] > 0.01


def test_backtest_ninguna_estrategia_supera_el_azar():
    df = cargar_historial("baloto")
    res, azar = backtest(df, BALOTO, repeticiones=3)
    for r in res:
        assert abs(r.aciertos_medios - azar) < 4 * r.error_estandar + 0.05
