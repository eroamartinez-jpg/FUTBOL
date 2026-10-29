package com.pocketbot.app

import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/** Horas en la zona horaria del teléfono. */
object Format {
    private val hms = SimpleDateFormat("HH:mm:ss", Locale.getDefault())

    @Synchronized fun time(epochS: Long): String = hms.format(Date(epochS * 1000))

    fun countdown(seconds: Long): String = when {
        seconds <= 0 -> "¡ya!"
        seconds < 60 -> "${seconds}s"
        else -> "${seconds / 60}m${"%02d".format(seconds % 60)}s"
    }
}
