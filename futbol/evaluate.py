"""CLI de backtest: valida empíricamente, competición por competición, que
las probabilidades calibradas del modelo reflejan la frecuencia real de
acierto (soporte del requisito de confianza 75%-100%).

Uso:
    python -m futbol.evaluate
    python -m futbol.evaluate --competition "La Liga 2015/16 (España)"
"""
from __future__ import annotations

import argparse

from futbol.config import CONFIDENCE_MIN
from futbol.models.calibration import evaluate_calibration, fit_calibrators, honest_calibration_report, \
    walk_forward_backtest
from futbol.pipeline import load_processed_data


def _print_family_stats(stats: dict, key_n: str) -> None:
    for family, s in stats.items():
        print(f"  [{family}] n={s[key_n]}  Brier crudo={s['brier_raw']:.4f}  "
              f"Brier calibrado={s['brier_calibrated']:.4f}")
        if s["hit_rate_high_confidence"] is not None:
            print(f"    Pronósticos con probabilidad calibrada >= {CONFIDENCE_MIN:.0%}: "
                  f"{s['n_high_confidence']}  ->  acierto real {s['hit_rate_high_confidence']:.1%}")
        else:
            print("    (sin pronósticos que superen el umbral de confianza)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Backtest de calibración del modelo.")
    parser.add_argument("--competition", help="Evalúa solo esta competición (por defecto: todas)")
    args = parser.parse_args()

    matches_df, _ = load_processed_data()
    print(f"Partidos totales en el dataset: {len(matches_df)}")
    print(f"Competiciones: {matches_df['competition'].nunique()}\n")

    competitions = [args.competition] if args.competition else sorted(matches_df["competition"].unique())

    for competition in competitions:
        comp_matches = matches_df[matches_df["competition"] == competition]
        print(f"=== {competition} ({len(comp_matches)} partidos) ===")

        backtest_df = walk_forward_backtest(comp_matches)
        if backtest_df.empty:
            print("  (muy pocos partidos para hacer un backtest walk-forward fiable)\n")
            continue

        calibrators = fit_calibrators(backtest_df)
        print(" Calibración en todo el histórico de la competición (referencia):")
        _print_family_stats(evaluate_calibration(backtest_df, calibrators), "n")

        honest = honest_calibration_report(backtest_df)
        if honest:
            print(" Validación honesta (calibrador con el primer 70%, medido en el 30% final nunca visto):")
            _print_family_stats(honest, "n_test")
        print()


if __name__ == "__main__":
    main()
