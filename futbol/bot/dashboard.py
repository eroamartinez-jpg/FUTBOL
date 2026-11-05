"""Genera un tablero HTML autocontenido del bot (paper trading + backtests).

Uso:
    python -m futbol.bot.dashboard            # escribe web/bot.html
    python -m http.server 8000 -d web         # y abrir http://localhost:8000/bot.html
"""
from __future__ import annotations

import argparse
import html
import json
from pathlib import Path

from futbol.bot.ledger import Ledger
from futbol.config import ROOT_DIR

BACKTESTS = [
    ("pinnacle_default.json", "Pinnacle · estrategia por defecto"),
    ("bet365_default.json", "Bet365 · estrategia por defecto"),
    ("pinnacle_conservadora.json", "Pinnacle · conservadora (solo 1X2)"),
]
MARKET_LABEL = {"1x2": "1X2", "ou2.5": "Goles 2.5", "ou1.5": "Goles 1.5", "ou3.5": "Goles 3.5", "btts": "Ambos marcan"}
SEL_LABEL = {"home": "Local", "draw": "Empate", "away": "Visitante", "over": "Más de", "under": "Menos de",
             "yes": "Sí", "no": "No"}


def _pct(x, signed=False):
    if x is None:
        return "–"
    return f"{x * 100:+.1f}%" if signed else f"{x * 100:.1f}%"


def _money(x, signed=False):
    return f"{x:+,.2f}" if signed else f"{x:,.2f}"


def _curve(ledger: Ledger) -> list[float]:
    pts, bank = [ledger.initial_bankroll], ledger.initial_bankroll
    for b in ledger.bets:
        if b["status"] in ("won", "lost"):
            bank += b["pnl"]
            pts.append(bank)
    return pts


def _sparkline(points: list[float], width=640, height=180, base=None) -> str:
    if len(points) < 2:
        return ""
    lo, hi = min(points + [base or points[0]]), max(points + [base or points[0]])
    span = (hi - lo) or 1.0
    pad = 8

    def xy(i, v):
        x = pad + i * (width - 2 * pad) / (len(points) - 1)
        y = pad + (hi - v) * (height - 2 * pad) / span
        return f"{x:.1f},{y:.1f}"

    line = " ".join(xy(i, v) for i, v in enumerate(points))
    area = f"{pad},{height - pad} {line} {width - pad},{height - pad}"
    base_y = pad + (hi - (base if base is not None else points[0])) * (height - 2 * pad) / span
    cls = "up" if points[-1] >= points[0] else "down"
    return (f'<svg class="spark {cls}" viewBox="0 0 {width} {height}" preserveAspectRatio="none" role="img" '
            f'aria-label="Evolución de la banca">'
            f'<line class="base" x1="{pad}" x2="{width - pad}" y1="{base_y:.1f}" y2="{base_y:.1f}"/>'
            f'<polygon class="area" points="{area}"/><polyline class="line" points="{line}"/></svg>')


def _kpi(label, value, sub="", tone=""):
    return (f'<div class="kpi"><div class="kpi-label">{label}</div>'
            f'<div class="kpi-value {tone}">{value}</div><div class="kpi-sub">{sub}</div></div>')


def _bet_rows(bets: list[dict]) -> str:
    rows = []
    for b in sorted(bets, key=lambda b: (b["date"], b["bet_id"])):
        status = {"won": ("Ganada", "pos"), "lost": ("Perdida", "neg"), "open": ("Abierta", "muted")}[b["status"]]
        pick = f'{MARKET_LABEL.get(b["market"], b["market"])} · {SEL_LABEL.get(b["selection"], b["selection"])}'
        fair = _pct(b.get("fair_prob")) if b.get("fair_prob") is not None else "–"
        pnl = "" if b["status"] == "open" else _money(b["pnl"], signed=True)
        score = b.get("score", "")
        rows.append(
            f'<tr><td class="nowrap">{b["date"]}</td>'
            f'<td><div class="match">{html.escape(b["home_team"])} <span class="vs">vs</span> {html.escape(b["away_team"])}</div>'
            f'<div class="pick">{pick}</div></td>'
            f'<td class="num">{b["odds"]:.2f}</td>'
            f'<td class="num">{_pct(b["model_prob"])}<span class="muted"> / {fair}</span></td>'
            f'<td class="num">{_pct(b["edge"], signed=True)}</td>'
            f'<td class="num">{b["stake"]:.2f}</td>'
            f'<td><span class="chip {status[1]}">{status[0]}</span>{f" <span class=muted>{score}</span>" if score else ""}</td>'
            f'<td class="num {status[1]}">{pnl}</td></tr>')
    return "\n".join(rows)


