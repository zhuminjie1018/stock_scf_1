# 改造方案：SCF 移动端适配 + Android(WebView) 客户端

> 生成日期：2026-10-15
> 关联文件：`index.py`、`stock_kline.py`、`doc/scf-refactor-plan.md`、`doc/scf-implementation-plan.md`
>
> 决策基线（已确认）：
> 1. Android 端采用**方案 B**：OkHttp 拉取 SCF 返回的 HTML → `WebView.loadDataWithBaseURL` 渲染。
> 2. SCF 的移动适配**本次一起做**（`inline` + viewport + 宽度 100% + CORS）。
> 3. **不预留** `format=json` 接口。
> 4. 手机竖屏采用**页面内纵向滚动 + 图表加高**。

---

## 1. 背景与目标

- 现状：SCF（`index.py.main_handler`）返回 `text/html` 的完整 K 线页，桌面浏览器可直接看；但生成的 HTML 面向桌面，手机端渲染有两个硬伤——缺 viewport、图表容器固定 `900px × 500px`。
- 目标：在不改动指标计算逻辑、不重写图表的前提下，让 SCF 返回的 HTML 在安卓 WebView 里正常、可读地展示；Android 侧用最小代码量完成"输入股票代码 → 请求 → 显示图表"闭环。

## 2. 总体架构

```
┌─────────────── Android App (Android Studio / Kotlin) ───────────────┐
│  EditText(股票代码) ─┐                                               │
│                      ├─ 校验正则 → OkHttp GET ──────────────┐        │
│  Button(查询) ───────┘                                       │        │
│                                                              ▼        │
│  WebView.loadDataWithBaseURL(scfUrl, html, "text/html")  ← HTML 字符串 │
└──────────────────────────────────────────────────────────────┼───────┘
                                                               │ HTTPS
                                                               ▼
┌──────────────── SCF 函数 URL (Python 3.10) ─────────────────┐
│  main_handler → generate_html(mobile=True)                  │
│    → get_data_from_ts → calc_zhibiao → draw_charts(宽100%,高加高) │
│  返回: text/html + Content-Disposition:inline + CORS + viewport │
└─────────────────────────────────────────────────────────────┘
```

要点：图表与指标**完全复用现有 Python 管线**，Android 不重复实现；移动适配集中在 SCF 侧的"外壳"（响应头 + HTML 注入 + 容器尺寸）。

---

## 3. SCF 侧改造

### 3.1 `_resp()`：补 `Content-Disposition` 与 CORS（index.py:20-26）

改为支持可选文件名，并统一加 CORS 头：

```python
def _resp(status_code, content_type, body, filename=None):
    headers = {
        "Content-Type": content_type,
        "Access-Control-Allow-Origin": "*",
    }
    if filename:
        headers["Content-Disposition"] = f'inline; filename="{filename}"'
    return {
        "isBase64Encoded": False,
        "statusCode": status_code,
        "headers": headers,
        "body": body,
    }
```

- 用 `inline` 语义上正确，但**在函数 URL 上不生效**：平台会把响应头的 `Content-Disposition` 覆盖为裸 `attachment`（无 filename），并额外注入默认 `Content-Type: application/json`。故浏览器直接访问仍会下载——这是"事件函数 + 函数 URL"链路的固有行为，非本函数可控。
- `filename` 因此也不生效，浏览器下载名改由 **URL 末段** 决定（见 §7.3）。
- CORS：原生 OkHttp 不需要，但为将来可能的 H5 版留出兼容，成本极低（实测响应头已出现）。
- 代码保留 `inline; filename=...` 无害：将来若改用 Web 函数（响应直接透传）则会生效。

### 3.2 `main_handler()`：请求移动版 + 注入 viewport + 命名（index.py:73-85）

