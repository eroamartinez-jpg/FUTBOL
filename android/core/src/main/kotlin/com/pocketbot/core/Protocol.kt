package com.pocketbot.core

import org.json.JSONArray
import org.json.JSONObject

/**
 * Protocolo de Pocket Option (Socket.IO v4 sobre WebSocket), sin red: aquí
 * solo se interpretan y construyen mensajes, para poder probarlo en la JVM.
 *
 * Flujo: servidor "0{sid}" -> cliente "40" -> servidor "40{...}" -> cliente
 * envía el SSID `42["auth",{...}]` -> servidor "successauth". Los eventos
 * con datos binarios llegan en dos tramas: texto `451-["evento",{"_placeholder":true,"num":0}]`
 * seguido de una trama binaria con el JSON.
 */
object Protocol {
    const val ORIGIN = "https://pocketoption.com"
    const val DEFAULT_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 " +
        "(KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36"

    val DEMO_URLS = listOf("wss://demo-api-eu.po.market/socket.io/?EIO=4&transport=websocket")
    val REAL_URLS = listOf(
        "wss://api-eu.po.market/socket.io/?EIO=4&transport=websocket",
        "wss://api-us-south.po.market/socket.io/?EIO=4&transport=websocket",
        "wss://api-msk.po.market/socket.io/?EIO=4&transport=websocket",
        "wss://api-spb.po.market/socket.io/?EIO=4&transport=websocket",
    )

    data class Ssid(val raw: String, val isDemo: Boolean, val userAgent: String?) {
        val urls get() = if (isDemo) DEMO_URLS else REAL_URLS
    }

    /** Acepta `42["auth",{...}]`, solo el `{...}` o el mensaje entre comillas. */
    fun parseSsid(input: String): Ssid {
        var s = input.trim()
        if (s.length >= 2 && s.startsWith("\"") && s.endsWith("\"")) {
            s = runCatching { JSONArray("[$s]").getString(0) }.getOrElse { s.substring(1, s.length - 1) }.trim()
        }
        val prefix = "42[\"auth\","
        val json = if (s.startsWith(prefix)) s.removePrefix(prefix).removeSuffix("]") else s
        val obj = try {
            JSONObject(json)
        } catch (e: Exception) {
            throw IllegalArgumentException("SSID no válido: debe ser el mensaje 42[\"auth\",{...}]")
        }
        require(obj.has("session")) { "SSID no válido: falta el campo session" }
        val demo = obj.optInt("isDemo", 0) == 1 || obj.optString("currentUrl").contains("demo")
        // En cuentas reales "session" es un array PHP serializado que incluye el
        // user agent con el que se inició sesión; el servidor lo compara.
        val ua = Regex("\"user_agent\";s:\\d+:\"(.*?)\";").find(obj.getString("session"))?.groupValues?.get(1)
        return Ssid(if (s.startsWith(prefix)) s else "$prefix$json]", demo, ua)
    }

    data class Asset(val symbol: String, val name: String, val type: String, val payout: Int,
                     val isOtc: Boolean, val isActive: Boolean)

    /** `updateAssets`: lista de arrays posicionales (id, símbolo, nombre, tipo, _, payout, ..., is_otc[9], ..., activo[14]). */
    fun parseAssets(payload: String): List<Asset> {
        val arr = JSONArray(payload)
        return (0 until arr.length()).mapNotNull { i ->
            val a = arr.optJSONArray(i) ?: return@mapNotNull null
            if (a.length() < 15) return@mapNotNull null
            Asset(
                symbol = a.optString(1), name = a.optString(2), type = a.optString(3),
                payout = a.optInt(5), isOtc = a.optInt(9) == 1, isActive = a.optBoolean(14),
            )
        }
    }

    data class History(val asset: String, val index: Long, val period: Int, val candles: List<Candle>)

    /** Respuesta de `loadHistoryPeriod`: {asset, index, period, data:[{time,open,close,high,low}]}. */
    fun parseHistory(payload: String): History {
        val o = JSONObject(payload)
        val data = o.optJSONArray("data") ?: JSONArray()
        val candles = (0 until data.length()).mapNotNull { i ->
            val c = data.optJSONObject(i) ?: return@mapNotNull null
            if (!c.has("open")) return@mapNotNull null
            Candle(c.getDouble("time").toLong(), c.getDouble("open"), c.getDouble("high"),
                c.getDouble("low"), c.getDouble("close"))
        }.distinctBy { it.time }.sortedBy { it.time }
        return History(o.optString("asset"), o.optLong("index"), o.optInt("period"), candles)
    }

    fun loadHistory(asset: String, period: Int, endTime: Long, offsetS: Long, index: Long): String {
        val o = JSONObject()
            .put("asset", asset).put("period", period).put("time", endTime)
            .put("index", index).put("offset", offsetS)
        return "42[\"loadHistoryPeriod\",$o]"
    }

    val AFTER_AUTH = listOf(
        "42[\"assets/load\"]", "42[\"indicator/load\"]", "42[\"favorite/load\"]",
        "42[\"price-alert/load\"]",
        "42[\"changeSymbol\",{\"asset\":\"EURUSD_otc\",\"period\":60}]",
        "42[\"subfor\",\"EURUSD_otc\"]",
    )
    const val PING = "42[\"ps\"]"

    /** Evento decodificado: nombre + JSON del payload (puede ser null). */
    data class Event(val name: String, val payload: String?)

    sealed interface Action {
        data class Send(val text: String) : Action
        data class Emit(val event: Event) : Action
        data class Rejected(val message: String) : Action
    }

    /**
     * Máquina de estados de una conexión. Recibe tramas de texto y binarias y
     * devuelve qué responder y qué eventos llegaron.
     */
    class Session(private val ssid: Ssid) {
        var authenticated = false
            private set
        private var pendingBinaryEvent: String? = null

        fun onText(text: String): List<Action> {
            when {
                text.startsWith("0{") -> return listOf(Action.Send("40"))
                text.startsWith("40") -> return listOf(Action.Send(ssid.raw))
                text == "2" -> return listOf(Action.Send("3"))
                text == "41" -> return listOf(Action.Rejected("El servidor rechazó la sesión (SSID caducado o inválido)"))
            }
            val start = text.indexOf('[')
            if (start < 0) return emptyList()
            val arr = runCatching { JSONArray(text.substring(start)) }.getOrNull() ?: return emptyList()
            val name = arr.optString(0)
            if (text.startsWith("451-")) {
                pendingBinaryEvent = name
                return emptyList()
            }
            val payload = if (arr.length() > 1) arr.get(1).toString() else null
            return handle(Event(name, payload))
        }

        fun onBinary(bytes: ByteArray): List<Action> {
            val name = pendingBinaryEvent ?: return onUnexpectedBinary(bytes)
            pendingBinaryEvent = null
            // Algunas tramas binarias llevan un byte de tipo (0x04) al inicio.
            val body = String(bytes, Charsets.UTF_8).trimStart('\u0004')
            return handle(Event(name, body))
        }

        /** Como en la librería de referencia: un binario con "serverName" también confirma la sesión. */
        fun onUnexpectedBinary(bytes: ByteArray): List<Action> {
            if (authenticated || !String(bytes, Charsets.UTF_8).contains("serverName")) return emptyList()
            return handle(Event("successauth", null))
        }

        private fun handle(ev: Event): List<Action> {
            val out = mutableListOf<Action>()
            if (ev.name == "successauth" && !authenticated) {
                authenticated = true
                AFTER_AUTH.forEach { out += Action.Send(it) }
            }
            out += Action.Emit(ev)
            return out
        }
    }
}
