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

**Dataset por defecto: Liga F 2023/24** (primera división femenina de
España — Barcelona, Real Madrid, Atlético de Madrid, etc.), la única
temporada de un top-5 europeo disponible en abierto que está **completa**
(240 partidos, 16 equipos, 30 partidos cada uno — se verificó explícitamente
antes de usarla; otras temporadas "gratuitas" de StatsBomb para clubes
masculinos como La Liga o Premier League solo incluyen los partidos de un
equipo concreto, no la liga entera, y no sirven para un modelo de forma por
equipo).

Para añadir más temporadas/ligas (todas completas y verificadas), edita
`futbol/config.py::COMPETITIONS` con más pares `(competition_id, season_id)`
de StatsBomb (ver `data/competitions.json` en su repo) y vuelve a ejecutar
la ingesta.

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
# 1. Descargar y procesar los datos (una sola vez; usa cache en data/raw/)
python -m futbol.data.build_dataset

# 2. Pronosticar un partido
python -m futbol.predict --list-teams
python -m futbol.predict "Barcelona WFC" "Real Madrid CF W"

# 3. Ver el backtest / validación de calibración
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
   acierto real coincide con la probabilidad prometida.

## Validación de la confianza (75%-100%)

El requisito de que la confianza mostrada corresponda a una probabilidad
real de entre el 75% y el 100% se valida empíricamente, no se asume:

```
python -m futbol.evaluate
```

En el dataset de Liga F 2023/24, con un split honesto (calibrador ajustado
solo con el primer 70% cronológico de partidos, medido en el 30% final,
nunca visto por el calibrador): los pronósticos con probabilidad calibrada
≥75% acertaron ~85-87% de las veces, tanto en los mercados basados en
Dixon-Coles (1X2, goles, BTTS) como en los basados en las Poisson de equipo
(corners, tarjetas, tiros, tiros a puerta). Es decir, el filtro de
confianza es realista y ligeramente conservador, no optimista.

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
