package com.pocketbot.core

/**
 * Hora de entrada: apertura de la próxima vela (con al menos [minLeadS]
 * segundos de margen para abrir la operación a mano). Todo en epoch UTC.
 */
data class EntryWindow(val entry: Long, val expiry: Long, val secondsLeft: Long, val durationS: Int)

object Timing {
    fun nextCandleOpen(nowS: Long, periodS: Int): Long = (nowS / periodS + 1) * periodS

    fun window(nowS: Long, periodS: Int, expiryCandles: Int = 1, minLeadS: Int = 5): EntryWindow {
        var entry = nextCandleOpen(nowS, periodS)
        if (entry - nowS < minLeadS) entry += periodS
        val duration = periodS * expiryCandles
        return EntryWindow(entry, entry + duration, entry - nowS, duration)
    }

    /** Velas completas entre el cierre de la última vela y la entrada. */
    fun delayCandles(lastCandleOpen: Long, periodS: Int, entry: Long): Int {
        val lastClose = lastCandleOpen + periodS
        return maxOf(Math.round((entry - lastClose).toDouble() / periodS).toInt(), 0)
    }
}
