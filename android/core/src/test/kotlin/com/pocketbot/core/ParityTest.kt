package com.pocketbot.core

import org.json.JSONObject
import kotlin.math.abs
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/** Comprueba que el núcleo Kotlin da los mismos resultados que pocket_bot (Python). */
class ParityTest {
    private val fixture = JSONObject(javaClass.getResource("/parity.json")!!.readText())

    private fun candles(asset: String): List<Candle> {
        val arr = fixture.getJSONObject(asset).getJSONArray("candles")
        return (0 until arr.length()).map {
            val r = arr.getJSONArray(it)
            Candle(r.getLong(0), r.getDouble(1), r.getDouble(2), r.getDouble(3), r.getDouble(4))
        }
    }

    @Test
    fun scoreConfidenceAndDirectionMatchPython() {
        for (asset in fixture.keySet()) {
            val exp = fixture.getJSONObject(asset)
            val f = Strategy.scoreFrame(candles(asset))
            val score = exp.getJSONArray("score")
            val conf = exp.getJSONArray("confidence")
            val dir = exp.getJSONArray("direction")
            for (i in 0 until score.length()) {
                assertTrue(abs(score.getDouble(i) - f.score[i]) < 1e-9, "$asset score[$i]")
                assertEquals(conf.getDouble(i), f.confidence[i], 1e-9, "$asset confidence[$i]")
                assertEquals(dir.getString(i), f.direction[i].name, "$asset direction[$i]")
            }
        }
    }

    @Test
    fun backtestMatchesPython() {
        for (asset in fixture.keySet()) {
            val bts = fixture.getJSONObject(asset).getJSONArray("backtests")
            for (i in 0 until bts.length()) {
                val b = bts.getJSONObject(i)
                val r = Backtest.run(candles(asset), b.getDouble("payout"), b.getInt("expiry"),
                    b.getDouble("minConf"), b.getInt("delay"))
                assertEquals(b.getInt("trades"), r.trades, "$asset trades $i")
                assertEquals(b.getInt("wins"), r.wins, "$asset wins $i")
                assertEquals(b.getDouble("expectancy"), r.expectancy, 1e-12)
            }
        }
    }
}
