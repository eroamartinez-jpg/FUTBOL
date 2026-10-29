package com.pocketbot.core

data class BacktestResult(
    val trades: Int,
    val wins: Int,
    val winRate: Double,     // 0-1
    val breakeven: Double,   // 0-1
    val expectancy: Double,  // ganancia media por unidad apostada
) {
    val edge: Boolean get() = trades > 0 && winRate > breakeven
}

/** Backtest walk-forward, igual que pocket_bot/backtest.py. */
object Backtest {
    /** Con payout p (0.92 = 92 %) se gana p y se pierde 1: equilibrio = 1/(1+p). */
    fun breakeven(payout: Double) = 1.0 / (1.0 + payout)

    /**
     * Señal al cierre de la vela i -> entra en close[i + delay] y sale en
     * close[i + delay + expiry]. Los empates (precio igual) no cuentan.
     */
    fun run(c: List<Candle>, payout: Double, expiryCandles: Int = 1, minConfidence: Double = 60.0,
            delayCandles: Int = 0): BacktestResult {
        val f = Strategy.scoreFrame(c)
        var wins = 0
        var trades = 0
        for (i in 0 until maxOf(c.size - expiryCandles - delayCandles, 0)) {
            val d = f.direction[i]
            if (d == Direction.NEUTRAL || f.confidence[i] < minConfidence) continue
            val move = (c[i + delayCandles + expiryCandles].close - c[i + delayCandles].close) *
                (if (d == Direction.CALL) 1 else -1)
            if (move == 0.0) continue
            trades++
            if (move > 0) wins++
        }
        val wr = if (trades > 0) wins.toDouble() / trades else 0.0
        val exp = if (trades > 0) wr * payout - (1 - wr) else 0.0
        return BacktestResult(trades, wins, wr, breakeven(payout), exp)
    }
}
