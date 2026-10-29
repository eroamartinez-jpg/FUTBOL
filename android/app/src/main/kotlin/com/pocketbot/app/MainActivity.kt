package com.pocketbot.app

import android.Manifest
import android.app.Activity
import android.app.AlertDialog
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.text.InputType
import android.view.Gravity
import android.view.View
import android.view.ViewGroup.LayoutParams.MATCH_PARENT
import android.view.ViewGroup.LayoutParams.WRAP_CONTENT
import android.widget.AdapterView
import android.widget.ArrayAdapter
import android.widget.Button
import android.widget.CheckBox
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.Spinner
import android.widget.TextView
import android.widget.Toast
import com.pocketbot.core.Direction
import com.pocketbot.core.Opportunity
import com.pocketbot.core.Protocol

class MainActivity : Activity() {
    private lateinit var prefs: Prefs
    private lateinit var account: TextView
    private lateinit var status: TextView
    private lateinit var startStop: Button
    private lateinit var list: LinearLayout
    private val countdowns = mutableListOf<Pair<TextView, Long>>()
    private val ticker = Handler(Looper.getMainLooper())
    private val observer: (BotState.Snapshot) -> Unit = ::render

    private val bg = Color.parseColor("#0F1724")
    private val card = Color.parseColor("#1B2A41")
    private val fg = Color.parseColor("#E6EDF3")
    private val muted = Color.parseColor("#8B9BB0")
    private val green = Color.parseColor("#2ECC71")
    private val red = Color.parseColor("#E74C3C")
    private val gold = Color.parseColor("#F1C40F")

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        prefs = Prefs(this)
        window.statusBarColor = bg
        setContentView(buildUi())
        if (Build.VERSION.SDK_INT >= 33 &&
            checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(arrayOf(Manifest.permission.POST_NOTIFICATIONS), 1)
        }
    }

    override fun onStart() {
        super.onStart()
        BotState.observe(observer)
        ticker.post(tick)
        refreshAccount()
    }

    override fun onStop() {
        BotState.remove(observer)
        ticker.removeCallbacks(tick)
        super.onStop()
    }

    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        refreshAccount()
    }

    private val tick = object : Runnable {
        override fun run() {
            val now = System.currentTimeMillis() / 1000
            countdowns.forEach { (tv, entry) -> tv.text = "faltan ${Format.countdown(entry - now)}" }
            ticker.postDelayed(this, 1000)
        }
    }

    // ---------- UI ----------

    private fun dp(v: Int) = (v * resources.displayMetrics.density).toInt()

    private fun text(s: String, size: Float = 14f, color: Int = fg, bold: Boolean = false) = TextView(this).apply {
        text = s
        textSize = size
        setTextColor(color)
        if (bold) setTypeface(typeface, Typeface.BOLD)
    }

    private fun button(label: String, color: Int = card, onClick: () -> Unit) = Button(this).apply {
        text = label
        setTextColor(fg)
        isAllCaps = false
        background = GradientDrawable().apply { setColor(color); cornerRadius = dp(10).toFloat() }
        setOnClickListener { onClick() }
    }

    private fun rounded(view: View, color: Int = card) {
        view.background = GradientDrawable().apply { setColor(color); cornerRadius = dp(12).toFloat() }
        view.setPadding(dp(12), dp(10), dp(12), dp(10))
    }

    private fun row(vararg views: View) = LinearLayout(this).apply {
        orientation = LinearLayout.HORIZONTAL
        gravity = Gravity.CENTER_VERTICAL
        views.forEachIndexed { i, v ->
            addView(v, LinearLayout.LayoutParams(0, WRAP_CONTENT, 1f).apply { if (i > 0) marginStart = dp(8) })
        }
    }

    private fun spaced(v: View, top: Int = 10) =
        LinearLayout.LayoutParams(MATCH_PARENT, WRAP_CONTENT).apply { topMargin = dp(top) }

    private fun <T> spinner(options: List<Pair<String, T>>, current: T, onPick: (T) -> Unit) = Spinner(this).apply {
        adapter = ArrayAdapter(this@MainActivity, android.R.layout.simple_spinner_dropdown_item, options.map { it.first })
        setSelection(options.indexOfFirst { it.second == current }.coerceAtLeast(0))
        onItemSelectedListener = object : AdapterView.OnItemSelectedListener {
            override fun onItemSelected(p: AdapterView<*>?, v: View?, pos: Int, id: Long) {
                (v as? TextView)?.setTextColor(fg)
                onPick(options[pos].second)
            }
            override fun onNothingSelected(p: AdapterView<*>?) {}
        }
    }

    private fun numberField(value: Int, onChange: (Int) -> Unit) = EditText(this).apply {
        setText(value.toString())
        setTextColor(fg)
        inputType = InputType.TYPE_CLASS_NUMBER
        setOnFocusChangeListener { _, has -> if (!has) text.toString().toIntOrNull()?.let(onChange) }
    }

    private fun labeled(label: String, v: View) = LinearLayout(this).apply {
        orientation = LinearLayout.VERTICAL
        addView(text(label, 12f, muted))
        addView(v)
    }

    private fun buildUi(): View {
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(16), dp(16), dp(16), dp(16))
        }
        root.addView(text("Pocket Bot", 24f, fg, bold = true))
        root.addView(text("Señales de tendencia y hora de entrada para Pocket Option", 13f, muted))

        account = text("", 13f, muted)
        root.addView(account, spaced(account, 8))

        root.addView(row(
            button("Iniciar sesión") { startActivityForResult(Intent(this, LoginActivity::class.java), 2) },
            button("Pegar SSID") { pasteSsidDialog() },
        ), spaced(root, 10))

        val settings = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        rounded(settings)
        val periods = listOf("5 s" to 5, "15 s" to 15, "30 s" to 30, "1 min" to 60, "2 min" to 120,
            "3 min" to 180, "5 min" to 300, "10 min" to 600, "15 min" to 900, "30 min" to 1800, "1 h" to 3600)
        val expiries = (1..5).map { "$it vela${if (it > 1) "s" else ""}" to it }
        settings.addView(row(
            labeled("Temporalidad", spinner(periods, prefs.periodS) { prefs.periodS = it }),
            labeled("Expiración", spinner(expiries, prefs.expiryCandles) { prefs.expiryCandles = it }),
        ))
        settings.addView(row(
            labeled("Payout mínimo %", numberField(prefs.minPayout) { prefs.minPayout = it.coerceIn(0, 100) }),
            labeled("Confianza mínima %", numberField(prefs.minConfidence) { prefs.minConfidence = it.coerceIn(0, 100) }),
        ), spaced(settings, 6))
        val otc = CheckBox(this).apply {
            text = "Solo OTC"; setTextColor(fg); isChecked = prefs.otcOnly
            setOnCheckedChangeListener { _, c -> prefs.otcOnly = c }
        }
        val all = CheckBox(this).apply {
            text = "Mostrar todos"; setTextColor(fg); isChecked = prefs.showAll
            setOnCheckedChangeListener { _, c -> prefs.showAll = c; render(BotState.current) }
        }
        settings.addView(row(otc, all), spaced(settings, 4))
        root.addView(settings, spaced(settings, 12))

        startStop = button("▶ Iniciar escaneo", Color.parseColor("#1E8449")) { toggle() }
        root.addView(startStop, spaced(startStop, 12))

        status = text("", 13f, muted)
        root.addView(status, spaced(status, 8))

        list = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        root.addView(list, spaced(list, 8))

        root.addView(text(
            "Aviso: las opciones binarias son de muy alto riesgo y la mayoría de los operadores " +
                "pierde dinero. Las señales son estimaciones estadísticas, no garantías. Prueba en DEMO.",
            11f, muted), spaced(root, 16))

        return ScrollView(this).apply {
            setBackgroundColor(bg)
            isFillViewport = true
            addView(root)
        }
    }

    // ---------- Acciones ----------

    private fun refreshAccount() {
        val raw = prefs.ssid
        val ssid = raw?.let { runCatching { Protocol.parseSsid(it) }.getOrNull() }
        account.text = when {
            ssid == null -> "Sin sesión: pulsa «Iniciar sesión» (o pega tu SSID)."
            ssid.isDemo -> "Sesión guardada: cuenta DEMO"
            else -> "Sesión guardada: cuenta REAL"
        }
    }

    private fun pasteSsidDialog() {
        val input = EditText(this).apply {
            hint = "42[\"auth\",{\"session\":...}]"
            setText(prefs.ssid ?: "")
        }
        AlertDialog.Builder(this)
            .setTitle("SSID de Pocket Option")
            .setMessage("Pega el mensaje 42[\"auth\",…] de tu sesión. Se guarda solo en este teléfono.")
            .setView(input)
            .setPositiveButton("Guardar") { _, _ ->
                try {
                    prefs.ssid = Protocol.parseSsid(input.text.toString()).raw
                    refreshAccount()
                } catch (e: IllegalArgumentException) {
                    Toast.makeText(this, e.message, Toast.LENGTH_LONG).show()
                }
            }
            .setNegativeButton("Cancelar", null)
            .show()
    }

    private fun toggle() {
        currentFocus?.clearFocus() // guarda los campos numéricos en edición
        if (BotState.current.running) {
            ScanService.stop(this)
            return
        }
        if (prefs.ssid == null) {
            Toast.makeText(this, "Primero inicia sesión en Pocket Option", Toast.LENGTH_LONG).show()
            return
        }
        BotState.update { it.copy(running = true, status = "Iniciando…") }
        ScanService.start(this)
    }

    // ---------- Resultados ----------

    private fun render(s: BotState.Snapshot) {
        startStop.text = if (s.running) "■ Detener" else "▶ Iniciar escaneo"
        (startStop.background as GradientDrawable).setColor(
            if (s.running) Color.parseColor("#922B21") else Color.parseColor("#1E8449"))
        val progress = if (s.running && s.total > 0 && s.scanned < s.total) " (${s.scanned}/${s.total})" else ""
        val last = if (s.lastScanAt > 0) "\nÚltimo escaneo: ${Format.time(s.lastScanAt / 1000)}" else ""
        status.text = s.status + progress + last

        list.removeAllViews()
        countdowns.clear()
        val rows = if (prefs.showAll) s.results else s.results.filter { it.recommended }
        if (s.lastScanAt > 0 && rows.isEmpty()) {
            list.addView(text("Sin señales recomendadas en esta vela. Espera a la siguiente.", 14f, muted))
        }
        rows.take(60).forEach { list.addView(resultCard(it), spaced(list, 8)) }
    }

    private fun resultCard(o: Opportunity): View {
        val s = o.signal
        val call = s.direction == Direction.CALL
        val color = when (s.direction) { Direction.CALL -> green; Direction.PUT -> red; else -> muted }
        val box = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        rounded(box)

        val head = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL }
        if (o.recommended) head.addView(text("★ ", 16f, gold, bold = true))
        head.addView(text(s.asset, 16f, fg, bold = true), LinearLayout.LayoutParams(0, WRAP_CONTENT, 1f))
        head.addView(text(if (call) "▲ CALL" else if (s.direction == Direction.PUT) "▼ PUT" else "—", 16f, color, bold = true))
        box.addView(head)

        val entry = text("Entrada ${Format.time(o.window.entry)}  →  expira ${Format.time(o.window.expiry)}", 15f, fg, bold = true)
        box.addView(entry, spaced(entry, 4))
        val cd = text("", 13f, gold)
        countdowns += cd to o.window.entry
        box.addView(cd)

        val b = o.stats
        box.addView(text(
            "Confianza ${s.confidence.toInt()}% · Payout ${o.payout}%\n" +
                "Acierto histórico ${"%.1f".format(b.winRate * 100)}% (equilibrio ${"%.1f".format(b.breakeven * 100)}%, n=${b.trades})",
            12f, muted), spaced(box, 4))
        return box
    }
}
