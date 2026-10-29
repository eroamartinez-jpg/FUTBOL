"""Fuentes de velas: Pocket Option (real) y sintética (pruebas sin conexión).

Pocket Option no publica una API oficial. La conexión usa la librería
comunitaria `BinaryOptionsToolsV2`, que habla el mismo WebSocket que la web
de la plataforma autenticándose con el SSID de tu sesión.
"""
from __future__ import annotations

import os
import zlib
from typing import Protocol

import numpy as np
import pandas as pd


class CandleSource(Protocol):
    def assets(self, min_payout: int) -> dict[str, int]:
        """Activos disponibles -> payout en %."""

    def candles(self, asset: str, period_s: int, count: int) -> pd.DataFrame:
        """Velas cerradas (open/high/low/close) indexadas por hora UTC."""

    def server_time(self) -> float | None:
        """Hora del servidor (epoch) si se conoce."""


def candles_to_frame(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    if df.empty:
        return pd.DataFrame(columns=["open", "high", "low", "close"])
    t = df["time"]
    if pd.api.types.is_numeric_dtype(t):
        idx = pd.to_datetime(t, unit="s", utc=True)
    else:
        idx = pd.to_datetime(t, utc=True)
    df = df.set_index(idx)[["open", "high", "low", "close"]].astype(float)
    return df[~df.index.duplicated(keep="last")].sort_index()


class PocketOptionSource:
    """Datos en vivo de Pocket Option.

    - Con `ssid` (o variable de entorno POCKET_SSID) usa tu cuenta.
    - Sin SSID abre una sesión de invitado "Try demo" (solo datos/demo).
    """

    def __init__(self, ssid: str | None = None):
        try:
            from BinaryOptionsToolsV2.pocketoption import PocketOption
        except ImportError as exc:  # pragma: no cover - depende del entorno
            raise SystemExit(
                "Falta la librería de conexión: pip install BinaryOptionsToolsV2"
            ) from exc
        ssid = ssid or os.environ.get("POCKET_SSID")
        self.client = PocketOption(ssid) if ssid else PocketOption.try_demo()

    def assets(self, min_payout: int) -> dict[str, int]:
        payouts = self.client.payouts() or {}
        return {a: int(p) for a, p in payouts.items() if p and int(p) >= min_payout}

    def candles(self, asset: str, period_s: int, count: int) -> pd.DataFrame:
        return candles_to_frame(self.client.candles(asset, period_s, count=count))

    def server_time(self) -> float | None:
        try:
            return float(self.client.get_server_time())
        except Exception:
            return None

    def is_demo(self) -> bool:
        return bool(self.client.is_demo())

    def place(self, asset: str, direction: str, amount: float, duration_s: int):
        fn = self.client.buy if direction == "CALL" else self.client.sell
        return fn(asset, amount, duration_s)


class SyntheticSource:
    """Velas aleatorias con tendencias por tramos, para probar sin conexión."""

    ASSETS = {
        "EURUSD_otc": 92, "GBPUSD_otc": 90, "USDJPY_otc": 88, "AUDCAD_otc": 85,
        "BTCUSD_otc": 80, "ETHUSD_otc": 78, "#AAPL_otc": 82, "XAUUSD_otc": 86,
    }

    def __init__(self, seed: int = 0):
        self.seed = seed

    def assets(self, min_payout: int) -> dict[str, int]:
        return {a: p for a, p in self.ASSETS.items() if p >= min_payout}

    def candles(self, asset: str, period_s: int, count: int) -> pd.DataFrame:
        rng = np.random.default_rng(zlib.crc32(f"{asset}:{self.seed}".encode()))
        drift = np.repeat(rng.normal(0, 0.0004, count // 40 + 1), 40)[:count]
        close = 1.0 * np.exp(np.cumsum(drift + rng.normal(0, 0.001, count)))
        open_ = np.concatenate([[close[0]], close[:-1]])
        spread = np.abs(rng.normal(0, 0.0005, count)) * close
        end = pd.Timestamp.now(tz="UTC").floor(f"{period_s}s")
        idx = pd.date_range(end=end - pd.Timedelta(seconds=period_s), periods=count,
                            freq=f"{period_s}s")
        return pd.DataFrame({
            "open": open_, "close": close,
            "high": np.maximum(open_, close) + spread,
            "low": np.minimum(open_, close) - spread,
        }, index=idx)

    def server_time(self) -> float | None:
        return None
