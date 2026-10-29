package com.pocketbot.app

import android.os.Handler
import android.os.Looper
import com.pocketbot.core.Opportunity
import java.util.concurrent.CopyOnWriteArrayList

/** Estado compartido entre el servicio de escaneo y la pantalla. */
object BotState {
    data class Snapshot(
        val running: Boolean = false,
        val status: String = "Detenido",
        val accountDemo: Boolean? = null,
        val results: List<Opportunity> = emptyList(),
        val scanned: Int = 0,
        val total: Int = 0,
        val lastScanAt: Long = 0,
    )

    @Volatile var current = Snapshot()
        private set

    private val main = Handler(Looper.getMainLooper())
    private val listeners = CopyOnWriteArrayList<(Snapshot) -> Unit>()

    fun update(f: (Snapshot) -> Snapshot) {
        synchronized(this) { current = f(current) }
        val snap = current
        main.post { listeners.forEach { it(snap) } }
    }

    fun observe(l: (Snapshot) -> Unit) { listeners += l; l(current) }
    fun remove(l: (Snapshot) -> Unit) { listeners -= l }
}
