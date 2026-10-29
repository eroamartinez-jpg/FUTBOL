# pocket_bot — Señales de tendencia para Pocket Option

> **Aviso:** las opciones binarias son de muy alto riesgo y la mayoría de los
> operadores pierde dinero. Ningún indicador predice el mercado con certeza:
> este bot da **estimaciones estadísticas**, no garantías. Úsalo primero en
> cuenta **DEMO**. Pocket Option no tiene API oficial; la conexión usa una
> librería comunitaria que puede romperse si la plataforma cambia.

## Qué hace

1. **Se conecta a Pocket Option** y lee la lista de activos con su payout
   actual (forex, OTC, cripto, acciones, materias primas…). Escanea **todos**
   los que tengan un payout ≥ `--min-payout`.
2. Para cada activo descarga las últimas velas (por defecto 500) y calcula
   una **señal de tendencia** por confluencia de 7 votos: cruce EMA 9/21,
   precio vs EMA 50, histograma MACD y su pendiente, RSI, Estocástico y
   Bandas de Bollinger. La confianza se reduce cuando el ADX indica mercado
   lateral.
3. **Valida cada activo con un backtest** sobre su propio historial: solo
   marca ★ (recomendada) una señal si, con el mismo umbral de confianza y el
   mismo retraso de entrada, la estrategia acertó en ese activo **más que el
   % de equilibrio** que exige su payout (`1 / (1 + payout)`; con 92 % es
   52,1 %).
4. **Indica la hora de entrada** (apertura de la próxima vela), la hora de
   expiración y los segundos que faltan, en tu zona horaria.

## Instalación

```bash
pip install -r pocket_bot/requirements.txt
```

## Uso

```bash
# Escaneo único con una sesión demo de invitado (no requiere cuenta)
python -m pocket_bot

# Con tu cuenta: SSID de la sesión (ver abajo)
export POCKET_SSID='42["auth",{"session":"...","isDemo":1,...}]'
python -m pocket_bot --tz America/Bogota

# Repetir automáticamente en cada vela, M5 con expiración de 2 velas (10 min)
python -m pocket_bot --loop --period 300 --expiry 2

# Ver todos los activos, no solo los recomendados
python -m pocket_bot --all --top 50

# Probar sin conexión con datos sintéticos
python -m pocket_bot --synthetic --all
```

Salida de ejemplo:

```
  ACTIVO          SEÑAL     CONF  PAYOUT  ACIERTO BT  EQUIL.    N  ENTRADA   EXPIRA      FALTA
----------------------------------------------------------------------------------------------
★ USDJPY_otc      ▲ CALL     83%     88%       63.5%   53.2%  233  11:56:00  11:57:00      39s
★ EURUSD_otc      ▲ CALL     67%     92%       55.1%   52.1%  158  11:56:00  11:57:00      39s
```

- **CONF**: fuerza de la confluencia (0–100).
- **ACIERTO BT / N**: % de acierto y número de señales en el backtest del activo.
- **EQUIL.**: % de acierto mínimo para no perder dinero con ese payout.
- **ENTRADA / EXPIRA**: a qué hora abrir la operación y cuándo vence. En
  Pocket Option elige la misma expiración (`--period × --expiry` segundos).

### Opciones principales

| Opción | Por defecto | Descripción |
|---|---|---|
| `--period` | 60 | Temporalidad en segundos (60 = M1, 300 = M5) |
| `--expiry` | 1 | Expiración en número de velas |
| `--min-payout` | 80 | Payout mínimo del activo (%) |
| `--min-confidence` | 60 | Confianza mínima para señal |
| `--min-trades` | 20 | Señales mínimas en el backtest para confiar en él |
| `--tz` | sistema | Zona horaria de las horas mostradas |
| `--loop` | – | Re-escanear en cada cierre de vela |
| `--auto-trade --amount N` | – | Abrir las operaciones recomendadas al instante (solo DEMO salvo `--allow-real`) |

## Cómo obtener el SSID

1. Inicia sesión en pocketoption.com desde el navegador.
2. Abre las herramientas de desarrollador (F12) → pestaña **Red / Network** → filtro **WS**.
3. Recarga la página, abre la conexión WebSocket y en **Mensajes** busca el
   que empieza por `42["auth",`. Copia ese mensaje completo.

El SSID da acceso a tu cuenta: **no lo compartas ni lo subas al repositorio**.

## Hora de entrada y backtest coherentes

Al operar a mano, entre que cierra la vela que da la señal y la hora de
entrada pasa al menos una vela (el bot deja ≥ 5 s de margen). El backtest
simula exactamente ese retraso, así que el % de acierto mostrado corresponde
a entrar a la hora indicada, no al instante del cierre. Con `--auto-trade`
la orden se abre en el momento del escaneo y el backtest usa retraso cero.

## Estructura

- `indicators.py` — EMA, RSI, MACD, Bollinger, Estocástico, ADX.
- `strategy.py` — votos, puntaje y confianza por vela.
- `backtest.py` — validación walk-forward por activo.
- `timing.py` — hora de entrada y expiración.
- `data.py` — conexión a Pocket Option y fuente sintética.
- `scanner.py` / `__main__.py` — escaneo multi-activo y CLI.

Pruebas: `python -m pytest tests/test_pocket_bot.py`.
