# FUTBOL — Modelo de pronóstico de partidos

Modelo que pronostica, para un partido de fútbol:

- **Marcador más probable** (y top-5 de marcadores)
- **Resultado 1X2**
- **Goles**: over/under en varias líneas
- **Ambos equipos marcan (BTTS)**
- **Corners, tarjetas, tiros totales y tiros a puerta** — por equipo
- **Tiros y tiros a puerta esperados de los 3 jugadores con más volumen de cada equipo**

Cada pronóstico solo se muestra si su **probabilidad real, validada por
backtest, está entre el 75% y el 100%** (ver [Validación de la
confianza](#validación-de-la-confianza-75-100)). Si ningún resultado de un
mercado alcanza ese umbral, se indica explícitamente en vez de forzar un
pronóstico poco fiable.

## Fuente de datos

**[StatsBomb Open Data](https://github.com/statsbomb/open-data)**, gratuita
y de uso libre para fines no comerciales/investigación (requiere atribución
a StatsBomb). Se eligió después de comprobar que:

- `football-data.co.uk` (la fuente pública "clásica" de estadísticas de
  equipo) **no incluye estadísticas por jugador**, y este proyecto las
  necesita para el mercado de tiros por jugador.
- Este entorno de ejecución no tiene salida a internet general (solo a
  GitHub y a los índices de paquetes), así que solo son viables fuentes
  servidas desde GitHub.
- StatsBomb Open Data sí publica eventos completos partido a partido
  (goles, cada tiro con su resultado exacto, corners, tarjetas, con el
  jugador que los generó), lo que permite calcular TODOS los mercados
  pedidos, incluido el de jugadores, con datos reales.

### Competiciones incluidas

Se recorrieron ~75 competiciones/temporadas candidatas de StatsBomb Open
Data y se verificó, para cada una, que todos los equipos disputan (casi) el
mismo número de partidos — es decir que es una temporada/torneo **completo**
y no el recorte de un solo equipo, que es lo que StatsBomb regala para la
mayoría de ligas masculinas top-5 en temporadas recientes (por ejemplo, casi
todas las temporadas gratuitas de La Liga o de la Bundesliga masculina
resultan ser solo los partidos del Barcelona o del Bayern, y se descartaron
por eso). Con las que sí superaron esa verificación se armó esta lista:

**Ligas masculinas** (temporada completa):
- Premier League 2015/16 (Inglaterra)
- La Liga 2015/16 (España)
- Serie A 2015/16 (Italia)
- Ligue 1 2015/16 (Francia)
- Indian Super League 2021/22 (India)

**Torneos masculinos de selecciones** (torneo completo):
- FIFA World Cup 2018 y 2022
- UEFA Euro 2020 y 2024
- Copa América 2024
- Africa Cup of Nations 2023

**Ligas femeninas** (temporada completa):
- Liga F 2023/24 (España)
- Frauen Bundesliga 2023/24 (Alemania)
- Serie A Women 2023/24 (Italia)
- FA Women's Super League 2018/19, 2020/21 y 2023/24 (Inglaterra)
- NWSL 2023 (Estados Unidos)

**Torneos femeninos de selecciones** (torneo completo):
- Women's World Cup 2019 y 2023
- UEFA Women's Euro 2022 y 2025

Para añadir más (todas completas y verificadas), edita
`futbol/config.py::COMPETITIONS` con más pares `(competition_id, season_id)`
de StatsBomb (ver `data/competitions.json` en su repo) y vuelve a ejecutar
la ingesta.

### Un modelo por competición, no uno global

Mezclar todo en un único modelo distorsionaría los resultados: la ventaja
de jugar de local en un club no existe igual en un Mundial a sede neutral,
y el ritmo de gol de una liga femenina doméstica no es el de un torneo de
selecciones masculino. Por eso `futbol/pipeline.py` agrupa por la columna
`competition` y ajusta un Dixon-Coles + juego de modelos Poisson +
calibración **independiente para cada una**. Al pronosticar un partido, si
el nombre de los dos equipos identifica una única competición en común no
hace falta indicarla explícitamente; si hay ambigüedad (o los dos equipos
no coinciden en ninguna) el CLI lo dice y hay que usar `--competition`.

### Limitación conocida

No hay ninguna fuente gratuita con esta granularidad (evento a evento, por
jugador) para las ligas masculinas top-5 en temporada en curso — esos datos
solo existen en proveedores de pago (Opta, StatsBomb IQ, Wyscout,
API-Football...). El pipeline está desacoplado en capas (`data/` →
`features/` → `models/`) precisamente para poder sustituir la fuente de
datos por una de pago sin tocar los modelos: basta con producir las mismas
tablas `matches.csv` / `player_match.csv` desde el nuevo proveedor.

## Instalación

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Uso

```bash
# 1. Descargar y procesar los datos (tarda; descarga eventos de miles de
#    partidos y borra el JSON crudo de cada uno tras procesarlo para no
#    llenar el disco — usa --keep-raw-events si quieres conservarlos)
python -m futbol.data.build_dataset

# 2. Ver qué competiciones y equipos hay disponibles
python -m futbol.predict --list-competitions
python -m futbol.predict --list-teams --competition "Liga F 2023/24 (España)"

# 3. Pronosticar un partido (detecta la competición automáticamente si el
#    par de equipos es inequívoco; si no, se indica con --competition)
python -m futbol.predict "Barcelona WFC" "Real Madrid CF W"
python -m futbol.predict "Real Madrid" "Barcelona" --competition "La Liga 2015/16 (España)"

# 4. Ver el backtest / validación de calibración (todas las competiciones,
#    o una en concreto con --competition)
python -m futbol.evaluate
```

## Cómo funciona

1. **`futbol/data/`**: descarga (con cache local) los partidos y eventos de
   StatsBomb y los convierte en dos tablas planas: `matches.csv` (una fila
   por partido, con goles/tiros/corners/tarjetas de cada equipo) y
   `player_match.csv` (una fila por jugador y partido, con sus tiros y
   tiros a puerta). Definiciones usadas: tiro a puerta = resultado
   Goal/Saved/Saved To Post; corner = pase de tipo Corner; tarjeta = evento
   Bad Behaviour o Foul Committed con card asociada (Second Yellow cuenta
   como roja).

2. **`futbol/features/`**: construye, para cada equipo y jugador, medias
   móviles de forma **sin fuga de datos** (usan `shift(1)` antes del
   `rolling`, así el partido X solo ve partidos anteriores) y un rating Elo
   de goles (metodología [World Football Elo
   Ratings](https://www.eloratings.net/about)).

3. **`futbol/models/dixon_coles.py`**: modelo Dixon-Coles (Poisson
   bivariante con corrección de marcadores bajos) ajustado por máxima
   verosimilitud con ponderación temporal (partidos recientes pesan más).
   De él salen marcador más probable, 1X2, goles over/under y BTTS.

4. **`futbol/models/poisson_markets.py`**: una regresión Poisson por
   estadística (corners, tarjetas, tiros, tiros a puerta) que predice el
   valor esperado de un equipo a partir de su forma reciente y la del
   rival.

5. **`futbol/models/player_shots.py`**: en vez de un modelo por jugador
   (hay muy pocos partidos por jugador para eso), se calcula la "cuota" de
   tiros de cada jugador sobre el total histórico de su equipo y se aplica
   al número de tiros que el modelo de equipo espera para ESE partido
   concreto (que ya tiene en cuenta la fuerza del rival).

6. **`futbol/models/calibration.py`**: backtest walk-forward (reentrena los
   modelos usando solo partidos anteriores a cada bloque evaluado) que
   calibra las probabilidades crudas con regresión isotónica y mide si el
   acierto real coincide con la probabilidad prometida. El tamaño de la
   ventana de calentamiento y de reentrenamiento se adapta al tamaño de la
   competición (una liga de 380 partidos no necesita el mismo esquema que
   un torneo de 31); en competiciones demasiado pequeñas para un backtest
   fiable, el pronóstico usa la probabilidad Poisson/Dixon-Coles sin
   calibrar en vez de fallar.

7. **`futbol/pipeline.py`**: orquesta todo lo anterior **por competición**
   (agrupando por la columna `competition`), no de forma global — ver
   [Un modelo por competición](#un-modelo-por-competición-no-uno-global).

## Validación de la confianza (75%-100%)

El requisito de que la confianza mostrada corresponda a una probabilidad
real de entre el 75% y el 100% se valida empíricamente, no se asume:

```
python -m futbol.evaluate
```

`evaluate.py` corre este backtest **competición por competición** (cada una
tiene su propio modelo, ver arriba) con un split honesto: el calibrador se
ajusta solo con el primer 70% cronológico de partidos de esa competición y
se mide el acierto en el 30% final, nunca visto por el calibrador. En Liga F
2023/24, por ejemplo, los pronósticos con probabilidad calibrada ≥75%
acertaron ~85-87% de las veces, tanto en los mercados basados en Dixon-Coles
(1X2, goles, BTTS) como en los basados en las Poisson de equipo (corners,
tarjetas, tiros, tiros a puerta) — es decir, el filtro de confianza es
realista y ligeramente conservador, no optimista. En torneos pequeños
(31-64 partidos) hay menos datos para validar y el informe lo refleja con
un `n` más bajo; ahí conviene mirar también la calibración "de referencia"
(no hold-out) que imprime `evaluate.py`.

**Importante sobre el marcador exacto**: en fútbol ningún marcador exacto
alcanza el 75% de probabilidad real (el más probable de un partido suele
rondar 10-20%). El modelo siempre calcula el marcador más probable y su top
5, pero los presenta como información, no como "pronóstico de alta
confianza" — igual que ocurre con el mercado BTTS en partidos muy
desequilibrados, donde a veces tampoco hay un lado que supere el 75%.

## Tests

```bash
python -m pytest tests/ -q
```
