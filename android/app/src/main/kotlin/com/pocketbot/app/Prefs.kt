package com.pocketbot.app

import android.content.Context
import com.pocketbot.core.ScanConfig

/** Ajustes guardados en el teléfono (incluido el SSID, que nunca sale del dispositivo). */
class Prefs(context: Context) {
    private val sp = context.getSharedPreferences("pocketbot", Context.MODE_PRIVATE)

    var ssid: String?
        get() = sp.getString("ssid", null)
        set(v) = sp.edit().putString("ssid", v).apply()

    var periodS: Int
        get() = sp.getInt("period", 60)
        set(v) = sp.edit().putInt("period", v).apply()

    var expiryCandles: Int
        get() = sp.getInt("expiry", 1)
        set(v) = sp.edit().putInt("expiry", v).apply()

    var minPayout: Int
        get() = sp.getInt("min_payout", 80)
        set(v) = sp.edit().putInt("min_payout", v).apply()

    var minConfidence: Int
        get() = sp.getInt("min_conf", 60)
        set(v) = sp.edit().putInt("min_conf", v).apply()

    var showAll: Boolean
        get() = sp.getBoolean("show_all", false)
        set(v) = sp.edit().putBoolean("show_all", v).apply()

    var otcOnly: Boolean
        get() = sp.getBoolean("otc_only", false)
        set(v) = sp.edit().putBoolean("otc_only", v).apply()

    fun scanConfig() = ScanConfig(
        periodS = periodS,
        expiryCandles = expiryCandles,
        minPayout = minPayout,
        minConfidence = minConfidence.toDouble(),
        count = 300,
    )
}
