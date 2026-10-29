package com.pocketbot.app

import android.annotation.SuppressLint
import android.app.Activity
import android.os.Bundle
import android.webkit.CookieManager
import android.webkit.JavascriptInterface
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Toast
import androidx.webkit.WebViewCompat
import androidx.webkit.WebViewFeature
import com.pocketbot.core.Protocol

/**
 * Abre pocketoption.com para iniciar sesión y captura el SSID: el mensaje
 * `42["auth",...]` que la propia web envía por su WebSocket. Se guarda solo
 * en este teléfono.
 */
class LoginActivity : Activity() {
    private lateinit var web: WebView
    @Volatile private var captured = false

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        web = WebView(this)
        setContentView(web)
        CookieManager.getInstance().setAcceptCookie(true)
        web.settings.javaScriptEnabled = true
        web.settings.domStorageEnabled = true
        web.addJavascriptInterface(Bridge(), "PocketBot")
        val origins = setOf("https://pocketoption.com", "https://*.pocketoption.com")
        if (WebViewFeature.isFeatureSupported(WebViewFeature.DOCUMENT_START_SCRIPT)) {
            WebViewCompat.addDocumentStartJavaScript(web, HOOK, origins)
        }
        web.webViewClient = object : WebViewClient() {
            override fun onPageStarted(view: WebView, url: String?, favicon: android.graphics.Bitmap?) {
                // Respaldo para WebViews antiguos sin DOCUMENT_START_SCRIPT.
                view.evaluateJavascript(HOOK, null)
            }
        }
        Toast.makeText(this, "Inicia sesión y abre la sala de operaciones (demo o real)", Toast.LENGTH_LONG).show()
        web.loadUrl("https://pocketoption.com/es/login/")
    }

    @Deprecated("API de Activity sin AndroidX")
    @Suppress("DEPRECATION")
    override fun onBackPressed() {
        if (web.canGoBack()) web.goBack() else super.onBackPressed()
    }

    inner class Bridge {
        @JavascriptInterface
        fun onSsid(message: String) {
            if (captured) return
            val ssid = runCatching { Protocol.parseSsid(message) }.getOrNull() ?: return
            captured = true
            Prefs(this@LoginActivity).ssid = ssid.raw
            runOnUiThread {
                val kind = if (ssid.isDemo) "DEMO" else "REAL"
                Toast.makeText(this@LoginActivity, "Sesión $kind capturada", Toast.LENGTH_LONG).show()
                setResult(RESULT_OK)
                finish()
            }
        }
    }

    companion object {
        private const val HOOK = """
            (function () {
              if (window.__pocketBotHook) return;
              window.__pocketBotHook = true;
              var send = WebSocket.prototype.send;
              WebSocket.prototype.send = function (data) {
                try {
                  if (typeof data === 'string' && data.indexOf('42["auth"') === 0) PocketBot.onSsid(data);
                } catch (e) {}
                return send.apply(this, arguments);
              };
            })();
        """
    }
}
