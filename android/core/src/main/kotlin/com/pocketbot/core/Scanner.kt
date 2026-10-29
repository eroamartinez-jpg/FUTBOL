package com.pocketbot.core

data class Opportunity(
    val signal: Signal,
    val payout: Int,
    val stats: BacktestResult,
    val window: EntryWindow,
    val recommended: Boolean,
)

data class ScanConfig(
    val periodS: Int = 60,
    val expiryCandles: Int = 1,
    val minPayout: Int = 80,
    val minConfidence: Double = 60.0,
    val minTrades: Int = 20,
    val count: Int = 500,
)

/** Analiza un activo ya descargado. Devuelve null si hay pocas velas. */
fun analyze(asset: String, payout: Int, candles: List<Candle>, cfg: ScanConfig, nowS: Long): Opportunity? {
    if (candles.size < Strategy.WARMUP + 10) return null
    val window = Timing.window(nowS, cfg.periodS, cfg.expiryCandles)
    val delay = Timing.delayCandles(candles.last().time, cfg.periodS, window.entry)
    val stats = Backtest.run(candles, payout / 100.0, cfg.expiryCandles, cfg.minConfidence, delay)
    val sig = Strategy.latest(asset, candles)
    val rec = sig.direction != Direction.NEUTRAL && sig.confidence >= cfg.minConfidence &&
        stats.trades >= cfg.minTrades && stats.edge
    return Opportunity(sig, payout, stats, window, rec)
}

/** Orden de la lista: recomendadas primero (por expectativa), luego por confianza. */
val opportunityOrder: Comparator<Opportunity> = compareByDescending<Opportunity> { it.recommended }
    .thenByDescending { if (it.recommended) it.stats.expectancy else 0.0 }
    .thenByDescending { it.signal.confidence }
