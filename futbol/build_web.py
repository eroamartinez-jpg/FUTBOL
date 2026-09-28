"""Genera la página autocontenida `web/predictor.html` a partir de la
plantilla (`web/predictor_template.html`) y dos fuentes de datos:

- `web/model_data.json` (ver `futbol.export_web`): modelos StatsBomb ya
  ajustados y calibrados por backtest, temporadas históricas completas.
- `web/live_leagues.json`: banco de equipos de temporada en curso
  (2026-27), tomado del artifact "Predictor de Fútbol" del usuario. No
  tiene calibración por backtest (no hay historial partido a partido para
  esas ligas), así que la página lo etiqueta como estimación, no como
  probabilidad validada. Ver `scripts`/notas del proyecto para cómo se
  regenera este archivo a partir de ese artifact.

El resultado no necesita servidor ni conexión: todo el motor de predicción
corre en el navegador.

Uso:
    python -m futbol.export_web
    python -m futbol.build_web
    # abrir web/predictor.html en cualquier navegador
"""
from __future__ import annotations

import json

from futbol.config import ROOT_DIR

TEMPLATE_PATH = ROOT_DIR / "web" / "predictor_template.html"
DATA_PATH = ROOT_DIR / "web" / "model_data.json"
LIVE_DATA_PATH = ROOT_DIR / "web" / "live_leagues.json"
OUTPUT_PATH = ROOT_DIR / "web" / "predictor.html"

_EMPTY_LIVE = {"updated": "(sin datos en vivo cargados)", "rho": -0.13, "home_advantage": 1.2,
               "max_goals": 6, "leagues": [], "teams": {}}


def _safe(json_text: str) -> str:
    return json_text.replace("</script", "<\\/script")


def main() -> None:
    if not DATA_PATH.exists():
        raise FileNotFoundError(f"No existe {DATA_PATH}. Corré primero: python -m futbol.export_web")

    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    data_json = DATA_PATH.read_text(encoding="utf-8")

    if LIVE_DATA_PATH.exists():
        live_json = LIVE_DATA_PATH.read_text(encoding="utf-8")
    else:
        live_json = json.dumps(_EMPTY_LIVE)
        print(f"Aviso: no existe {LIVE_DATA_PATH}, la página queda sin ligas en vivo.")

    output = template.replace("__MODEL_DATA_JSON__", _safe(data_json))
    output = output.replace("__LIVE_DATA_JSON__", _safe(live_json))
    OUTPUT_PATH.write_text(output, encoding="utf-8")
    print(f"Guardado {OUTPUT_PATH} ({len(output) / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
