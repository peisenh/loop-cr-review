package de.peisenh.loopcrreview

import android.annotation.SuppressLint
import android.app.Activity
import android.content.Intent
import android.database.Cursor
import android.graphics.Typeface
import android.net.Uri
import android.os.Bundle
import android.print.PrintAttributes
import android.print.PrintManager
import android.provider.OpenableColumns
import android.util.Log
import android.view.ViewGroup
import android.webkit.CookieManager
import android.webkit.ValueCallback
import android.webkit.WebChromeClient
import android.webkit.WebResourceRequest
import android.webkit.WebResourceResponse
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.FrameLayout
import android.widget.ScrollView
import android.widget.TextView
import android.widget.Toast
import androidx.core.content.FileProvider
import androidx.core.view.ViewCompat
import androidx.core.view.WindowCompat
import androidx.core.view.WindowInsetsCompat
import com.chaquo.python.PyObject
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform
import java.io.File
import java.net.HttpURLConnection
import java.net.URL

/**
 * Thin shell: Chaquopy starts Flask on loopback; WebView shows the existing UI.
 * Health data never leaves the device (processed in Python temp dirs).
 */
private const val TAG = "loop-cr-review"

class MainActivity : Activity() {
    private lateinit var webView: WebView
    private var fileCallback: ValueCallback<Array<Uri>>? = null
    private var server: PyObject? = null
    private var accessToken: String = ""
    private var pendingSave: File? = null
    private var printPreview: WebView? = null
    private var loopbackPort: Int = -1

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        WindowCompat.setDecorFitsSystemWindows(window, false)

        try {
            if (!Python.isStarted()) {
                Python.start(AndroidPlatform(this))
            }
            val module = Python.getInstance().getModule("android_server")
            server = module
            val port = module.callAttr("start").toInt()
            loopbackPort = port
            setupWebView(port)
        } catch (e: Exception) {
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
        // Pad a wrapper, not the WebView: WebView eats WindowInsets and the
        // chrome then sits under the Pixel status bar.
        val root = FrameLayout(this)
        webView = WebView(this)
        root.addView(
            webView,
            FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.MATCH_PARENT
            )
        )
        setContentView(root)
        ViewCompat.setOnApplyWindowInsetsListener(root) { v, insets ->
            val bars = insets.getInsets(WindowInsetsCompat.Type.systemBars())
            v.setPadding(bars.left, bars.top, bars.right, bars.bottom)
            WindowInsetsCompat.CONSUMED
        }
        ViewCompat.requestApplyInsets(root)

        webView.settings.javaScriptEnabled = true
        webView.settings.domStorageEnabled = true
        webView.settings.allowFileAccess = false
        webView.settings.allowContentAccess = false
        webView.webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(
                view: WebView,
                request: WebResourceRequest
            ): Boolean {
                val uri = request.url
                if (isLoopbackOrigin(uri)) {
                    val path = uri.path ?: return false
                    if (path.endsWith("/print")) {
                        val body = uri.buildUpon()
                            .encodedPath(path.removeSuffix("/print") + "/body")
                            .build()
                        printReport(body.toString())
                        return true
                    }
                    return false
                }
                if (uri.scheme == "http" || uri.scheme == "https") {
                    startActivity(Intent(Intent.ACTION_VIEW, uri))
                }
                return true
            }