```python
VIEWPORT = '<meta name="viewport" content="width=device-width, initial-scale=1">'

def _inject_viewport(html):
    return html.replace("<head>", "<head>\n" + VIEWPORT, 1)

def main_handler(event, context):
    qs = (event or {}).get("queryString") or {}
    ts_code = qs.get("ts_code") or var_ts_code
    start_date = qs.get("start_date") or var_start_date
    end_date = qs.get("end_date") or var_end_date

    try:
        html = generate_html(ts_code, start_date, end_date, mobile=True)
        html = _inject_viewport(html)
        return _resp(200, "text/html; charset=utf-8", html,
                     filename=f"kline_{ts_code}.html")
    except ValueError as e:
        return _resp(400, "text/html; charset=utf-8", _help_page(str(e), ts_code),
                     filename="kline_help.html")
    except Exception as e:
        return _resp(500, "text/plain; charset=utf-8", f"服务内部错误: {e}")
```

> `_help_page`（index.py:29-70）本身已带 viewport，无需再注入；它已足够长（>512B，满足 SCF 4xx 响应体要求）。

### 3.3 `stock_kline.py`：`mobile` 开关 + 宽度自适应 + 加高

新增 `mobile` 参数，向下贯穿 `generate_html → draw_charts`，**保留桌面 CLI 的原样**：

```python
# 移动端图表容器尺寸（竖屏纵向滚动 + 加高；可调）
MOBILE_CHART_WIDTH  = "100%"
MOBILE_CHART_HEIGHT = "900px"   # 相对桌面默认 500px 约 1.8 倍，K线区≈405px

def draw_charts(df, ts_code, mobile=False):
    ...
    if mobile:
        init_opts = opts.InitOpts(
            animation_opts=opts.AnimationOpts(animation=False),
            width=MOBILE_CHART_WIDTH,      # 关键：铺满屏宽，避免 900px 横向溢出
            height=MOBILE_CHART_HEIGHT,    # 关键：加高，竖屏内滚动查看
        )
    else:
        init_opts = opts.InitOpts(
            animation_opts=opts.AnimationOpts(animation=False),
        )
    grid = (Grid(init_opts=init_opts) ... )
```

```python
def generate_html(ts_code, start_date, end_date, mobile=False):
    ...
    return draw_charts(df, ts_code, mobile=mobile)
```

要点：
- Grid 内各分区用百分比定位（`pos_top`/`height` 为 `45%`/`10%` 等，stock_kline.py:556-574），容器加高后**各分区等比例变高**，4 区更易读。
- `width="100%"` 配合 viewport，图表宽度随屏宽自适应。
- CLI（`__main__`）不传 `mobile`，行为与现在完全一致。

### 3.4 echarts 资源可达性（风险项）

生成的 HTML 从 `https://assets.pyecharts.org/assets/v6/echarts.min.js` 加载 echarts（kline_chart.html:6）。需在手机网络下实测；若不可达，兜底方案（本次不做，仅登记）：自托管该 JS 并令 pyecharts 指向本地（`opts.InitOpts(js_host=...)`）。

---

## 4. Android 侧（方案 B：OkHttp + WebView）

### 4.1 依赖与权限

- `build.gradle`(app)：`implementation("com.squareup.okhttp3:okhttp:4.12.0")`
- `AndroidManifest.xml`：`<uses-permission android:name="android.permission.INTERNET" />`
- 函数 URL 为 HTTPS，**无需** cleartext / network security config。

### 4.2 UI 结构

```
LinearLayout(vertical)
 ├─ LinearLayout(horizontal)
 │    ├─ EditText  (hint="股票代码，如 000001.SZ"；inputType=text)
 │    └─ Button    ("查询")
 ├─ ProgressBar   (indeterminate，加载态)
 └─ WebView       (填充满剩余空间)
```

### 4.3 交互流程

1. 用户输入代码 → 点"查询"。
2. 客户端用正则校验 `\d{6}\.(SH|SZ|BJ)`（与 stock_kline.py:591 `validate()` 保持一致），非法则原生 Toast 提示、不发请求。
3. OkHttp 异步 GET：`https://<函数URL>/?ts_code=...&start_date=...&end_date=...`。
4. 成功：取 `body.string()`，在 UI 线程 `webView.loadDataWithBaseURL(scfUrl, html, "text/html", "utf-8", null)`；失败/超时：原生错误提示 + 重试。

### 4.4 WebView 配置