def build(ledger_path: Path, backtest_dir: Path, history_md: Path | None) -> str:
    live = Ledger.load(ledger_path)
    s = live.summary()
    lost = s["bets"] - s["won"]
    tone = "pos" if s["pnl"] >= 0 else "neg"
    kpis = "".join([
        _kpi("Banca simulada", _money(s["bankroll"]), f"inicial {_money(live.initial_bankroll)}", tone),
        _kpi("Ganancia / pérdida", _money(s["pnl"], signed=True), f"ROI {_pct(s['roi_bankroll'], True)}", tone),
        _kpi("Yield", _pct(s["yield"], True), f"sobre {_money(s['staked'])} apostado", tone),
        _kpi("Apuestas", f'{s["won"]}–{lost}', f"ganadas–perdidas · {s['open']} abiertas"),
    ])

    bt_cards = []
    for fname, label in BACKTESTS:
        path = backtest_dir / fname
        if not path.exists():
            continue
        bt = Ledger.load(path)
        bs = bt.summary()
        t = "pos" if bs["pnl"] >= 0 else "neg"
        bt_cards.append(
            f'<article class="card bt"><header><h3>{label}</h3>'
            f'<span class="big {t}">{_pct(bs["yield"], True)}</span></header>'
            f'{_sparkline(_curve(bt), base=bt.initial_bankroll)}'
            f'<dl><div><dt>Apuestas</dt><dd>{bs["bets"]:,}</dd></div>'
            f'<div><dt>Banca final</dt><dd class="{t}">{_money(bs["bankroll"])}</dd></div>'
            f'<div><dt>Peor caída</dt><dd>{_pct(bs["max_drawdown"])}</dd></div>'
            f'<div><dt>CLV medio</dt><dd>{_pct(bs["avg_clv"], True)}</dd></div></dl></article>')

    history = ""
    if history_md and history_md.exists():
        history = html.escape(history_md.read_text())

    return TEMPLATE.format(
        kpis=kpis, curve=_sparkline(_curve(live), base=live.initial_bankroll) or
        '<p class="muted">Aún no hay apuestas liquidadas.</p>',
        rows=_bet_rows(live.bets), backtests="\n".join(bt_cards), history=history,
        n_bets=len(live.bets))


