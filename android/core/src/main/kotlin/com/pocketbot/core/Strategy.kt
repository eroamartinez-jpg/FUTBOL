package com.pocketbot.core

import kotlin.math.abs
import kotlin.math.round
import kotlin.math.sign

enum class Direction { CALL, PUT, NEUTRAL }

data class Signal(
    val asset: String,
    val direction: Direction,
    val confidence: Double,  // 0-100
    val score: Double,       // -1..1
    val adx: Double,
    val rsi: Double,
    val lastClose: Double,
    val lastTime: Long,
)

/**
 * Estrategia de confluencia (misma que pocket_bot/strategy.py): cada
 * indicador vota CALL (+) o PUT (-), el puntaje se normaliza a [-1, 1] y la
 * confianza baja cuando el ADX indica mercado lateral.
 */
object Strategy {
    const val WARMUP = 60

    private val WEIGHTS = linkedMapOf(
        "ema_cross" to 1.5, "ema_trend" to 1.0, "macd" to 1.0, "macd_slope" to 0.5,
        "rsi" to 1.0, "stoch" to 0.5, "bollinger" to 0.5,
    )
    private val TOTAL = WEIGHTS.values.sum()

    class Frame(val score: DoubleArray, val confidence: DoubleArray, val direction: Array<Direction>,
                val adx: DoubleArray, val rsi: DoubleArray)

    private fun sgn(x: Double) = if (x.isNaN()) 0.0 else sign(x)

    fun scoreFrame(c: List<Candle>): Frame {
        val n = c.size
        val close = DoubleArray(n) { c[it].close }
        val e9 = Indicators.ema(close, 9)
        val e21 = Indicators.ema(close, 21)
        val e50 = Indicators.ema(close, 50)
        val m = Indicators.macd(close)
        val r = Indicators.rsi(close)
        val st = Indicators.stochastic(c)
        val bb = Indicators.bollinger(close)
        val a = Indicators.adx(c)

        val score = DoubleArray(n)
        val conf = DoubleArray(n)
        val dir = Array(n) { Direction.NEUTRAL }
        for (i in 0 until n) {
            val rsiVote = when {
                r[i] > 50 && r[i] < 70 -> 1.0
                r[i] < 50 && r[i] > 30 -> -1.0
                else -> 0.0
            }
            val votes = mapOf(
                "ema_cross" to sgn(e9[i] - e21[i]),
                "ema_trend" to sgn(close[i] - e50[i]),
                "macd" to sgn(m.hist[i]),
                "macd_slope" to if (i == 0) 0.0 else sgn(m.hist[i] - m.hist[i - 1]),
                "rsi" to rsiVote,
                "stoch" to sgn(st.k[i] - st.d[i]),
                "bollinger" to sgn(close[i] - bb.mid[i]),
            )
            val s = WEIGHTS.entries.sumOf { (k, w) -> votes.getValue(k) * w } / TOTAL
            score[i] = s
            if (i < WARMUP) continue
            val adxFactor = (0.5 + (a[i] - 15) / 30).coerceIn(0.5, 1.0)
            conf[i] = round(abs(s) * adxFactor * 1000) / 10
            dir[i] = when { s > 0 -> Direction.CALL; s < 0 -> Direction.PUT; else -> Direction.NEUTRAL }
        }
        return Frame(score, conf, dir, a, r)
    }

    fun latest(asset: String, c: List<Candle>): Signal {
        val f = scoreFrame(c)
        val i = c.size - 1
        return Signal(asset, f.direction[i], f.confidence[i], f.score[i], f.adx[i], f.rsi[i],
            c[i].close, c[i].time)
    }
}
