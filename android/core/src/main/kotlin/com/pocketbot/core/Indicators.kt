package com.pocketbot.core

import kotlin.math.abs
import kotlin.math.max
import kotlin.math.sqrt

/** Vela OHLC; [time] es la hora de apertura en segundos epoch (UTC). */
data class Candle(val time: Long, val open: Double, val high: Double, val low: Double, val close: Double)

/**
 * Indicadores técnicos causales (solo usan datos pasados). Equivalentes a los
 * de pocket_bot/indicators.py. Los valores aún no definidos son NaN.
 */
object Indicators {
    /** EMA con alpha = 2/(span+1), igual que pandas ewm(adjust=False). */
    fun ema(x: DoubleArray, span: Int): DoubleArray = ewm(x, 2.0 / (span + 1))

    /** Media exponencial con alpha dado; ignora NaN iniciales. */
    fun ewm(x: DoubleArray, alpha: Double): DoubleArray {
        val out = DoubleArray(x.size) { Double.NaN }
        var prev = Double.NaN
        for (i in x.indices) {
            val v = x[i]
            if (v.isNaN()) { out[i] = prev; continue }
            prev = if (prev.isNaN()) v else alpha * v + (1 - alpha) * prev
            out[i] = prev
        }
        return out
    }

    fun rsi(close: DoubleArray, period: Int = 14): DoubleArray {
        val n = close.size
        val gain = DoubleArray(n) { Double.NaN }
        val loss = DoubleArray(n) { Double.NaN }
        for (i in 1 until n) {
            val d = close[i] - close[i - 1]
            gain[i] = max(d, 0.0)
            loss[i] = max(-d, 0.0)
        }
        val g = ewm(gain, 1.0 / period)
        val l = ewm(loss, 1.0 / period)
        return DoubleArray(n) { i ->
            when {
                g[i].isNaN() -> Double.NaN
                l[i] == 0.0 -> if (g[i] > 0) 100.0 else 50.0
                else -> 100 - 100 / (1 + g[i] / l[i])
            }
        }
    }

    class Macd(val line: DoubleArray, val signal: DoubleArray, val hist: DoubleArray)

    fun macd(close: DoubleArray, fast: Int = 12, slow: Int = 26, signal: Int = 9): Macd {
        val f = ema(close, fast)
        val s = ema(close, slow)
        val line = DoubleArray(close.size) { f[it] - s[it] }
        val sig = ema(line, signal)
        return Macd(line, sig, DoubleArray(close.size) { line[it] - sig[it] })
    }

    fun sma(x: DoubleArray, period: Int): DoubleArray = DoubleArray(x.size) { i ->
        if (i < period - 1) Double.NaN else (i - period + 1..i).sumOf { x[it] } / period
    }

    /** Media de Bollinger (solo se usa la banda media en la estrategia). */
    class Bands(val mid: DoubleArray, val upper: DoubleArray, val lower: DoubleArray)

    fun bollinger(close: DoubleArray, period: Int = 20, k: Double = 2.0): Bands {
        val mid = sma(close, period)
        val std = DoubleArray(close.size) { i ->
            if (i < period - 1) Double.NaN
            else sqrt((i - period + 1..i).sumOf { (close[it] - mid[i]).let { d -> d * d } } / period)
        }
        return Bands(mid, DoubleArray(close.size) { mid[it] + k * std[it] },
            DoubleArray(close.size) { mid[it] - k * std[it] })
    }

    class Stoch(val k: DoubleArray, val d: DoubleArray)

    fun stochastic(c: List<Candle>, kPeriod: Int = 14, dPeriod: Int = 3): Stoch {
        val n = c.size
        val k = DoubleArray(n) { i ->
            if (i < kPeriod - 1) 50.0
            else {
                var lo = Double.MAX_VALUE; var hi = -Double.MAX_VALUE
                for (j in i - kPeriod + 1..i) { lo = minOf(lo, c[j].low); hi = maxOf(hi, c[j].high) }
                if (hi - lo == 0.0) 50.0 else 100 * (c[i].close - lo) / (hi - lo)
            }
        }
        return Stoch(k, sma(k, dPeriod))
    }

    fun adx(c: List<Candle>, period: Int = 14): DoubleArray {
        val n = c.size
        val plusDm = DoubleArray(n)
        val minusDm = DoubleArray(n)
        val tr = DoubleArray(n)
        for (i in 0 until n) {
            if (i == 0) { tr[i] = c[i].high - c[i].low; continue }
            val up = c[i].high - c[i - 1].high
            val down = c[i - 1].low - c[i].low
            plusDm[i] = if (up > down && up > 0) up else 0.0
            minusDm[i] = if (down > up && down > 0) down else 0.0
            tr[i] = maxOf(c[i].high - c[i].low, abs(c[i].high - c[i - 1].close), abs(c[i].low - c[i - 1].close))
        }
        val a = 1.0 / period
        val atr = ewm(tr, a)
        val pdi = ewm(plusDm, a)
        val mdi = ewm(minusDm, a)
        val dx = DoubleArray(n) { i ->
            if (atr[i] == 0.0) Double.NaN
            else {
                val p = 100 * pdi[i] / atr[i]
                val m = 100 * mdi[i] / atr[i]
                if (p + m == 0.0) Double.NaN else 100 * abs(p - m) / (p + m)
            }
        }
        return ewm(dx, a).map { if (it.isNaN()) 0.0 else it }.toDoubleArray()
    }
}