            override fun shouldInterceptRequest(
                view: WebView,
                request: WebResourceRequest
            ): WebResourceResponse? {
                if (request.method != "GET") return null
                val uri = request.url
                if (!isLoopbackOrigin(uri)) {
                    return WebResourceResponse("text/plain", "utf-8", 403, "Forbidden",
                        emptyMap(), ByteArray(0).inputStream())
                }
                val path = uri.path ?: return null
                if (!Regex("^/result/[0-9a-f]{32}(/download|/external)?$").matches(path)) {
                    return null
                }
                return try {
                    // This is the app's own HTTP client, not the WebView: it has
                    // no cookie, so the token has to travel in the URL.
                    val authed = uri.buildUpon().appendQueryParameter("k", accessToken).build()
                    val conn = URL(authed.toString()).openConnection() as HttpURLConnection
                    conn.connect()
                    val bytes = conn.inputStream.readBytes()
                    val disp = conn.getHeaderField("Content-Disposition") ?: ""
                    val openExternal = path.endsWith("/external")
                    if (openExternal || disp.contains("attachment", ignoreCase = true)) {
                        val tmp = File(File(cacheDir, "reports").apply { mkdirs() }, "loop-cr-review.html")
                        tmp.writeBytes(bytes)
                        if (openExternal) {
                            view.post { openReportInBrowser(tmp) }
                        } else {
                            pendingSave = tmp
                            view.post {
                                val intent = Intent(Intent.ACTION_CREATE_DOCUMENT).apply {
                                    addCategory(Intent.CATEGORY_OPENABLE)
                                    type = "text/html"
                                    putExtra(Intent.EXTRA_TITLE, "loop-cr-review.html")
                                }
                                startActivityForResult(intent, SAVE_REQUEST)
                                val home = uri.buildUpon().encodedPath("/").encodedQuery(null)
                                    .fragment(null).build()
                                view.loadUrl(home.toString())
                            }
                        }
                        WebResourceResponse(
                            "text/html", "utf-8",
                            "<html></html>".byteInputStream()
                        )
                    } else {
                        WebResourceResponse("text/html", "utf-8", bytes.inputStream())
                    }
                } catch (e: Exception) {
                    Log.e(TAG, "intercept failed", e)
                    null
                }
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
                val intent = Intent(Intent.ACTION_GET_CONTENT).apply {
                    addCategory(Intent.CATEGORY_OPENABLE)
                    type = "*/*"
                    putExtra(Intent.EXTRA_ALLOW_MULTIPLE, true)
                    addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
                }
                startActivityForResult(Intent.createChooser(intent, null), FILE_REQUEST)
                return true
            }
        }
        // The server only answers with this secret; it hands back a cookie on the
        // first request, so the pages loaded afterwards need nothing extra.
        accessToken = server?.callAttr("access_token")?.toString().orEmpty()
        webView.loadUrl("http://127.0.0.1:$port/?k=" + Uri.encode(accessToken))
    }

    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode == FILE_REQUEST) {
            val result = if (resultCode == Activity.RESULT_OK && data != null) {
                runCatching {
                    val uris = mutableListOf<Uri>()

                    // Android returns multiple selections in ClipData.
                    data.clipData?.let { clipData ->
                        for (i in 0 until clipData.itemCount) {
                            uris += clipData.getItemAt(i).uri
                        }
                    }

                    // Some pickers return a single file in data.data instead.
                    if (uris.isEmpty()) {
                        data.data?.let { uris += it }
                    }

                    require(uris.isNotEmpty()) { "no file selected" }
                    uris.map { copyPickToCache(it) }.toTypedArray()
                }
                    .onFailure { Log.e(TAG, "could not copy picked files", it) }
                    .getOrNull()
            } else null

            fileCallback?.onReceiveValue(result)
            fileCallback = null
        } else if (requestCode == SAVE_REQUEST) {
            val dest = data?.data
            val src = pendingSave
            pendingSave = null
            if (resultCode == Activity.RESULT_OK && dest != null && src != null && src.isFile) {
                runCatching {
                    contentResolver.openOutputStream(dest).use { out ->
                        requireNotNull(out)
                        src.inputStream().use { it.copyTo(out) }
                    }
                }.onFailure { Log.e(TAG, "could not write saved report", it) }
                 .onSuccess { Toast.makeText(this, "Saved", Toast.LENGTH_SHORT).show() }
            }
            src?.delete()
        }
    }



    private fun isLoopbackOrigin(uri: Uri): Boolean {
        if (uri.scheme != "http") return false
        val host = uri.host ?: return false
        if (!host.equals("127.0.0.1", true) && !host.equals("localhost", true)) {
            return false
        }
        val port = if (uri.port == -1) 80 else uri.port
        return port == loopbackPort
    }

    private fun printReport(url: String) {
        val preview = WebView(this)
        printPreview = preview
        preview.settings.javaScriptEnabled = true
        preview.settings.allowFileAccess = false
        preview.settings.allowContentAccess = false
        if (!isLoopbackOrigin(Uri.parse(url))) return
        preview.webViewClient = object : WebViewClient() {
            override fun onPageFinished(view: WebView, loaded: String) {
                val printer = getSystemService(PRINT_SERVICE) as PrintManager
                printer.print(
                    "loop-cr-review",
                    view.createPrintDocumentAdapter("loop-cr-review"),
                    PrintAttributes.Builder().build()
                )
            }
        }
        preview.loadUrl(url)
    }

    private fun openReportInBrowser(file: File) {
        val uri = FileProvider.getUriForFile(this, "$packageName.files", file)
        val intent = Intent(Intent.ACTION_VIEW).apply {
            setDataAndType(uri, "text/html")
            addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
        }
        runCatching { startActivity(intent) }
            .onFailure {
                Log.e(TAG, "no browser for report", it)
                Toast.makeText(this, "No browser", Toast.LENGTH_LONG).show()
            }
    }

    private fun copyPickToCache(uri: Uri): Uri {
        val hinted = displayName(uri)
        val tmp = File(cacheDir, "picked.bin")
        contentResolver.openInputStream(uri).use { input ->
            requireNotNull(input) { "no stream for $uri" }
            tmp.outputStream().use { input.copyTo(it) }
        }
        val named = File(cacheDir, withSuffix(tmp, hinted))
        if (named != tmp) {
            if (named.exists()) named.delete()
            if (!tmp.renameTo(named)) {
                tmp.copyTo(named, overwrite = true)
                tmp.delete()
            }
        }
        Log.i(TAG, "picked ${named.name} ${named.length()} bytes")
        return Uri.fromFile(named)
    }

    private fun displayName(uri: Uri): String {
        var name = "export"
        contentResolver.query(uri, arrayOf(OpenableColumns.DISPLAY_NAME), null, null, null)
            ?.use { c: Cursor ->
                if (c.moveToFirst()) {
                    val i = c.getColumnIndex(OpenableColumns.DISPLAY_NAME)
                    if (i >= 0) name = c.getString(i) ?: name
                }
            }
        return File(name).name.ifBlank { "export" }
    }

    private fun withSuffix(file: File, name: String): String {
        val lower = name.lowercase()
        if (lower.endsWith(".zip") || lower.endsWith(".csv") || lower.endsWith(".json")) {
            return name
        }
        val head = ByteArray(4)
        val n = file.inputStream().use { it.read(head) }
        return if (n >= 2 && head[0] == 0x50.toByte() && head[1] == 0x4b.toByte()) {
            "$name.zip"
        } else {
            name
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

    override fun onPause() {
        // Android writes cookies to disk lazily. Without this the slot times a
        // user just entered can be lost when the process is killed, and the app
        // serves itself on a fresh port every launch, so there is nothing else
        // holding them.
        CookieManager.getInstance().flush()
        super.onPause()
    }

    override fun onDestroy() {
        // The report handed to the browser and the export the user picked are
        // both the user's data; neither has any reason to outlive the app.
        File(File(cacheDir, "reports"), "loop-cr-review.html").delete()
        cacheDir.listFiles()?.forEach { file ->
            if (file.isFile && file.name != "loop-cr-review.html") {
                file.delete()
            }
        }
        runCatching { server?.callAttr("stop") }
        if (::webView.isInitialized) {
            webView.destroy()
        }
        super.onDestroy()
    }

    companion object {
        private const val FILE_REQUEST = 1001
        private const val SAVE_REQUEST = 1002
    }
}
