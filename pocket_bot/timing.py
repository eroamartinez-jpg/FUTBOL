"""Cálculo de la hora de entrada y de expiración.

En opciones binarias la entrada se hace al abrir la vela siguiente a la que
generó la señal, para que la operación cubra velas completas. La expiración
es la entrada más `expiry_candles` velas.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo


@dataclass
class EntryWindow:
    entry: datetime        # hora de entrada (apertura de la próxima vela)
    expiry: datetime       # hora de cierre de la operación
    seconds_left: int      # segundos que faltan para entrar
    duration_s: int        # duración de la operación en segundos


def next_candle_open(now: datetime, period_s: int) -> datetime:
    """Primer múltiplo de `period_s` estrictamente posterior a `now` (UTC)."""
    ts = now.timestamp()
    nxt = (int(ts) // period_s + 1) * period_s
    return datetime.fromtimestamp(nxt, tz=timezone.utc)


def entry_window(
    period_s: int,
    expiry_candles: int = 1,
    now: datetime | None = None,
    tz: str | None = None,
    min_lead_s: int = 5,
    immediate: bool = False,
) -> EntryWindow:
    """Ventana de entrada para una señal calculada en `now`.

    Si quedan menos de `min_lead_s` segundos para la próxima vela no da
    tiempo a abrir la operación a mano, así que se salta a la siguiente.
    Con `immediate` (modo automático) la entrada es `now`.
    """
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    entry = now if immediate else next_candle_open(now, period_s)
    if not immediate and (entry - now).total_seconds() < min_lead_s:
        entry += timedelta(seconds=period_s)
    duration = period_s * expiry_candles
    expiry = entry + timedelta(seconds=duration)
    zone = ZoneInfo(tz) if tz else datetime.now().astimezone().tzinfo
    return EntryWindow(
        entry=entry.astimezone(zone),
        expiry=expiry.astimezone(zone),
        seconds_left=int((entry - now).total_seconds()),
        duration_s=duration,
    )
