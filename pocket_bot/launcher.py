"""Punto de entrada del ejecutable (PyInstaller).

Si se abre con doble clic (sin argumentos) pregunta la configuración básica
y arranca en modo continuo. La ventana no se cierra sola al terminar o ante
un error, para que se pueda leer el mensaje.
"""
from __future__ import annotations

import sys
import traceback

from pocket_bot.__main__ import main


def ask(prompt: str, default: str = "") -> str:
    value = input(f"{prompt} [{default or 'Enter = omitir'}]: ").strip()
    return value or default


def interactive_args() -> list[str]:
    print("=== Pocket Bot — configuración rápida (Enter acepta el valor por defecto) ===\n")
    args = ["--loop"]
    ssid = ask("SSID de tu sesión de Pocket Option (vacío = demo de invitado)")
    if ssid:
        args += ["--ssid", ssid]
    tz = ask("Zona horaria (ej. America/Bogota, America/Mexico_City)")
    if tz:
        args += ["--tz", tz]
    minutes = ask("Temporalidad de vela en minutos (1, 5, 15...)", "1")
    args += ["--period", str(int(float(minutes) * 60))]
    args += ["--expiry", ask("Expiración en número de velas", "1")]
    args += ["--min-payout", ask("Payout mínimo %", "80")]
    if ask("¿Probar sin conexión con datos sintéticos? (s/n)", "n").lower().startswith("s"):
        args.append("--synthetic")
    print()
    return args


def run() -> int:
    # La consola de Windows usa cp1252 por defecto y no sabe imprimir ★ ▲ ▼.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
        except (AttributeError, ValueError):
            pass
    argv = sys.argv[1:] or interactive_args()
    try:
        return main(argv)
    except SystemExit as exc:
        if exc.code not in (0, None):
            print(exc)
        return exc.code if isinstance(exc.code, int) else 1
    except Exception:
        traceback.print_exc()
        return 1
    finally:
        if not sys.argv[1:]:
            input("\nPresiona Enter para cerrar...")


if __name__ == "__main__":
    sys.exit(run())
