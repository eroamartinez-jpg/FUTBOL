"""Configuración global del proyecto FUTBOL."""
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT_DIR / "data" / "raw"
PROCESSED_DIR = ROOT_DIR / "data" / "processed"

STATSBOMB_BASE_URL = "https://raw.githubusercontent.com/statsbomb/open-data/master/data"

# Competiciones/temporadas StatsBomb Open Data a ingerir.
# (competition_id, season_id, etiqueta legible)
# Todas fueron verificadas antes de usarlas (script de verificación: se
# descargó matches.json de ~75 competiciones candidatas y se comprobó que
# cada equipo disputa (casi) el mismo número de partidos que sus rivales,
# es decir que son temporadas/torneos COMPLETOS y no el recorte de un solo
# equipo, que es lo que ofrece StatsBomb gratis para la mayoría de ligas
# masculinas top-5 en temporadas recientes). Se descartaron explícitamente:
# todas las demás temporadas de La Liga (son solo los partidos del Barça),
# Bundesliga masculina (solo Bayern), MLS (un solo equipo), Champions
# League/Copa del Rey/Europa League (un único partido histórico suelto),
# Ligue 1 2021/22 y 2022/23 (solo PSG), y los Mundiales anteriores a 2018
# (un puñado de partidos sueltos, no el torneo completo).

COMPETITIONS = [
    # --- Ligas masculinas (temporada completa) ---
    (2, 27, "Premier League 2015/16 (Inglaterra)"),
    (11, 27, "La Liga 2015/16 (España)"),
    (12, 27, "Serie A 2015/16 (Italia)"),
    (7, 27, "Ligue 1 2015/16 (Francia)"),
    (1238, 108, "Indian Super League 2021/22 (India)"),

    # --- Torneos masculinos de selecciones (torneo completo) ---
    (43, 3, "FIFA World Cup 2018"),
    (43, 106, "FIFA World Cup 2022"),
    (55, 43, "UEFA Euro 2020"),
    (55, 282, "UEFA Euro 2024"),
    (223, 282, "Copa América 2024"),
    (1267, 107, "Africa Cup of Nations 2023"),

    # --- Ligas femeninas (temporada completa) ---
    (182, 281, "Liga F 2023/24 (España)"),
    (135, 281, "Frauen Bundesliga 2023/24 (Alemania)"),
    (131, 281, "Serie A Women 2023/24 (Italia)"),
    (37, 281, "FA Women's Super League 2023/24 (Inglaterra)"),
    (37, 90, "FA Women's Super League 2020/21 (Inglaterra)"),
    (37, 4, "FA Women's Super League 2018/19 (Inglaterra)"),
    (49, 107, "NWSL 2023 (Estados Unidos)"),

    # --- Torneos femeninos de selecciones (torneo completo) ---
    (72, 30, "Women's World Cup 2019"),
    (72, 107, "Women's World Cup 2023"),
    (53, 106, "UEFA Women's Euro 2022"),
    (53, 315, "UEFA Women's Euro 2025"),
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
