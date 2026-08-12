"""Configuración global del proyecto FUTBOL."""
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT_DIR / "data" / "raw"
PROCESSED_DIR = ROOT_DIR / "data" / "processed"

STATSBOMB_BASE_URL = "https://raw.githubusercontent.com/statsbomb/open-data/master/data"

# Competiciones/temporadas StatsBomb Open Data a ingerir.
# (competition_id, season_id, etiqueta legible)
# Todas son temporadas COMPLETAS (round-robin), verificadas antes de usarlas:
# cada equipo disputa el mismo número de partidos que sus rivales.
COMPETITIONS = [
    (182, 281, "Liga F 2023/24 (España)"),
]

# Intervalo de confianza real exigido para mostrar un pronóstico.
CONFIDENCE_MIN = 0.75
CONFIDENCE_MAX = 1.00

# Número de partidos previos usados en las medias móviles de equipo/jugador.
TEAM_ROLLING_WINDOW = 10
PLAYER_ROLLING_WINDOW = 8

# Mínimo de partidos previos disputados para que un equipo/jugador entre en el modelo.
MIN_TEAM_HISTORY = 3
MIN_PLAYER_HISTORY = 2

RANDOM_SEED = 42