- `settings.javaScriptEnabled = true`（echarts 必需）
- `settings.domStorageEnabled = true`
- `webViewClient = WebViewClient()`（拦截为站内加载，避免跳出系统浏览器）
- 可选：`settings.useWideViewPort = true` / `loadWithOverviewMode = true`
- 竖屏纵向滚动由页面自然高度驱动（容器 900px > 屏高即可滚动），无需额外处理。

### 4.5 关键代码骨架（Kotlin）

```kotlin
class MainActivity : AppCompatActivity() {
    private val client = OkHttpClient()
    private val codeRegex = Regex("""\d{6}\.(SH|SZ|BJ)""")
    private val scfUrl = "https://<你的函数URL>/"
    private lateinit var webView: WebView
    private lateinit var codeInput: EditText
    private lateinit var progress: ProgressBar

    private fun query(code: String) {
        if (!codeRegex.matches(code)) { toast("代码格式应为 XXXXXX.SH/SZ/BJ"); return }
        val url = "$scfUrl?ts_code=$code"
        progress.visibility = View.VISIBLE
        client.newCall(Request.Builder().url(url).build()).enqueue(object : Callback {
            override fun onFailure(call: Call, e: IOException) =
                runOnUiThread { progress.visibility = View.GONE; toast("请求失败: ${e.message}") }
            override fun onResponse(call: Call, response: Response) {
                val html = response.body?.string().orEmpty()
                runOnUiThread {
                    progress.visibility = View.GONE
                    webView.loadDataWithBaseURL(scfUrl, html, "text/html", "utf-8", null)
                }
            }
        })
    }
}
```

> 注意：OkHttp 回调在后台线程，操作 View 必须 `runOnUiThread`。

---

## 5. 改动清单（文件 / 函数级）

| 文件 | 位置 | 改动 |
|---|---|---|
| `index.py` | `_resp()` (20-26) | 加 `filename` 参数、`Content-Disposition: inline`、`Access-Control-Allow-Origin: *` |
| `index.py` | 新增常量/函数 | `VIEWPORT`、`_inject_viewport()` |
| `index.py` | `main_handler()` (73-85) | `generate_html(..., mobile=True)`；注入 viewport；200/400 传 filename |
| `stock_kline.py` | 顶部常量 | `MOBILE_CHART_WIDTH` / `MOBILE_CHART_HEIGHT` |
| `stock_kline.py` | `draw_charts()` (177/545-550) | 新增 `mobile` 参数；按开关设置 `InitOpts(width,height)` |
| `stock_kline.py` | `generate_html()` (602/616) | 新增 `mobile` 参数并透传 |
| Android 工程 | 新建 | 按第 4 节实现（本次方案定稿，代码在 Android Studio 内落地） |

**不改动**：`get_data_from_ts` / `calc_*` / 各图表 series 逻辑 / CLI `__main__` 行为。

---

## 6. 验证步骤

**SCF（本地先行）**
1. `python -m py_compile stock_kline.py index.py`
2. 本地模拟：`generate_html('000001.SZ','20250101','20260918', mobile=True)` 渲染出的 HTML 中，容器应为 `width:100%; height:900px;`。
3. 部署后用 `curl -i "https://<函数URL>/?ts_code=000001.SZ"` 检查响应头：含 `Content-Type: text/html; charset=utf-8`、`Access-Control-Allow-Origin: *`；但 `Content-Disposition` 被平台覆盖为 `attachment`（无 filename），并额外注入 `Content-Type: application/json`；body 含 viewport meta。
4. 浏览器访问 URL 会**下载**（见 §7）；打开下载得到的 HTML 文件即可看到渲染效果。

**Android**
5. 真机/模拟器输入 `000001.SZ` → 触发请求 → WebView 显示 K 线；竖屏可纵向滚动，4 区可读。
6. 输入非法代码（如 `abc`）→ 原生提示、不发请求。
7. 断网点查询 → 原生错误提示。
8. 确认 echarts（`assets.pyecharts.org`）在目标网络下可加载。

---

## 7. 浏览器 URL 自测（无 App 端也可）

