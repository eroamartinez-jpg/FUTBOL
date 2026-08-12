"""Genera la página autocontenida `web/predictor.html` a partir de la
plantilla (`web/predictor_template.html`) y los datos exportados
(`web/model_data.json`, ver `futbol.export_web`). El resultado no necesita
servidor ni conexión: todo el motor de predicción corre en el navegador.

Uso:
    python -m futbol.export_web
    python -m futbol.build_web
    # abrir web/predictor.html en cualquier navegador
"""
from __future__ import annotations

from futbol.config import ROOT_DIR

TEMPLATE_PATH = ROOT_DIR / "web" / "predictor_template.html"
DATA_PATH = ROOT_DIR / "web" / "model_data.json"
OUTPUT_PATH = ROOT_DIR / "web" / "predictor.html"


def main() -> None:
    if not DATA_PATH.exists():
        raise FileNotFoundError(f"No existe {DATA_PATH}. Corré primero: python -m futbol.export_web")

    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    data_json = DATA_PATH.read_text(encoding="utf-8")
    # Por si el JSON llegara a contener la subcadena "</script>" (no debería,
    # son solo números y nombres, pero por seguridad).
    data_json_safe = data_json.replace("</script", "<\\/script")

    output = template.replace("__MODEL_DATA_JSON__", data_json_safe)
    OUTPUT_PATH.write_text(output, encoding="utf-8")
    print(f"Guardado {OUTPUT_PATH} ({len(output) / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
