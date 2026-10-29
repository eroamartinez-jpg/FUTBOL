package com.pocketbot.app

import com.pocketbot.core.Candle
import com.pocketbot.core.Protocol
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import okio.ByteString
import java.io.IOException
import java.util.concurrent.CompletableFuture
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicLong

/**
 * Conexión WebSocket con Pocket Option. Envía la cabecera Origin de la web
 * oficial (el servidor la exige) y el user agent de la sesión.
 */
class PocketClient(private val ssid: Protocol.Ssid, userAgent: String) {
    private val ua = ssid.userAgent ?: userAgent
    private val http = OkHttpClient.Builder()
        .pingInterval(20, TimeUnit.SECONDS)
        .readTimeout(0, TimeUnit.MILLISECONDS)
        .build()
    private var ws: WebSocket? = null
    private var session = Protocol.Session(ssid)
    @Volatile private var authLatch = CountDownLatch(1)
    private val assetsLatch = CountDownLatch(1)
    private val pending = ConcurrentHashMap<Long, CompletableFuture<List<Candle>>>()
    private val nextIndex = AtomicLong(System.currentTimeMillis() / 1000 * 100)

    @Volatile var assets: Map<String, Protocol.Asset> = emptyMap()
        private set
    @Volatile var closedReason: String? = null
        private set
    val isDemo get() = ssid.isDemo
    val isOpen get() = ws != null && closedReason == null

    /** Prueba cada servidor hasta autenticarse. Lanza IOException si ninguno responde. */
    fun connect(timeoutS: Long = 20) {
        var lastError = "sin respuesta"
        for (url in ssid.urls) {
            closedReason = null
            session = Protocol.Session(ssid)
            authLatch = CountDownLatch(1)
            val socket = http.newWebSocket(
                Request.Builder().url(url)
                    .header("Origin", Protocol.ORIGIN)
                    .header("User-Agent", ua)
                    .build(),
                listener,
            )
            ws = socket
            if (authLatch.await(timeoutS, TimeUnit.SECONDS) && closedReason == null) {
                startKeepAlive()
                return
            }
            lastError = closedReason ?: "tiempo de espera agotado en $url"
            socket.cancel()
            if (closedReason?.contains("rechaz") == true) break // SSID inválido: no insistir
        }
        throw IOException("No se pudo conectar a Pocket Option: $lastError")
    }

    fun awaitAssets(timeoutS: Long = 20): Boolean = assetsLatch.await(timeoutS, TimeUnit.SECONDS)

    /** Velas cerradas más recientes (hasta [count]). */
    fun candles(asset: String, periodS: Int, count: Int, timeoutS: Long = 15): List<Candle> {
        val now = System.currentTimeMillis() / 1000
        var result = request(asset, periodS, now, count.toLong() * periodS, timeoutS)
        if (result.isNotEmpty() && result.size < count) {
            // Si el servidor devolvió menos de lo pedido, se pide el tramo anterior.
            val older = request(asset, periodS, result.first().time, count.toLong() * periodS, timeoutS)
            result = (older + result).distinctBy { it.time }.sortedBy { it.time }
        }
        // La última vela puede seguir formándose: se descarta si aún no cerró.
        val closed = result.filter { it.time + periodS <= now }
        return closed.takeLast(count)
    }

    private fun request(asset: String, periodS: Int, end: Long, offsetS: Long, timeoutS: Long): List<Candle> {
        val index = nextIndex.incrementAndGet()
        val future = CompletableFuture<List<Candle>>()
        pending[index] = future
        try {
            val sent = ws?.send(Protocol.loadHistory(asset, periodS, end, offsetS, index)) ?: false
            if (!sent) throw IOException("conexión cerrada")
            return future.get(timeoutS, TimeUnit.SECONDS)
        } finally {
            pending.remove(index)
        }
    }

    fun close() {
        closedReason = closedReason ?: "cerrada"
        ws?.close(1000, null)
        ws = null
        http.dispatcher.executorService.shutdown()
    }

    private fun startKeepAlive() {
        Thread {
            while (isOpen) {
                try { Thread.sleep(20_000) } catch (_: InterruptedException) { break }
                ws?.send(Protocol.PING)
            }
        }.apply { isDaemon = true; name = "pocket-keepalive" }.start()
    }

    private fun dispatch(actions: List<Protocol.Action>) {
        for (a in actions) when (a) {
            is Protocol.Action.Send -> ws?.send(a.text)
            is Protocol.Action.Rejected -> {
                closedReason = a.message
                authLatch.countDown()
            }
            is Protocol.Action.Emit -> onEvent(a.event)
        }
    }

    private fun onEvent(ev: Protocol.Event) {
        val payload = ev.payload ?: run {
            if (ev.name == "successauth") authLatch.countDown()
            return
        }
        when (ev.name) {
            "successauth" -> authLatch.countDown()
            "updateAssets" -> runCatching { Protocol.parseAssets(payload) }.getOrNull()?.let { list ->
                if (list.isNotEmpty()) {
                    assets = list.associateBy { it.symbol }
                    assetsLatch.countDown()
                }
            }
            "loadHistoryPeriod", "loadHistoryPeriodFast" -> runCatching { Protocol.parseHistory(payload) }
                .getOrNull()?.let { h -> pending[h.index]?.complete(h.candles) }
        }
    }

    private val listener = object : WebSocketListener() {
        override fun onMessage(webSocket: WebSocket, text: String) {
            if (webSocket === ws) dispatch(session.onText(text))
        }

        override fun onMessage(webSocket: WebSocket, bytes: ByteString) {
            if (webSocket === ws) dispatch(session.onBinary(bytes.toByteArray()))
        }

        override fun onClosing(webSocket: WebSocket, code: Int, reason: String) {
            if (webSocket === ws) fail("el servidor cerró la conexión ($code)")
        }

        override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
            if (webSocket === ws) fail(t.message ?: t.javaClass.simpleName)
        }

        private fun fail(reason: String) {
            closedReason = closedReason ?: reason
            authLatch.countDown()
            pending.values.forEach { it.completeExceptionally(IOException(reason)) }
        }
    }
}
