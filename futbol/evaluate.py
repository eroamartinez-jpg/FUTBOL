"""CLI de backtest: valida empíricamente que las probabilidades calibradas
del modelo reflejan la frecuencia real de acierto (soporte del requisito de
confianza 75%-100%).

Uso:
    python -m futbol.evaluate
"""
from __future__ import annotations

from futbol.config import CONFIDENCE_MIN
from futbol.models.calibration import evaluate_calibration, fit_calibrators, honest_calibration_report, \
    walk_forward_backtest
from futbol.pipeline import load_processed_data


def main() -> None:
    matches_df, _ = load_processed_data()
    print(f"Partidos en el dataset: {len(matches_df)}")
    print("Ejecutando backtest walk-forward (reentrenando solo con partidos previos)...\n")

    backtest_df = walk_forward_backtest(matches_df)
    calibrators = fit_calibrators(backtest_df)

    print("== Calibración en todo el histórico (referencia, no es hold-out estricto) ==")
    for family, stats in evaluate_calibration(backtest_df, calibrators).items():
        print(f"[{family}] n={stats['n']}  Brier crudo={stats['brier_raw']:.4f}  "
              f"Brier calibrado={stats['brier_calibrated']:.4f}")
        if stats["hit_rate_high_confidence"] is not None:
            print(f"  Pronósticos con probabilidad calibrada >= {CONFIDENCE_MIN:.0%}: "
                  f"{stats['n_high_confidence']}  ->  acierto real {stats['hit_rate_high_confidence']:.1%}")
        else:
            print("  (sin pronósticos que superen el umbral de confianza)")

    print("\n== Validación honesta (calibrador ajustado solo con el primer 70% de partidos, "
          "medido en el 30% final nunca visto) ==")
    for family, stats in honest_calibration_report(backtest_df).items():
        print(f"[{family}] n_test={stats['n_test']}  Brier crudo={stats['brier_raw']:.4f}  "
              f"Brier calibrado={stats['brier_calibrated']:.4f}")
        if stats["hit_rate_high_confidence"] is not None:
            print(f"  Pronósticos con probabilidad calibrada >= {CONFIDENCE_MIN:.0%}: "
                  f"{stats['n_high_confidence']}  ->  acierto real {stats['hit_rate_high_confidence']:.1%}")
        else:
            print("  (sin pronósticos que superen el umbral de confianza)")


if __name__ == "__main__":
    main()
