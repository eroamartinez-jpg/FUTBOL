"""Bot de loterías colombianas.

Uso:
    python -m loteria                       # informe completo (Baloto + chance)
    python -m loteria probabilidades        # probabilidades exactas de cada juego
    python -m loteria analizar              # frecuencias y prueba de aleatoriedad (Baloto real)
    python -m loteria backtest              # ¿funcionan los números calientes/fríos?
    python -m loteria jugar baloto -n 5     # genera 5 jugadas "poco populares"
    python -m loteria jugar chance -n 3
    python -m loteria loterias              # las 15 loterías tradicionales: resultados y prueba de azar
    python -m loteria jugar loteria -n 3    # números de 4 cifras para cualquier lotería
    python -m loteria chance 0724           # probabilidad y retorno de cada modalidad para un número
"""
from __future__ import annotations

import argparse
import math

from .analisis import backtest, cargar_historial, frecuencias, matriz, prueba_uniformidad
from .generador import generar_chance, generar_loto
from .tradicionales import generar_numero, prueba_global, resumen
from .juegos import BALOTO, JUEGOS_LOTO, MILOTO, chance_modalidades, loteria_mayor


def _miles(x: float) -> str:
    return f"{x:,.0f}".replace(",", ".")


def _uno_en(p: float) -> str:
    return f"1 en {_miles(1 / p)}"


def cmd_probabilidades(_args=None):
    print("\n=== PROBABILIDADES EXACTAS (no cambian con ningún sistema) ===")
    for juego in (BALOTO, MILOTO):
        print(f"\n{juego.nombre}: {juego.k} de 1-{juego.n}" + (f" + balota 1-{juego.extra}" if juego.extra else ""))
        print(f"  Premio mayor: {_uno_en(1 / juego.combinaciones)}")
        for cat, p in juego.tabla_categorias():
            if p and cat[0] in "2345":
                print(f"    acertar {cat:<4} {p:.8f}   ({_uno_en(p)})")
    print("\nLotería tradicional (4 cifras + serie), premio mayor:")
    for series in (100, 200, 400):
        print(f"  con {series} series: {_uno_en(loteria_mayor(series)['probabilidad'])}")
    print("\nChance (número 0724 como ejemplo):")
    _imprimir_chance("0724")


def _imprimir_chance(numero: str):
    print(f"  {'modalidad':<20}{'probabilidad':>14}{'paga x peso':>13}{'te devuelve en promedio':>26}")
    for f in chance_modalidades(numero):
        print(f"  {f['modalidad']:<20}{_uno_en(f['probabilidad']):>14}{_miles(f['paga_por_peso']):>13}"
              f"{f['retorno_esperado'] * 100:>20.1f}% del valor")
    print("  → La de MAYOR probabilidad de ganar es 1 cifra (10%). Ninguna modalidad"
          " devuelve más de ~50 centavos por peso a largo plazo.")


def cmd_chance(args):
    if len(args.numero) != 4 or not args.numero.isdigit():
        raise SystemExit("El chance se juega con un número de 4 cifras, p. ej. 0724")
    print(f"\nChance con el número {args.numero}:")
    _imprimir_chance(args.numero)
    print("  Cualquier otro número de 4 cifras tiene EXACTAMENTE la misma probabilidad.")


def cmd_analizar(_args=None):
    df = cargar_historial("baloto")
    print(f"\n=== ANÁLISIS DEL HISTORIAL REAL DE BALOTO ({len(df)} sorteos, "
          f"{df.fecha.min():%d/%m/%Y} - {df.fecha.max():%d/%m/%Y}) ===")
    fr = frecuencias(df, BALOTO)
    print("\nMás frecuentes:  " + ", ".join(f"{r.numero}({r.veces})" for r in fr.head(8).itertuples()))
    print("Menos frecuentes: " + ", ".join(f"{r.numero}({r.veces})" for r in fr.tail(8).itertuples()))
    print(f"Esperado por número si es azar puro: {fr.esperado[0]} veces")
    u = prueba_uniformidad(df, BALOTO)
    print(f"\nPrueba de aleatoriedad (Monte Carlo, 2.000 historias simuladas):")
    print(f"  números principales: p-valor = {u['p_valor']:.2f}")
    print(f"  superbalota:         p-valor = {u['p_valor_superbalota']:.2f}")
    print("  (p-valor > 0.05 = las diferencias de frecuencia son las normales del azar;"
          " los 'calientes' y 'fríos' no son una señal.)")


def cmd_backtest(_args=None):
    df = cargar_historial("baloto")
    res, azar = backtest(df, BALOTO)
    print(f"\n=== BACKTEST: cada estrategia juega sorteo a sorteo sin ver el futuro ===")
    print(f"Aciertos esperados por puro azar: {azar:.3f} de 5 números\n")
    print(f"  {'estrategia':<28}{'aciertos medios':>16}{'±':>8}{'veces con 3+':>14}")
    for r in sorted(res, key=lambda r: -r.aciertos_medios):
        print(f"  {r.estrategia:<28}{r.aciertos_medios:>16.3f}{1.96 * r.error_estandar:>8.3f}{r.con_3_o_mas:>14.1f}")
    print("\n  Todas quedan dentro del margen de error del azar: ninguna 'predice'.")


