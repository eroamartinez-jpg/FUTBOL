"""Adaptador de cuotas de Rushbet (leídas con TinyFish) al formato del bot.

Rushbet no tiene API pública para terceros (su plataforma, Kambi, limita
las peticiones), así que las cuotas se leen de su sportsbook público con un
navegador automatizado de TinyFish, SIN iniciar sesión y SIN apostar. El
agente de TinyFish devuelve un JSON como:

    {"matches": [{"kickoff": "Sáb 09:00", "home_team": "Man. United",
                  "away_team": "Chelsea", "odds_home": 2.3, "odds_draw": 3.4,
                  "odds_away": 3.0, "total_line": 2.5, "odds_over": 1.8,
                  "odds_under": 2.0}, ...]}

Este módulo lo convierte en un CSV de próximos partidos (columnas genéricas
odds_home/odds_draw/odds_away/odds_over25/odds_under25) con los nombres de
equipo de football-data.co.uk, que es lo que lee `python -m futbol.bot scan`.

Uso:
    python -m futbol.bot.rushbet rushbet_e0.json --competition E0 \\
        --history data/odds/E0_2627.csv --out fixtures_rushbet.csv
"""
from __future__ import annotations

import argparse
import difflib
import json
import re
import unicodedata
from datetime import date, datetime, timedelta

import pandas as pd

from futbol.bot.data import load_matches

# Nombres que Rushbet/Kambi escribe distinto a football-data.co.uk y que la
# coincidencia aproximada no resuelve bien.
ALIASES = {
    "manchester united": "Man United", "manchester utd": "Man United", "man utd": "Man United",
    "manchester city": "Man City", "nottingham forest": "Nott'm Forest", "nottingham": "Nott'm Forest",
    "wolverhampton": "Wolves", "wolverhampton wanderers": "Wolves", "tottenham hotspur": "Tottenham",
    "newcastle united": "Newcastle", "west ham united": "West Ham", "brighton & hove albion": "Brighton",
    "brighton and hove albion": "Brighton", "leeds united": "Leeds", "ipswich town": "Ipswich",
    "hull city": "Hull", "coventry city": "Coventry", "afc bournemouth": "Bournemouth",
    "atletico madrid": "Ath Madrid", "atletico de madrid": "Ath Madrid", "athletic bilbao": "Ath Bilbao",
    "athletic club": "Ath Bilbao", "real sociedad": "Sociedad", "rayo vallecano": "Vallecano",
    "real betis": "Betis", "celta vigo": "Celta", "celta de vigo": "Celta", "espanyol": "Espanol",
    "rcd espanyol": "Espanol", "deportivo alaves": "Alaves", "deportivo la coruna": "La Coruna",
    "deportivo": "La Coruna", "racing santander": "Santander", "real racing club": "Santander",
    "real oviedo": "Oviedo", "real valladolid": "Valladolid", "ca osasuna": "Osasuna",
    "girona fc": "Girona", "rcd mallorca": "Mallorca", "ud las palmas": "Las Palmas",
}

DAYS_ES = {"lun": 0, "mar": 1, "mie": 2, "jue": 3, "vie": 4, "sab": 5, "dom": 6}
MONTHS_ES = {"ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6, "jul": 7, "ago": 8,
             "sep": 9, "oct": 10, "nov": 11, "dic": 12}


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[^a-z0-9& ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def map_team(name: str, known: list[str]) -> str | None:
    """Nombre de Rushbet -> nombre de football-data (None si no hay match fiable)."""
    n = _norm(name)
    if n in ALIASES and ALIASES[n] in known:
        return ALIASES[n]
    by_norm = {_norm(k): k for k in known}
    if n in by_norm:
        return by_norm[n]
    for suffix in (" fc", " cf", " afc", " sc"):
        if n.endswith(suffix) and n[: -len(suffix)] in by_norm:
            return by_norm[n[: -len(suffix)]]
    close = difflib.get_close_matches(n, list(by_norm), n=1, cutoff=0.75)
    return by_norm[close[0]] if close else None


def parse_kickoff(text: str, today: date) -> date:
    """'Sáb 09:00', 'sábado 31 de octubre', 'Hoy', '31 oct', '2026-10-31'... -> fecha."""
    t = _norm(text or "")
    if not t or t.startswith("hoy"):
        return today
    if t.startswith("manana"):
        return today + timedelta(days=1)
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", text or "")
    if m:
        return date(int(m[1]), int(m[2]), int(m[3]))
    m = re.search(r"(\d{1,2})(?:/| de | )([a-z]{3}|\d{1,2})", t)
    if m:
        month = MONTHS_ES.get(m[2][:3]) or (int(m[2]) if m[2].isdigit() else None)
        if month:
            d = date(today.year, month, int(m[1]))
            return d if d >= today - timedelta(days=1) else date(today.year + 1, month, int(m[1]))
    wd = DAYS_ES.get(t[:3])
    if wd is not None:
        return today + timedelta(days=(wd - today.weekday()) % 7)
    return today


def to_fixtures(payload: dict, competition: str, known_teams: list[str], today: date) -> tuple[pd.DataFrame, list[str]]:
    rows, skipped = [], []
    for m in payload.get("matches", []):
        h, a = map_team(m.get("home_team", ""), known_teams), map_team(m.get("away_team", ""), known_teams)
        if not h or not a:
            skipped.append(f"{m.get('home_team')} vs {m.get('away_team')}")
            continue
        row = {"date": parse_kickoff(m.get("kickoff") or m.get("date") or "", today).isoformat(),
               "competition": competition, "home_team": h, "away_team": a,
               "odds_home": m.get("odds_home") or None, "odds_draw": m.get("odds_draw") or None,
               "odds_away": m.get("odds_away") or None}
        over = m.get("odds_over") or m.get("odds_over25")
        under = m.get("odds_under") or m.get("odds_under25")
        if float(m.get("total_line") or 2.5) == 2.5 and over and under:
            row["odds_over25"], row["odds_under25"] = over, under
        rows.append(row)
    return pd.DataFrame(rows), skipped


def main() -> None:
    p = argparse.ArgumentParser(description="Convierte el JSON de Rushbet (TinyFish) en fixtures para el bot.")
    p.add_argument("json_file")
    p.add_argument("--competition", required=True, help="Código Div de football-data (E0, SP1, ...)")
    p.add_argument("--history", nargs="+", required=True, help="CSV(s) con los nombres de equipo de referencia")
    p.add_argument("--out", required=True)
    p.add_argument("--today", help="Fecha de referencia YYYY-MM-DD (default: hoy)")
    args = p.parse_args()

    hist = load_matches(args.history)
    known = sorted(set(hist["home_team"]) | set(hist["away_team"]))
    today = datetime.strptime(args.today, "%Y-%m-%d").date() if args.today else date.today()
    payload = json.loads(open(args.json_file, encoding="utf-8").read())
    df, skipped = to_fixtures(payload, args.competition, known, today)
    df.to_csv(args.out, index=False)
    print(f"{len(df)} partidos escritos en {args.out}")
    for s in skipped:
        print(f"  sin mapear (añádelo a ALIASES): {s}")


if __name__ == "__main__":
    main()
