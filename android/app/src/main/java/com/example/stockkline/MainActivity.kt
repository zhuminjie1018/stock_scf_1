package com.example.stockkline

import android.annotation.SuppressLint
import android.os.Bundle
import android.view.View
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Button
import android.widget.EditText
import android.widget.ProgressBar
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import okhttp3.Call
import okhttp3.Callback
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import java.io.IOException
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.concurrent.TimeUnit

class MainActivity : AppCompatActivity() {

    private lateinit var etCode: EditText
    private lateinit var etStart: EditText
    private lateinit var etEnd: EditText
    private lateinit var btnConfirm: Button
    private lateinit var btnToggleInput: Button
    private lateinit var inputContainer: View
    private lateinit var progress: ProgressBar
    private lateinit var webView: WebView

    private val client: OkHttpClient = OkHttpClient.Builder()
        .connectTimeout(30, TimeUnit.SECONDS)
        .readTimeout(30, TimeUnit.SECONDS)
        .build()

    private val codeRegex = Regex("""\d{6}\.(SH|SZ|BJ)""")
    private val dateRegex = Regex("""\d{8}""")

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        etCode = findViewById(R.id.etCode)
        etStart = findViewById(R.id.etStart)
        etEnd = findViewById(R.id.etEnd)
        btnConfirm = findViewById(R.id.btnConfirm)
        btnToggleInput = findViewById(R.id.btnToggleInput)
        inputContainer = findViewById(R.id.inputContainer)
        progress = findViewById(R.id.progress)
        webView = findViewById(R.id.webView)

        // 默认值：股票代码/开始日期用固定缺省；结束日期取"今天"
        etCode.setText(getString(R.string.default_code))
        etStart.setText(getString(R.string.default_start))
        etEnd.setText(SimpleDateFormat("yyyyMMdd", Locale.US).format(Date()))

        webView.settings.javaScriptEnabled = true
        webView.settings.domStorageEnabled = true
        webView.settings.useWideViewPort = true
        webView.settings.loadWithOverviewMode = true
        webView.webViewClient = object : WebViewClient() {
            override fun onPageFinished(view: WebView?, url: String?) {
                // 页面加载完成后让 echarts 按当前 WebView 可视高度重排
                dispatchResize()
            }
        }

        // WebView 尺寸变化（收起/展开输入区、旋转）后，通知页面内 echarts 重算布局
        webView.addOnLayoutChangeListener { _, left, top, right, bottom, oldLeft, oldTop, oldRight, oldBottom ->
            val sizeChanged = (right - left) != (oldRight - oldLeft) ||
                (bottom - top) != (oldBottom - oldTop)
            if (sizeChanged) dispatchResize()
        }

        // 默认展开
        setInputsVisible(true)

        btnToggleInput.setOnClickListener { setInputsVisible(inputContainer.visibility != View.VISIBLE) }
        btnConfirm.setOnClickListener { onConfirm() }
    }

    private fun onConfirm() {
        val code = etCode.text.toString().trim().uppercase(Locale.US)
        val start = etStart.text.toString().trim()
        val end = etEnd.text.toString().trim()

        if (!codeRegex.matches(code)) {
            toast(getString(R.string.msg_invalid_code))
            return
        }
        if (!isValidDate(start) || !isValidDate(end)) {
            toast(getString(R.string.msg_invalid_date))
            return
        }
        if (start > end) {
            toast(getString(R.string.msg_date_order))
            return
        }
        // 查询前收起输入区，让图表占满整屏
        setInputsVisible(false)
        loadChart(code, start, end)
    }

    private fun isValidDate(value: String): Boolean {
        if (!dateRegex.matches(value)) return false
        return try {
            val fmt = SimpleDateFormat("yyyyMMdd", Locale.US)
            fmt.isLenient = false
            fmt.parse(value)
            true
        } catch (e: Exception) {
            false
        }
    }

    private fun loadChart(code: String, start: String, end: String) {
        val base = BuildConfig.SCF_BASE_URL.trimEnd('/')
        val url = "$base/?ts_code=$code&start_date=$start&end_date=$end"

        showLoading(true)
        client.newCall(Request.Builder().url(url).build()).enqueue(object : Callback {
            override fun onFailure(call: Call, e: IOException) {
                runOnUiThread {
                    showLoading(false)
                    toast(getString(R.string.msg_network_error, e.message ?: e.toString()))
                }
            }

            override fun onResponse(call: Call, response: Response) {
                response.use { resp ->
                    // 注意：平台会注入重复 Content-Type，勿依赖响应头猜编码，统一按 UTF-8 解码
                    val html = resp.body?.bytes()?.toString(Charsets.UTF_8)
                    runOnUiThread {
                        showLoading(false)
                        when {
                            !resp.isSuccessful ->
                                toast(getString(R.string.msg_http_error, resp.code))

                            html.isNullOrBlank() ->
                                toast(getString(R.string.msg_empty_body))

                            else ->
                                webView.loadDataWithBaseURL(base, html, "text/html", "utf-8", null)
                        }
                    }
                }
            }
        })
    }

    private fun setInputsVisible(visible: Boolean) {
        inputContainer.visibility = if (visible) View.VISIBLE else View.GONE
        btnToggleInput.setText(if (visible) R.string.btn_collapse else R.string.btn_expand)
    }

    private fun dispatchResize() {
        // echarts 默认监听 window 的 resize 事件，会据此重算各分区尺寸
        webView.evaluateJavascript("window.dispatchEvent(new Event('resize'));", null)
    }

    private fun showLoading(loading: Boolean) {
        progress.visibility = if (loading) View.VISIBLE else View.GONE
        btnConfirm.isEnabled = !loading
    }

    private fun toast(message: String) {
        Toast.makeText(this, message, Toast.LENGTH_LONG).show()
    }
}