def cmd_loterias(_args=None):
    filas = resumen()
    print(f"\n=== LOTERÍAS TRADICIONALES ({len(filas)}) — ¿alguna cifra sale más de la cuenta? ===")
    print(f"  {'lotería':<27}{'día':<18}{'sorteos':>8}  {'último':<12}{'p-valor por posición (1ª 2ª 3ª 4ª)':>36}")
    for f in filas:
        u = f["ultimo"]
        ult = u["numero"] + (f"-{u['serie']}" if u["serie"] else "")
        ps = "  ".join(f"{p:.2f}" for p in f["p_valores"])
        print(f"  {f['nombre']:<27}{f['dia']:<18}{f['sorteos']:>8}  {ult:<12}{ps:>36}")
    g = prueba_global(filas)
    print(f"\n  {g['significativas']} de {g['pruebas']} pruebas dan p<0,05; el azar solo ya produce ~{g['esperadas_por_azar']:.0f}"
          f" (probabilidad de ver {g['significativas']} o más por azar: {g['p_de_ver_tantas']:.0%}).")
    print(f"  Ninguna pasa el umbral corregido por hacer {g['pruebas']} pruebas (p<{g['umbral_corregido']:.4f}):"
          " no hay cifras 'calientes' que aprovechar en ninguna lotería.")
    print("  Premio mayor (número + serie): 1 en 10.000 x número de series. El chance de cada lotería usa estas 4 cifras.")


def _pct(p: float) -> str:
    v = p * 100
    if v >= 1:
        txt = f"{v:.1f}"
    elif v >= 0.01:
        txt = f"{v:.3f}"
    else:  # dos cifras significativas sin notación científica
        txt = f"{v:.{1 - math.floor(math.log10(v))}f}"
    return txt.replace(".", ",") + " %"


def _prob_numero_4(numero: str, loteria: bool = False):
    if loteria:
        print(f"      premio mayor (número + serie): 1 en 10.000 x series emitidas (con 400 series: 1 en 4.000.000)")
        print(f"      {'las 4 cifras, cualquier serie':<34}{_uno_en(1 / 10_000):>18}{_pct(1 / 10_000):>13}")
    for f in chance_modalidades(numero):
        if loteria and f["modalidad"] == "4 cifras directo":
            continue
        print(f"      {f['modalidad']:<34}{_uno_en(f["probabilidad"]):>18}{_pct(f["probabilidad"]):>13}"
              f"   paga {_miles(f['paga_por_peso'])} por peso")


def cmd_jugar(args):
    if args.juego in ("loteria", "chance"):
        es_loteria = args.juego == "loteria"
        titulo = ("Números para cualquier lotería tradicional (las filas de 3, 2 y 1 cifra son el chance de esa lotería)"
                  if es_loteria else "Números de chance")
        print(f"\n{titulo}:")
        for n in (generar_numero() if es_loteria else generar_chance(1)[0] for _ in range(args.n)):
            print(f"  {n}")
            _prob_numero_4(n, loteria=es_loteria)
        return
    juego = JUEGOS_LOTO[args.juego]
    ganadoras = None
    if args.juego == "baloto":
        ganadoras = {tuple(sorted(f)) for f in matriz(cargar_historial("baloto")).tolist()}
    print(f"\nJugadas de {juego.nombre} (azar uniforme, filtrando combinaciones populares):")
    for j in generar_loto(juego, args.n, ganadoras):
        extra = f"  superbalota {j['extra']:02d}" if j["extra"] else ""
        print("  " + " - ".join(f"{x:02d}" for x in j["numeros"]) + extra)
    print("\n  Probabilidad de cada jugada (es la misma para cualquier combinación):")
    for cat, p in juego.tabla_categorias():
        aciertos = int(cat[0])
        if aciertos < 2:
            continue
        nombre = (f"{aciertos} números + superbalota" if cat.endswith("+1") else
                  f"{aciertos} números sin superbalota" if juego.extra else f"{aciertos} números")
        print(f"      {nombre:<34}{_uno_en(p):>18}{_pct(p):>13}")
    print("  Ventaja real del filtro: si ganas, es menos probable que compartas el acumulado.")


def cmd_informe(_args=None):
    cmd_probabilidades()
    cmd_analizar()
    cmd_backtest()
    cmd_loterias()
    cmd_jugar(argparse.Namespace(juego="baloto", n=3))
    cmd_jugar(argparse.Namespace(juego="chance", n=3))
    print("\nJuega solo lo que estés dispuesto a perder. Línea de ayuda por juego"
          " problemático: consulta coljuegos.gov.co.\n")


def main(argv=None):
    p = argparse.ArgumentParser(prog="python -m loteria", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd")
    sub.add_parser("probabilidades")
    sub.add_parser("analizar")
    sub.add_parser("backtest")
    sub.add_parser("loterias")
    j = sub.add_parser("jugar")
    j.add_argument("juego", choices=[*JUEGOS_LOTO, "chance", "loteria"])
    j.add_argument("-n", type=int, default=3)
    c = sub.add_parser("chance")
    c.add_argument("numero")
    args = p.parse_args(argv)
    {
        None: cmd_informe, "probabilidades": cmd_probabilidades, "analizar": cmd_analizar,
        "backtest": cmd_backtest, "loterias": cmd_loterias, "jugar": cmd_jugar, "chance": cmd_chance,
    }[args.cmd](args)


if __name__ == "__main__":
    main()
