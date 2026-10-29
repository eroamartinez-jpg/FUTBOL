package com.pocketbot.core

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertIs
import kotlin.test.assertNull
import kotlin.test.assertTrue

class CoreTest {
    @Test
    fun entryWindowAlignsToNextCandle() {
        val now = 1_767_268_830L // 12:00:30 UTC
        val w = Timing.window(now, 60, expiryCandles = 2)
        assertEquals(now + 30, w.entry)
        assertEquals(w.entry + 120, w.expiry)
        assertEquals(30, w.secondsLeft)
        // Con menos de 5 s de margen salta a la vela siguiente.
        assertEquals(now + 30 + 60, Timing.window(now + 27, 60).entry)
        assertEquals(1, Timing.delayCandles(now - 30 - 60, 60, w.entry))
    }

    @Test
    fun breakevenRate() {
        assertEquals(0.5, Backtest.breakeven(1.0), 1e-12)
    }

    @Test
    fun parsesDemoSsidInAllFormats() {
        val json = """{"session":"abc","isDemo":1,"uid":123,"platform":2}"""
        val full = """42["auth",$json]"""
        for (input in listOf(full, json, "\"" + full.replace("\"", "\\\"") + "\"")) {
            val s = Protocol.parseSsid(input)
            assertTrue(s.isDemo)
            assertEquals(full, s.raw)
            assertEquals(Protocol.DEMO_URLS, s.urls)
        }
    }

    @Test
    fun parsesRealSsidUserAgent() {
        val session = "a:4:{s:10:\\\"session_id\\\";s:3:\\\"xyz\\\";s:10:\\\"ip_address\\\";s:7:\\\"1.2.3.4\\\";" +
            "s:10:\\\"user_agent\\\";s:11:\\\"Mozilla/5.0\\\";s:13:\\\"last_activity\\\";i:1;}abcdef"
        val s = Protocol.parseSsid("""42["auth",{"session":"$session","isDemo":0,"uid":1,"platform":2}]""")
        assertFalse(s.isDemo)
        assertEquals("Mozilla/5.0", s.userAgent)
        assertEquals(Protocol.REAL_URLS, s.urls)
    }

    @Test
    fun handshakeAndBinaryEvents() {
        val ssid = Protocol.parseSsid("""{"session":"abc","isDemo":1,"uid":1}""")
        val session = Protocol.Session(ssid)
        assertEquals(listOf(Protocol.Action.Send("40")), session.onText("""0{"sid":"x","pingInterval":25000}"""))
        assertEquals(listOf(Protocol.Action.Send(ssid.raw)), session.onText("""40{"sid":"y"}"""))
        assertEquals(listOf(Protocol.Action.Send("3")), session.onText("2"))

        assertTrue(session.onText("""451-["successauth",{"_placeholder":true,"num":0}]""").isEmpty())
        val auth = session.onBinary("""{"id":"1"}""".toByteArray())
        assertTrue(session.authenticated)
        assertEquals(Protocol.AFTER_AUTH.size + 1, auth.size)

        session.onText("""451-["updateAssets",{"_placeholder":true,"num":0}]""")
        val assetsJson = """[[5,"AAPL_otc","Apple OTC","stock",2,92,60,30,3,1,170,0,[],1751906100,true,[{"time":60}],-1,60,1751906100],
            [6,"EURUSD","EUR/USD","currency",2,85,60,30,3,0,170,0,[],1751906100,false,[{"time":60}],-1,60,1751906100]]"""
        val ev = session.onBinary(assetsJson.toByteArray()).single()
        assertIs<Protocol.Action.Emit>(ev)
        val assets = Protocol.parseAssets(ev.event.payload!!)
        assertEquals(listOf("AAPL_otc", "EURUSD"), assets.map { it.symbol })
        assertTrue(assets[0].isOtc && assets[0].isActive && assets[0].payout == 92)
        assertFalse(assets[1].isActive)

        assertIs<Protocol.Action.Rejected>(session.onText("41").single())
    }

    @Test
    fun parsesHistorySortedAndDeduplicated() {
        val h = Protocol.parseHistory("""{"asset":"EURUSD_otc","index":17,"period":60,"data":[
            {"symbol_id":1,"time":120,"open":1,"close":2,"high":3,"low":0.5},
            {"symbol_id":1,"time":60,"open":1,"close":1.5,"high":2,"low":0.5},
            {"symbol_id":1,"time":120,"open":1,"close":2,"high":3,"low":0.5}]}""")
        assertEquals(listOf(60L, 120L), h.candles.map { it.time })
        assertEquals(17L, h.index)
    }

    @Test
    fun analyzeNeedsEnoughCandles() {
        val few = (0 until 20).map { Candle(it * 60L, 1.0, 1.0, 1.0, 1.0) }
        assertNull(analyze("X", 90, few, ScanConfig(), 2000))
    }
}
