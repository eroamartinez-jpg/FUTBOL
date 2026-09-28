"""Convierte el TEAM_DB del artifact "Predictor de Fútbol" (banco de equipos
de temporada en curso, mantenido por otra rutina semanal del usuario) al
`web/live_leagues.json` que consume la página de FUTBOL como "Track B" (en
vivo, sin calibración por backtest).

El artifact fuente es JS (objeto literal, no JSON estricto: claves con
comillas simples, sin comillas en nombres de propiedad), así que se delega
la extracción a `node` en vez de reimplementar un parser de JS en Python.

Uso:
    # 1. Con el Artifact tool: action "read" sobre la URL del otro artifact,
    #    que guarda el HTML completo en un archivo local (el mensaje de
    #    resultado indica la ruta exacta).
    # 2. python -m futbol.import_live_leagues /ruta/al/artifact-leido.html
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from futbol.config import ROOT_DIR

OUTPUT_PATH = ROOT_DIR / "web" / "live_leagues.json"

_NODE_SCRIPT = r"""
const fs = require('fs');
const src = fs.readFileSync(process.argv[1], 'utf-8');

function extractBalanced(text, startMarker, openChar, closeChar) {
  const idx = text.indexOf(startMarker);
  if (idx === -1) throw new Error('marker not found: ' + startMarker);
  const braceStart = text.indexOf(openChar, idx);
  let depth = 0, i = braceStart;
  for (; i < text.length; i++) {
    if (text[i] === openChar) depth++;
    else if (text[i] === closeChar) { depth--; if (depth === 0) { i++; break; } }
  }
  return text.slice(braceStart, i);
}

const LEAGUES = eval(extractBalanced(src, 'var LEAGUES = ', '[', ']'));
const TEAM_DB = eval('(' + extractBalanced(src, 'var TEAM_DB = ', '{', '}') + ')');
const updatedMatch = src.match(/var TEAM_DB_UPDATED = '([^']*)'/);
const rhoMatch = src.match(/var RHO = (-?[\d.]+)/);
const hfaMatch = src.match(/getElementById\('hfa'\)\.value = '([\d.]+)'/);
const maxGMatch = src.match(/var MAXG = (\d+)/);

const priorAvg = {}, groupOf = {};
LEAGUES.forEach(g => g.items.forEach(it => { priorAvg[it.name] = it.avg; groupOf[it.name] = g.group; }));

const agg = {};
for (const t of Object.values(TEAM_DB)) {
  const a = agg[t.league] || (agg[t.league] = {gf: 0, pj: 0});
  a.gf += t.gf; a.pj += t.pj;
}

const leagues = Object.keys(priorAvg).map(name => {
  const a = agg[name] || {gf: 0, pj: 0};
  const empPerTeam = a.pj >= 20 ? a.gf / a.pj : null;
  return {
    name, group: groupOf[name],
    prior_avg_goals: priorAvg[name],
    league_avg_per_team: empPerTeam !== null ? empPerTeam : priorAvg[name] / 2,
    n_teams_seen: Object.values(TEAM_DB).filter(t => t.league === name).length,
    n_matches_seen_approx: a.pj,
  };
});

const teams = {};
for (const [name, t] of Object.entries(TEAM_DB)) {
  teams[name] = {
    league: t.league, pj: t.pj, pg: t.pg, pe: t.pe, pp: t.pp, gf: t.gf, gc: t.gc,
    cards: t.cards, shots: t.shots, sot: t.sot, corners: t.corners,
    players: t.players,
  };
}

console.log(JSON.stringify({
  updated: updatedMatch ? updatedMatch[1] : null,
  rho: rhoMatch ? parseFloat(rhoMatch[1]) : -0.13,
  home_advantage: hfaMatch ? parseFloat(hfaMatch[1]) : 1.2,
  max_goals: maxGMatch ? parseInt(maxGMatch[1], 10) : 6,
  leagues, teams,
}));
"""


def main() -> None:
    if len(sys.argv) != 2:
        print("Uso: python -m futbol.import_live_leagues /ruta/al/artifact-leido.html", file=sys.stderr)
        sys.exit(1)

    src_path = Path(sys.argv[1])
    if not src_path.exists():
        print(f"No existe: {src_path}", file=sys.stderr)
        sys.exit(1)

    result = subprocess.run(
        ["node", "-e", _NODE_SCRIPT, str(src_path)],
        capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        print(result.stderr, file=sys.stderr)
        sys.exit(1)

    data = json.loads(result.stdout)
    OUTPUT_PATH.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    print(f"Guardado {OUTPUT_PATH}: {len(data['leagues'])} ligas, {len(data['teams'])} equipos, "
          f"actualizado: {data['updated']}")


if __name__ == "__main__":
    main()
