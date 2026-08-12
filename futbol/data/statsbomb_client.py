"""Cliente de descarga (con cache local en disco) para StatsBomb Open Data.

Fuente: https://github.com/statsbomb/open-data (licencia de uso no comercial,
requiere atribución a StatsBomb). Solo se usan competiciones marcadas como
temporadas completas en futbol.config.COMPETITIONS.
"""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests
from tqdm import tqdm

from futbol.config import RAW_DIR, STATSBOMB_BASE_URL

_SESSION = requests.Session()


def _get_json(url: str, timeout: int = 30) -> object:
    resp = _SESSION.get(url, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def _cached_json(url: str, cache_path: Path, timeout: int = 30) -> object:
    if cache_path.exists():
        with open(cache_path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    data = _get_json(url, timeout=timeout)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    with open(cache_path, "w", encoding="utf-8") as fh:
        json.dump(data, fh)
    return data


def get_matches(competition_id: int, season_id: int) -> list[dict]:
    """Descarga (o lee de cache) la lista de partidos de una temporada."""
    url = f"{STATSBOMB_BASE_URL}/matches/{competition_id}/{season_id}.json"
    cache_path = RAW_DIR / "matches" / f"{competition_id}_{season_id}.json"
    return _cached_json(url, cache_path)


def get_events(match_id: int) -> list[dict]:
    """Descarga (o lee de cache) los eventos de un partido."""
    url = f"{STATSBOMB_BASE_URL}/events/{match_id}.json"
    cache_path = RAW_DIR / "events" / f"{match_id}.json"
    return _cached_json(url, cache_path)


def download_events_bulk(match_ids: list[int], max_workers: int = 12) -> dict[int, list[dict]]:
    """Descarga eventos de muchos partidos en paralelo, usando cache en disco."""
    results: dict[int, list[dict]] = {}

    def _load_cached(mid: int) -> tuple[int, list[dict]]:
        return mid, get_events(mid)

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_load_cached, mid): mid for mid in match_ids}
        for fut in tqdm(as_completed(futures), total=len(futures), desc="Descargando eventos"):
            mid, events = fut.result()
            results[mid] = events

    return results
