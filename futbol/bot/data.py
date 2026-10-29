"""Lectura de CSV de resultados + cuotas.

Formato principal: el de football-data.co.uk (https://www.football-data.co.uk/data.php),
gratuito, con resultados y cuotas de cierre/apertura de varias casas para
~25 ligas desde los 90 hasta la temporada en curso. Columnas usadas:

  Date, HomeTeam, AwayTeam, FTHG, FTAG (resultado; vacío en partidos futuros)
  {P}H, {P}D, {P}A              cuotas 1X2 de la casa P
  {P}>2.5, {P}<2.5              cuotas over/under 2.5
  {P}CH, {P}CD, {P}CA, {P}C>2.5, {P}C<2.5   cuotas de cierre (opcionales)

Casas: B365 (Bet365), PS (Pinnacle; su over/under usa el prefijo "P"),
Avg (media del mercado), Max (mejor cuota disponible).

También acepta columnas genéricas para cuotas de cualquier otra fuente:
odds_home, odds_draw, odds_away, odds_over25, odds_under25, odds_btts_yes, odds_btts_no.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

BOOK_PREFIXES = {
    "B365": {"1x2": "B365", "ou": "B365"},
    "PS": {"1x2": "PS", "ou": "P"},
    "Avg": {"1x2": "Avg", "ou": "Avg"},
    "Max": {"1x2": "Max", "ou": "Max"},
}

GENERIC_COLUMNS = {
    ("1x2", "home"): "odds_home", ("1x2", "draw"): "odds_draw", ("1x2", "away"): "odds_away",
    ("ou2.5", "over"): "odds_over25", ("ou2.5", "under"): "odds_under25",
    ("btts", "yes"): "odds_btts_yes", ("btts", "no"): "odds_btts_no",
}


def _odds_columns(book: str, closing: bool) -> dict[tuple[str, str], str]:
    if book not in BOOK_PREFIXES:
        raise ValueError(f"casa desconocida '{book}'. Opciones: {', '.join(BOOK_PREFIXES)}")
    p = BOOK_PREFIXES[book]
    c = "C" if closing else ""
    return {
        ("1x2", "home"): f"{p['1x2']}{c}H", ("1x2", "draw"): f"{p['1x2']}{c}D",
        ("1x2", "away"): f"{p['1x2']}{c}A",
        ("ou2.5", "over"): f"{p['ou']}{c}>2.5", ("ou2.5", "under"): f"{p['ou']}{c}<2.5",
    }


def load_matches(paths: list[str | Path]) -> pd.DataFrame:
    """Concatena uno o varios CSV y normaliza nombres de columnas y fecha."""
    frames = []
    for path in paths:
        df = pd.read_csv(path, encoding="latin-1")
        df = df.dropna(how="all")
        df = df.rename(columns={"HomeTeam": "home_team", "AwayTeam": "away_team",
                                "FTHG": "home_goals", "FTAG": "away_goals",
                                "Date": "date", "Div": "competition"})
        df["date"] = pd.to_datetime(df["date"], dayfirst=True, format="mixed")
        if "competition" not in df.columns:
            df["competition"] = Path(path).stem
        frames.append(df)
    out = pd.concat(frames, ignore_index=True).sort_values("date", kind="stable").reset_index(drop=True)
    return out


def row_odds(row: pd.Series, book: str, closing: bool = False) -> dict[str, dict[str, float]]:
    """Cuotas válidas de una fila como {mercado: {selección: cuota}}."""
    cols = {} if closing else dict(GENERIC_COLUMNS)
    cols.update(_odds_columns(book, closing))
    out: dict[str, dict[str, float]] = {}
    for (market, sel), col in cols.items():
        val = row.get(col)
        if val is not None and pd.notna(val) and float(val) > 1.0:
            out.setdefault(market, {})[sel] = float(val)
    return out


def played(df: pd.DataFrame) -> pd.DataFrame:
    return df.dropna(subset=["home_goals", "away_goals"])
