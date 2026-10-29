"""CLI del bot.

    python -m pocket_bot                 # escaneo único con Pocket Option
    python -m pocket_bot --loop          # repite en cada vela
    python -m pocket_bot --synthetic     # prueba sin conexión
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from .scanner import Opportunity, scan
from .timing import next_candle_open

DISCLAIMER = (
    "AVISO: las opciones binarias son de muy alto riesgo y la mayoría de los "
    "operadores pierde dinero. Estas señales son estimaciones estadísticas, "
    "no garantías. Prueba primero en cuenta DEMO."
)


def parse_args(argv=None):
    p = argparse.ArgumentParser(prog="pocket_bot", description="Señales de tendencia para Pocket Option")
    p.add_argument("--ssid", help="SSID de sesión de Pocket Option (o variable POCKET_SSID). "
                                  "Sin él se usa una sesión demo de invitado.")
    p.add_argument("--period", type=int, default=60, help="Temporalidad de vela en segundos (60 = M1)")
    p.add_argument("--expiry", type=int, default=1, help="Expiración en número de velas")
    p.add_argument("--min-payout", type=int, default=80, help="Payout mínimo del activo en %%")
    p.add_argument("--min-confidence", type=float, default=60.0, help="Confianza mínima 0-100")
    p.add_argument("--min-trades", type=int, default=20, help="Señales mínimas en el backtest")
    p.add_argument("--count", type=int, default=500, help="Velas de historial por activo")
    p.add_argument("--max-assets", type=int, help="Limitar número de activos escaneados")
    p.add_argument("--top", type=int, default=15, help="Filas a mostrar")
    p.add_argument("--all", action="store_true", help="Mostrar también activos no recomendados")
    p.add_argument("--tz", help="Zona horaria para mostrar las horas (ej. America/Bogota). "
                                "Por defecto la del sistema.")
    p.add_argument("--loop", action="store_true", help="Escanear en cada cierre de vela")
    p.add_argument("--synthetic", action="store_true", help="Datos sintéticos (sin conexión)")
    p.add_argument("--auto-trade", action="store_true",
                   help="Abrir operaciones automáticamente en las señales recomendadas")
    p.add_argument("--amount", type=float, default=1.0, help="Monto por operación (auto-trade)")
    p.add_argument("--allow-real", action="store_true",
                   help="Permitir auto-trade en cuenta REAL (por defecto solo demo)")
    return p.parse_args(argv)


def fmt_dur(seconds: int) -> str:
    m, s = divmod(seconds, 60)
    return f"{m}m{s:02d}s" if m else f"{s}s"


def print_table(opps: list[Opportunity], top: int, show_all: bool) -> None:
    rows = opps if show_all else [o for o in opps if o.recommended]
    if not rows:
        print("Sin señales recomendadas en esta vela. Espera a la siguiente.")
        return
    hdr = f"{'':2}{'ACTIVO':<16}{'SEÑAL':<8}{'CONF':>6}{'PAYOUT':>8}{'ACIERTO BT':>12}{'EQUIL.':>8}{'N':>5}  {'ENTRADA':<10}{'EXPIRA':<10}{'FALTA':>7}"
    print(hdr)
    print("-" * len(hdr))
    for o in rows[:top]:
        s, b, w = o.signal, o.stats, o.window
        arrow = "▲ CALL" if s.direction == "CALL" else "▼ PUT" if s.direction == "PUT" else "—"
        mark = "★ " if o.recommended else "  "
        print(f"{mark}{s.asset:<16}{arrow:<8}{s.confidence:>5.0f}%{o.payout:>7}%"
              f"{b.win_rate * 100:>11.1f}%{b.breakeven * 100:>7.1f}%{b.trades:>5}  "
              f"{w.entry:%H:%M:%S}  {w.expiry:%H:%M:%S}  {fmt_dur(w.seconds_left):>7}")
    print("\n★ = recomendada: confianza >= umbral y el backtest del activo supera el "
          "% de acierto de equilibrio que exige su payout.")


def run_once(source, args) -> list[Opportunity]:
    errors = []
    opps = scan(source, args.period, args.expiry, args.min_payout, args.min_confidence,
                args.min_trades, args.count, args.max_assets, args.tz,
                immediate=args.auto_trade, on_error=lambda a, e: errors.append((a, e)))
    now = datetime.now(ZoneInfo(args.tz)) if args.tz else datetime.now().astimezone()
    print(f"\n=== Escaneo {now:%Y-%m-%d %H:%M:%S %Z} | M{args.period // 60 or args.period} | "
          f"{len(opps)} activos analizados | expiración {args.expiry} vela(s) ===")
    print_table(opps, args.top, args.all)
    for a, e in errors:
        print(f"  (no se pudo leer {a}: {e})", file=sys.stderr)
    if args.auto_trade:
        for o in opps:
            if o.recommended:
                try:
                    res = source.place(o.signal.asset, o.signal.direction, args.amount,
                                       o.window.duration_s)
                    print(f"  → orden {o.signal.direction} {o.signal.asset} ${args.amount}: {res[0]}")
                except Exception as exc:
                    print(f"  → error al abrir {o.signal.asset}: {exc}", file=sys.stderr)
    return opps


def main(argv=None) -> int:
    args = parse_args(argv)
    print(DISCLAIMER)
    if args.synthetic:
        from .data import SyntheticSource
        source = SyntheticSource()
        if args.auto_trade:
            print("--auto-trade no aplica con --synthetic.")
            args.auto_trade = False
    else:
        from .data import PocketOptionSource
        source = PocketOptionSource(args.ssid)
        demo = source.is_demo()
        print(f"Conectado a Pocket Option ({'DEMO' if demo else 'REAL'}).")
        if args.auto_trade and not demo and not args.allow_real:
            print("Cuenta REAL detectada: auto-trade desactivado (usa --allow-real bajo tu riesgo).")
            args.auto_trade = False

    if not args.loop:
        run_once(source, args)
        return 0
    try:
        while True:
            run_once(source, args)
            # Esperar al cierre de la próxima vela (+2 s para que el servidor la publique).
            nxt = next_candle_open(datetime.now(timezone.utc), args.period)
            time.sleep(max((nxt - datetime.now(timezone.utc)).total_seconds() + 2, 1))
    except KeyboardInterrupt:
        print("\nDetenido.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