**实测结论：函数 URL（事件函数）会强制 `Content-Disposition: attachment` 并注入默认 `Content-Type: application/json`，覆盖本函数返回的 `inline; filename=...`。因此浏览器直接访问 URL 会"下载"而不是渲染。** 该行为属平台链路固有，非本函数可控；也**不影响 Android 方案 B**（OkHttp 读取 body，忽略 `Content-Disposition`）。

### 7.1 实测证据

`curl -i "https://<host>/?ts_code=000001.SZ"` 的真实响应头：

```
HTTP/1.1 200 OK
Access-Control-Allow-Origin: *
Content-Disposition: attachment            # 平台强制，本函数的 inline 被覆盖
Content-Type: application/json             # 平台注入的默认（重复头）
Content-Type: text/html; charset=utf-8     # 本函数设置
X-Scf-Request-Id: ...
Transfer-Encoding: chunked
```

（下载到的 HTML 内已含 viewport 与 `width:100%; height:900px`，证明移动改造已生效。）

### 7.2 自测方法

| # | 操作 | 预期 |
|---|---|---|
| 1 | 地址栏访问 `https://<url>/?ts_code=000001.SZ&start_date=20250101&end_date=20260918` | 浏览器**下载** HTML（不是渲染） |
| 2 | 打开下载得到的 `下载.htm` | 该文件自包含（脚本走绝对 CDN），本地打开即渲染 K 线；`F12`→`Ctrl+Shift+M` 选手机机型检查竖屏布局 |
| 3 | `curl -i "https://<url>/?ts_code=000001.SZ"` | 响应头如上；body 含 viewport meta |
| 4 | 访问 `?ts_code=abc`（非法代码） | 返回 400 辅助提示页；同样以文件形式下载，打开即见提示 |

### 7.3 自定义下载文件名（可选）

由于平台会剥掉响应头里的 filename，浏览器按 **URL 末段** 命名下载文件；而函数 URL 会把任意路径都路由给函数（本函数只看 query、忽略 path），因此把文件名放进 URL 末段即可：

| 访问 URL | 保存为 |
|---|---|
| `.../<host>/`（末段为空） | `下载.htm` |
| `.../<host>/kline_000001.SZ.html?ts_code=000001.SZ` | `kline_000001.SZ.html` |

SCF 侧无需改代码。

### 7.4 浏览器测不到、仍需真机/模拟器的部分

| 项 | 原因 |
|---|---|
| 手机网络下 `assets.pyecharts.org` 可达性 | 浏览器用电脑网络，环境不同（正是风险项） |
| WebView 行为（`WebViewClient`、返回键、`domStorage`） | 属 Android 层，浏览器不存在 |
| OkHttp 拉取 + `loadDataWithBaseURL` 链路 | Android 专有流程 |
| 触屏手势（双指缩放、brush 框选） | 桌面鼠标近似但不等同 |

> 即：**渲染效果、响应头、错误页** 可在浏览器阶段全部验证；**网络可达性与 WebView 交互** 留到真机阶段。

---

## 8. 风险与待观测项

| 风险 | 说明 | 应对 |
|---|---|---|
| echarts CDN 不可达 | 手机网络访问不到 `assets.pyecharts.org` → 白屏 | 自托管 JS（本次不做，登记备选） |
| 函数 URL 强制下载 | 平台覆盖 `Content-Disposition` 为 `attachment`，浏览器直接访问会下载 HTML（非渲染） | 属平台行为，不影响 App；浏览器自测＝打开下载文件（见 §7） |
| 加高后字号偏小 | `width:100%` 在窄屏下坐标轴/提示框拥挤 | 调整 `MOBILE_CHART_HEIGHT`、`pos_left/right` 边距 |
| 函数 URL 变动 | URL 变更需同步 App 配置 | App 中集中为常量/配置项，勿散落 |
| WebView 返回键 | 页面无路由，返回键默认退出 | 视需要 `webView.canGoBack()` 处理（当前单页，可忽略） |

---

## 9. 非目标（本次不做）

- 不新增 `format=json` 数据接口（已明确不预留）。
- 不做原生图表（MPAndroidChart/Vico）。
- 不改造指标计算逻辑与图表 series。
- 不改动桌面 CLI 的默认输出尺寸。