TEMPLATE = """<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Bot de apuestas</title>
<style>
:root {{
  --bg:#f6f5f1; --surface:#fff; --text:#1d1d1b; --muted:#6b6a65; --line:#e4e2db;
  --pos:#1f7a4d; --pos-bg:#e3f2e9; --neg:#b3392f; --neg-bg:#f8e4e1; --accent:#2f5d8a; --warn-bg:#fff4dc; --warn:#7a5300;
}}
@media (prefers-color-scheme: dark) {{ :root:not([data-theme="light"]) {{
  --bg:#141413; --surface:#1e1e1c; --text:#ecebe6; --muted:#9c9a93; --line:#33322e;
  --pos:#5cc48d; --pos-bg:#173326; --neg:#ef7b70; --neg-bg:#3a1d1a; --accent:#7fb0e0; --warn-bg:#33290f; --warn:#f0c867;
}} }}
:root[data-theme="dark"] {{
  --bg:#141413; --surface:#1e1e1c; --text:#ecebe6; --muted:#9c9a93; --line:#33322e;
  --pos:#5cc48d; --pos-bg:#173326; --neg:#ef7b70; --neg-bg:#3a1d1a; --accent:#7fb0e0; --warn-bg:#33290f; --warn:#f0c867;
}}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--bg); color:var(--text);
  font:15px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif; }}
main {{ max-width:1080px; margin:0 auto; padding:28px 16px 64px; }}
h1 {{ font-size:26px; margin:0; letter-spacing:-.01em; }}
h2 {{ font-size:17px; margin:40px 0 12px; }}
h3 {{ font-size:14px; margin:0; font-weight:600; }}
.top {{ display:flex; flex-wrap:wrap; gap:10px; align-items:center; justify-content:space-between; }}
.badge {{ font-size:12px; font-weight:600; padding:4px 10px; border-radius:99px; background:var(--warn-bg); color:var(--warn); }}
.lede {{ color:var(--muted); margin:6px 0 0; }}
.kpis {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(200px,1fr)); gap:12px; margin-top:24px; }}
.kpi, .card {{ background:var(--surface); border:1px solid var(--line); border-radius:12px; padding:16px; }}
.kpi-label {{ font-size:12px; color:var(--muted); text-transform:uppercase; letter-spacing:.04em; }}
.kpi-value {{ font-size:28px; font-weight:650; font-variant-numeric:tabular-nums; margin-top:4px; }}
.kpi-sub {{ font-size:13px; color:var(--muted); }}
.pos {{ color:var(--pos); }} .neg {{ color:var(--neg); }} .muted {{ color:var(--muted); }}
.spark {{ width:100%; height:160px; display:block; margin:8px 0; }}
.spark .line {{ fill:none; stroke-width:2; vector-effect:non-scaling-stroke; }}
.spark .base {{ stroke:var(--line); stroke-dasharray:4 4; vector-effect:non-scaling-stroke; }}
.spark.up .line {{ stroke:var(--pos); }} .spark.up .area {{ fill:var(--pos-bg); }}
.spark.down .line {{ stroke:var(--neg); }} .spark.down .area {{ fill:var(--neg-bg); }}
.table-wrap {{ overflow-x:auto; background:var(--surface); border:1px solid var(--line); border-radius:12px; }}
table {{ width:100%; border-collapse:collapse; min-width:720px; }}
th, td {{ padding:10px 12px; border-bottom:1px solid var(--line); text-align:left; vertical-align:top; }}
th {{ font-size:12px; color:var(--muted); font-weight:600; text-transform:uppercase; letter-spacing:.04em; }}
tr:last-child td {{ border-bottom:0; }}
.num {{ text-align:right; font-variant-numeric:tabular-nums; white-space:nowrap; }}
.nowrap {{ white-space:nowrap; }}
.match {{ font-weight:600; }} .vs {{ color:var(--muted); font-weight:400; }}
.pick {{ font-size:13px; color:var(--muted); }}
.chip {{ font-size:12px; font-weight:600; padding:2px 8px; border-radius:99px; white-space:nowrap; }}
.chip.pos {{ background:var(--pos-bg); }} .chip.neg {{ background:var(--neg-bg); }}
.chip.muted {{ background:var(--bg); border:1px solid var(--line); }}
.bts {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(300px,1fr)); gap:12px; }}
.bt header {{ display:flex; justify-content:space-between; align-items:baseline; gap:8px; }}
.big {{ font-size:22px; font-weight:650; font-variant-numeric:tabular-nums; }}
dl {{ display:grid; grid-template-columns:1fr 1fr; gap:6px 16px; margin:0; font-size:13px; }}
dl div {{ display:flex; justify-content:space-between; }} dt {{ color:var(--muted); }}
dd {{ margin:0; font-variant-numeric:tabular-nums; }}
.warn {{ background:var(--warn-bg); color:var(--warn); border-radius:12px; padding:14px 16px; margin-top:16px; }}
pre {{ white-space:pre-wrap; font:13px/1.55 ui-monospace,Menlo,monospace; margin:0; }}
footer {{ margin-top:40px; font-size:13px; color:var(--muted); }}
</style></head>
<body><main>
<div class="top"><h1>Bot de apuestas de valor</h1><span class="badge">Simulado · sin dinero real</span></div>
<p class="lede">Modelo Dixon-Coles contra las cuotas de Rushbet (Premier League), con stakes Kelly fraccional y banca ficticia.</p>

<section class="kpis">{kpis}</section>

<h2>Evolución de la banca en vivo</h2>
<div class="card">{curve}</div>

<h2>Apuestas ({n_bets})</h2>
<div class="table-wrap"><table>
<thead><tr><th>Fecha</th><th>Partido y apuesta</th><th class="num">Cuota</th>
<th class="num">Modelo / mercado</th><th class="num">Edge</th><th class="num">Stake</th><th>Estado</th><th class="num">P&amp;L</th></tr></thead>
<tbody>{rows}</tbody></table></div>

<h2>Backtest con datos reales (2023/24 – 2025/26)</h2>
<div class="bts">{backtests}</div>
<div class="warn"><strong>Ojo:</strong> en el backtest de ~2 300 partidos de Premier League y La Liga el modelo pierde
contra el mercado en las tres variantes y su CLV es ≈0 o negativo. Una buena semana en vivo es varianza, no prueba de ventaja.</div>

<h2>Historial semanal</h2>
<div class="card"><pre>{history}</pre></div>

<footer>Cuotas leídas del sportsbook público de Rushbet con TinyFish (sin iniciar sesión ni apostar).
Resultados y cuotas históricas: football-data.co.uk. Generado con <code>python -m futbol.bot.dashboard</code>.</footer>
</main></body></html>
"""


def main() -> None:
    p = argparse.ArgumentParser(description="Tablero HTML del bot de apuestas.")
    p.add_argument("--ledger", default=str(ROOT_DIR / "data/rushbet/ledger_rushbet.json"))
    p.add_argument("--backtests", default=str(ROOT_DIR / "data/backtest"))
    p.add_argument("--history", default=str(ROOT_DIR / "data/rushbet/HISTORIAL.md"))
    p.add_argument("--out", default=str(ROOT_DIR / "web/bot.html"))
    args = p.parse_args()
    out = Path(args.out)
    out.write_text(build(Path(args.ledger), Path(args.backtests), Path(args.history)), encoding="utf-8")
    print(f"Tablero escrito en {out}")


if __name__ == "__main__":
    main()
