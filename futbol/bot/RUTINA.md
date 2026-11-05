# Rutina semanal del bot (paper trading con cuotas de Rushbet)

La ejecuta una tarea programada cada viernes. Todo es **simulado**: nunca
iniciar sesión en Rushbet ni apostar, solo leer cuotas públicas.

Trabajar en la rama `claude/sports-betting-trading-bot-10qgeu`
(`git fetch origin <rama> && git checkout <rama> && git pull`).
Instalar dependencias: `pip install -r requirements.txt`.
`HOY` = fecha de hoy (YYYY-MM-DD); `TEMP` = temporada actual en formato
football-data (2026/27 -> `2627`).

1. **Históricos (football-data.co.uk) con TinyFish `fetch_content`** (ttl 0):
   `https://www.football-data.co.uk/mmz4281/{TEMP}/E0.csv` y la de las dos
   temporadas anteriores. El resultado suele ser demasiado grande y se guarda
   en un archivo JSON: sacar `results[i].text` y escribirlo en
   `data/odds/E0_{temporada}.csv`. Comprobar que la última fecha del CSV de
   la temporada actual es reciente.

2. **Liquidar** las apuestas abiertas con los resultados nuevos:
   `python -m futbol.bot settle --ledger data/rushbet/ledger_rushbet.json --results data/odds/E0_{TEMP}.csv`

3. **Leer cuotas de Rushbet con TinyFish `run_web_automation`**:
   url `https://www.rushbet.co/?page=sportsbook#filter/football/england/premier_league`,
   `browser_profile: stealth`, proxy `CO`, `max_duration_seconds: 400`.
   Goal: no iniciar sesión, no apostar, no tocar el cupón; leer los próximos
   partidos pre-partido de la Premier League con fecha, hora, local,
   visitante, cuotas decimales 1/X/2 y más/menos 2.5 si se ven (null si no).
   `output_schema`: objeto con `matches` (array de objetos con `date`,
   `time`, `home_team`, `away_team`, `odds_home`, `odds_draw`, `odds_away`,
   `odds_over25`, `odds_under25`; los dos últimos `"type": "number",
   "nullable": true` — TinyFish no acepta arrays de tipos). Si la llamada da
   timeout de 60 s, sigue corriendo: buscarla con `list_runs` y esperar con
   `wait_for_run`. Guardar `result` en `data/rushbet/E0_{HOY}.json`.

4. **Convertir y escanear**:
   ```
   python -m futbol.bot.rushbet data/rushbet/E0_{HOY}.json --competition E0 \
       --history data/odds/E0_*.csv --out data/rushbet/fixtures_E0.csv --today {HOY}
   python -m futbol.bot scan --history <las 3 temporadas de data/odds/E0_*.csv> \
       --fixtures data/rushbet/fixtures_E0.csv --ledger data/rushbet/ledger_rushbet.json --place
   python -m futbol.bot report --ledger data/rushbet/ledger_rushbet.json
   ```
   Si el conversor avisa de equipos sin mapear, añadirlos a `ALIASES` en
   `futbol/bot/rushbet.py` (con test) y repetir.

5. **Registrar**: añadir una entrada al final de `data/rushbet/HISTORIAL.md`
   con la fecha, apuestas liquidadas (ganadas/perdidas, P&L), apuestas
   nuevas, banca simulada, yield acumulado y CLV si hay. Commit y push a la
   rama. No abrir PR.

6. **Resumen** final en español para el usuario: resultado de la semana,
   apuestas nuevas (partido, mercado, cuota, stake) y estado de la banca.
   Recordar que es simulado y que el backtest con datos reales es negativo.

Si algo falla (Rushbet cambia la página, TinyFish no responde,
football-data no tiene datos nuevos), no inventar cuotas ni resultados:
registrar el fallo en el historial y decirlo en el resumen.
