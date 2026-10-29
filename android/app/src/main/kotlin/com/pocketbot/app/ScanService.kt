package com.pocketbot.app

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.IBinder
import android.os.PowerManager
import android.webkit.WebSettings
import com.pocketbot.core.Opportunity
import com.pocketbot.core.Protocol
import com.pocketbot.core.ScanConfig
import com.pocketbot.core.Timing
import com.pocketbot.core.analyze
import com.pocketbot.core.opportunityOrder
import java.util.concurrent.Callable
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit

/**
 * Servicio en primer plano: mantiene la conexión y escanea todos los activos
 * al cierre de cada vela, aunque la app esté en segundo plano (por ejemplo,
 * mientras se opera en la app de Pocket Option). Avisa con una notificación
 * cuando aparece una señal recomendada.
 */
class ScanService : Service() {
    @Volatile private var running = false
    private var worker: Thread? = null
    private var wakeLock: PowerManager.WakeLock? = null
    private val notified = HashSet<String>()

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == ACTION_STOP) {
            stopSelf()
            return START_NOT_STICKY
        }
        createChannels()
        val notif = statusNotification("Conectando…")
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            startForeground(ID_STATUS, notif, ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC)
        } else {
            startForeground(ID_STATUS, notif)
        }
        if (!running) {
            running = true
            wakeLock = (getSystemService(Context.POWER_SERVICE) as PowerManager)
                .newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "pocketbot:scan")
                .apply { acquire(6 * 60 * 60 * 1000L) }
            worker = Thread(::loop, "pocket-scan").apply { start() }
        }
        return START_NOT_STICKY
    }

    override fun onDestroy() {
        running = false
        worker?.interrupt()
        wakeLock?.let { if (it.isHeld) it.release() }
        BotState.update { it.copy(running = false, status = "Detenido") }
        super.onDestroy()
    }

    private fun setStatus(text: String) {
        BotState.update { it.copy(running = true, status = text) }
        getSystemService(NotificationManager::class.java).notify(ID_STATUS, statusNotification(text))
    }

    private fun loop() {
        val prefs = Prefs(this)
        val ssid = try {
            Protocol.parseSsid(prefs.ssid ?: throw IllegalArgumentException("Falta el SSID: inicia sesión primero"))
        } catch (e: IllegalArgumentException) {
            BotState.update { it.copy(running = false, status = e.message ?: "SSID no válido") }
            stopSelf()
            return
        }
        val ua = runCatching { WebSettings.getDefaultUserAgent(this) }.getOrDefault(Protocol.DEFAULT_UA)
        var client: PocketClient? = null
        var failures = 0
        while (running) {
            try {
                if (client == null || !client.isOpen) {
                    client?.close()
                    setStatus("Conectando con Pocket Option…")
                    client = PocketClient(ssid, ua).also { it.connect() }
                    BotState.update { it.copy(accountDemo = client.isDemo) }
                    if (!client.awaitAssets()) throw java.io.IOException("no llegó la lista de activos")
                }
                scanOnce(client, prefs.scanConfig(), prefs.otcOnly)
                failures = 0
                sleepUntilNextCandle(prefs.periodS)
            } catch (e: InterruptedException) {
                break
            } catch (e: Exception) {
                client?.close()
                client = null
                failures++
                val msg = e.message ?: e.javaClass.simpleName
                if (msg.contains("rechaz")) {
                    BotState.update { it.copy(running = false, status = "$msg. Vuelve a iniciar sesión.") }
                    break
                }
                setStatus("Error: $msg. Reintentando…")
                try { Thread.sleep(minOf(5_000L * failures, 60_000L)) } catch (_: InterruptedException) { break }
            }
        }
        client?.close()
        stopSelf()
    }

    private fun scanOnce(client: PocketClient, cfg: ScanConfig, otcOnly: Boolean) {
        val assets = client.assets.values
            .filter { it.isActive && it.payout >= cfg.minPayout && (!otcOnly || it.isOtc) }
            .sortedByDescending { it.payout }
        setStatus("Analizando ${assets.size} activos…")
        BotState.update { it.copy(scanned = 0, total = assets.size) }
        val pool = Executors.newFixedThreadPool(4)
        val results = try {
            pool.invokeAll(assets.map { a ->
                Callable {
                    val opp = runCatching {
                        analyze(a.symbol, a.payout, client.candles(a.symbol, cfg.periodS, cfg.count), cfg,
                            System.currentTimeMillis() / 1000)
                    }.getOrNull()
                    BotState.update { it.copy(scanned = it.scanned + 1) }
                    opp
                }
            }).mapNotNull { runCatching { it.get() }.getOrNull() }
        } finally {
            pool.shutdownNow()
        }
        if (results.isEmpty() && assets.isNotEmpty() && !client.isOpen) {
            throw java.io.IOException(client.closedReason ?: "conexión perdida")
        }
        val sorted = results.sortedWith(opportunityOrder)
        val rec = sorted.count { it.recommended }
        BotState.update {
            it.copy(results = sorted, lastScanAt = System.currentTimeMillis(),
                status = "${results.size} activos analizados · $rec señal(es) recomendada(s)")
        }
        getSystemService(NotificationManager::class.java)
            .notify(ID_STATUS, statusNotification("${results.size} activos · $rec recomendada(s)"))
        notifySignals(sorted.filter { it.recommended })
    }

    private fun notifySignals(list: List<Opportunity>) {
        if (list.isEmpty()) return
        val key = list.joinToString { "${it.signal.asset}@${it.window.entry}" }
        if (!notified.add(key)) return
        val lines = list.take(5).map {
            val arrow = if (it.signal.direction.name == "CALL") "▲ CALL" else "▼ PUT"
            "${it.signal.asset} $arrow ${it.signal.confidence.toInt()}% · entrada ${Format.time(it.window.entry)}"
        }
        val n = builder(CHANNEL_SIGNALS)
            .setContentTitle("${list.size} señal(es) · entrada ${Format.time(list.first().window.entry)}")
            .setContentText(lines.first())
            .setStyle(Notification.BigTextStyle().bigText(lines.joinToString("\n")))
            .setAutoCancel(true)
            .build()
        getSystemService(NotificationManager::class.java).notify(ID_SIGNALS, n)
    }

    private fun sleepUntilNextCandle(periodS: Int) {
        val now = System.currentTimeMillis()
        val next = Timing.nextCandleOpen(now / 1000, periodS) * 1000
        // +2 s para que el servidor ya tenga la vela cerrada.
        Thread.sleep(maxOf(next - now + 2_000, 1_000))
    }

    private fun builder(channel: String): Notification.Builder {
        val b = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) Notification.Builder(this, channel)
        else @Suppress("DEPRECATION") Notification.Builder(this)
        val open = PendingIntent.getActivity(this, 0, Intent(this, MainActivity::class.java),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
        return b.setSmallIcon(R.drawable.ic_stat).setContentIntent(open)
    }

    private fun statusNotification(text: String): Notification {
        val stop = PendingIntent.getService(this, 1, Intent(this, ScanService::class.java).setAction(ACTION_STOP),
            PendingIntent.FLAG_IMMUTABLE)
        return builder(CHANNEL_STATUS)
            .setContentTitle("Pocket Bot escaneando")
            .setContentText(text)
            .setOngoing(true)
            .setOnlyAlertOnce(true)
            .addAction(Notification.Action.Builder(null, "Detener", stop).build())
            .build()
    }

    private fun createChannels() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
        val nm = getSystemService(NotificationManager::class.java)
        nm.createNotificationChannel(NotificationChannel(CHANNEL_STATUS, "Estado del escaneo",
            NotificationManager.IMPORTANCE_LOW))
        nm.createNotificationChannel(NotificationChannel(CHANNEL_SIGNALS, "Señales recomendadas",
            NotificationManager.IMPORTANCE_HIGH))
    }

    companion object {
        const val ACTION_STOP = "com.pocketbot.app.STOP"
        private const val CHANNEL_STATUS = "status"
        private const val CHANNEL_SIGNALS = "signals"
        private const val ID_STATUS = 1
        private const val ID_SIGNALS = 2

        fun start(context: Context) {
            val i = Intent(context, ScanService::class.java)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) context.startForegroundService(i)
            else context.startService(i)
        }

        fun stop(context: Context) {
            context.startService(Intent(context, ScanService::class.java).setAction(ACTION_STOP))
        }
    }
}
