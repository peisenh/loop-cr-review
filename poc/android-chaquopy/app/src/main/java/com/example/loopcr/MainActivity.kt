package com.example.loopcr

import android.annotation.SuppressLint
import android.app.Activity
import android.content.Intent
import android.graphics.Typeface
import android.net.Uri
import android.os.Bundle
import android.util.Log
import android.webkit.ValueCallback
import android.webkit.WebChromeClient
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.ScrollView
import android.widget.TextView
import com.chaquo.python.PyObject
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform

/**
 * Thin shell: Chaquopy starts Flask on loopback; WebView shows the existing UI.
 * Health data never leaves the device (processed in Python temp dirs).
 */
private const val TAG = "loop-cr-review"

class MainActivity : Activity() {
    private lateinit var webView: WebView
    private var fileCallback: ValueCallback<Array<Uri>>? = null
    private var server: PyObject? = null

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        try {
            if (!Python.isStarted()) {
                Python.start(AndroidPlatform(this))
            }
            val module = Python.getInstance().getModule("android_server")
            server = module
            val port = module.callAttr("start").toInt()
            setupWebView(port)
        } catch (e: Exception) {
            // A toast truncates the message and is gone in seconds, which is
            // useless for a Python traceback - log the whole thing, and keep the
            // window open with the text on screen instead of closing silently.
            Log.e(TAG, "Python/Flask failed to start", e)
            showStartupError(e)
        }
    }

    private fun showStartupError(e: Exception) {
        val text = TextView(this).apply {
            setPadding(32, 64, 32, 32)
            typeface = Typeface.MONOSPACE
            textSize = 12f
            setTextIsSelectable(true)
            text = "Python/Flask failed to start\n\n" + Log.getStackTraceString(e)
        }
        setContentView(ScrollView(this).apply { addView(text) })
    }

    private fun setupWebView(port: Int) {
        webView = WebView(this)
        setContentView(webView)
        webView.settings.javaScriptEnabled = true
        webView.settings.domStorageEnabled = true
        webView.settings.allowFileAccess = false
        webView.settings.allowContentAccess = true
        webView.webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(
                view: WebView,
                request: WebResourceRequest
            ): Boolean {
                val host = request.url.host ?: return true
                return !host.equals("localhost", ignoreCase = true)
                        && !host.equals("127.0.0.1", ignoreCase = true)
            }
        }
        webView.webChromeClient = object : WebChromeClient() {
            override fun onShowFileChooser(
                webView: WebView?,
                filePathCallback: ValueCallback<Array<Uri>>?,
                fileChooserParams: FileChooserParams?
            ): Boolean {
                fileCallback?.onReceiveValue(null)
                fileCallback = filePathCallback
                val intent = Intent(Intent.ACTION_OPEN_DOCUMENT).apply {
                    addCategory(Intent.CATEGORY_OPENABLE)
                    type = "*/*"
                    putExtra(
                        Intent.EXTRA_MIME_TYPES,
                        arrayOf("application/zip", "text/csv", "text/*", "application/json")
                    )
                }
                startActivityForResult(intent, FILE_REQUEST)
                return true
            }
        }
        webView.loadUrl("http://127.0.0.1:$port/")
    }

    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode == FILE_REQUEST) {
            val result = if (resultCode == Activity.RESULT_OK && data?.data != null) {
                arrayOf(data.data!!)
            } else null
            fileCallback?.onReceiveValue(result)
            fileCallback = null
        }
    }

    @Deprecated("Deprecated in Java")
    override fun onBackPressed() {
        if (::webView.isInitialized && webView.canGoBack()) {
            webView.goBack()
        } else {
            @Suppress("DEPRECATION")
            super.onBackPressed()
        }
    }

    override fun onDestroy() {
        runCatching { server?.callAttr("stop") }
        if (::webView.isInitialized) {
            webView.destroy()
        }
        super.onDestroy()
    }

    companion object {
        private const val FILE_REQUEST = 1001
    }
}
