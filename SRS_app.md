# SRS：股票 K 线 Android 客户端（WebView 方案）

> 文档版本：v0.2（草稿）
> 生成日期：2026-10-15
> 关联文档：`doc/mobile-adaptation-plan.md`（SCF 移动适配方案）、`AGENTS.md`
> 服务端：腾讯云函数 SCF（事件函数 + 函数 URL，已上线）

---

## 1. 背景与目标

- 现有 **SCF 服务**已能根据 `ts_code / start_date / end_date` 返回移动适配的 K 线 HTML 页面（含 K线、成交量、MACD、波段四区）。
- 本项目的目标是开发一个 **Android 客户端**：用户在手机上输入参数、点击确认，App 请求 SCF、取回 HTML 并在应用内显示股票图。
- 采用 **方案 B**：原生 HTTP 客户端（OkHttp）拉取 SCF 返回的 HTML 字符串 → 交给 `WebView` 渲染。复用 SCF 全部指标计算与图表逻辑，Android 端不重复实现任何指标。

## 2. 范围

**包含**
- 一个可输入参数、请求 SCF、显示图表的单页 Android 应用。
- SCF 函数 URL 的**可配置**能力。

**不包含**（本次）
- 原生图表重绘（MPAndroidChart/Vico 等）。
- SCF 侧 `format=json` 数据接口。
- 账号、登录、自选股、离线缓存、图表另存/分享等增值功能。

## 3. 术语

| 术语 | 含义 |
|---|---|
| SCF | 腾讯云函数（Serverless Cloud Function），本项目服务端 |
| 函数 URL | SCF 提供的公网 HTTPS 端点，形如 `https://<id>.<region>.tencentscf.com` |
| ts_code | 股票代码，格式 `XXXXXX.SH/SZ/BJ`（如 `000001.SZ`） |
| 方案 B | OkHttp 拉取 HTML → `WebView.loadDataWithBaseURL` 渲染 |

## 4. 总体架构

```
┌──────────────────── Android App（单 Activity） ────────────────────┐
│  [股票代码] [开始日期] [结束日期]  [确认]                            │
│        │                                                            │
│        ├─ 客户端校验（ts_code / 日期格式）                          │
│        │                                                            │
│        └─ OkHttp GET  <SCF_BASE_URL>?ts_code=..&start_date=..&end_date=.. │
│                          │（读 body 字符串）                        │
│                          ▼                                          │
│              WebView.loadDataWithBaseURL(<SCF_BASE_URL>, html, ...) │
└────────────────────────────────────────────────────────────────────┘
                              │ HTTPS
                              ▼
┌──────────────── SCF 函数 URL（事件函数） ────────────────┐
│  返回 text/html（移动版：viewport + width:100% + height:100vh + 去body边距） │
│  注：平台会强制 Content-Disposition: attachment —— App 取 body │
│      渲染，不受该头影响（见 §8.4）                             │
└──────────────────────────────────────────────────────────┘
```

## 5. 功能需求（FR）

### FR-1 参数输入
页面须提供以下输入项：
- **股票代码**：文本输入框，提示格式 `XXXXXX.SH/SZ/BJ`，默认值 `600519.SH`。
- **开始日期**：**纯文本框**，输入 `YYYYMMDD`（8 位数字），带格式提示（如"格式 YYYYMMDD，例 20250101"），默认 `20260101`。
- **结束日期**：**纯文本框**，输入 `YYYYMMDD`（8 位数字），带格式提示，默认 **当前日期**（启动时按 `yyyyMMdd` 计算）。
- **确认按钮**：触发查询。
- **输入区可折叠**：顶部提供"收起/展开"切换；**默认展开**；点确认且校验通过后**自动收起**，让图表占满整屏。

### FR-2 参数校验（客户端）
- `ts_code` 须匹配正则 `\d{6}\.(SH|SZ|BJ)`；不匹配时不发请求，原生提示。
- 开始/结束日期须为合法 `YYYYMMDD`，且 `start <= end`；不满足时不发请求，原生提示。
- 校验规则须与 SCF 侧 `validate()`（`stock_kline.py`）保持一致。

### FR-3 请求 SCF
- 用 **OkHttp** 异步 GET：`<SCF_BASE_URL>?ts_code=..&start_date=..&end_date=..`。
- 请求期间显示加载态（进度指示），禁用重复点击。
- 超时须可配置（建议连接/读取各 15~30s，含 SCF 冷启动）。

### FR-4 显示股票图
- 成功（HTTP 2xx）时，将响应 body 作为 HTML 载入 `WebView`：`loadDataWithBaseURL(SCF_BASE_URL, html, "text/html", "utf-8", null)`。
- `WebView` 须启用 JS（echarts 依赖）；图表高度＝WebView 可视高度（SCF 用 `100vh`），**恰好一屏、无需滚动**；输入区收起后图表自动占满并重排。
- 图表内 echarts 脚本从 `assets.pyecharts.org` CDN 加载，需保证网络可达。

### FR-5 加载态与错误处理
- **加载中**：显示进度指示。
- **网络失败/超时**：原生错误提示（含原因），可重试。
- **非 2xx**：默认展示原生错误（含状态码）；可选将响应体（SCF 的 400 辅助提示页）载入 WebView 展示。
- **请求成功但 body 异常**：提示"返回内容异常"。

### FR-6 SCF 函数 URL 可配置
- 函数 URL 可能变化，**不得硬编码**在业务代码中。
- 采用**仅编译期配置**（做法 A）：由构建配置（`gradle.properties` → `BuildConfig`）提供，代码读 `BuildConfig.SCF_BASE_URL`（见 §9）。
- 不提供运行期修改入口；换地址需重新构建 APK。

## 6. 非功能需求（NFR）

| 编号 | 需求 |
|---|---|
| NFR-1 | **兼容 Android Studio**：标准 Gradle 工程，可用 Android Studio 打开、同步、构建、运行、调试。 |
| NFR-2 | **目录隔离**：代码放在仓库内**独立新目录**，不与 SCF 的 `src/`、Python 文件混放（见 §7）。 |
| NFR-3 | 语言 Kotlin；`minSdk` 建议 24+，`targetSdk` 取开发时最新稳定版。 |
| NFR-4 | 网络：`AndroidManifest.xml` 声明 `INTERNET` 权限；SCF 为 HTTPS，无需 cleartext 配置。 |
| NFR-5 | 适配手机竖屏；图表恰好一屏（`100vh`）；输入区可折叠。 |
| NFR-6 | 简单可靠：单页、无多余依赖；构建产物不入库（`.gitignore` 排除 `build/`、`.gradle/`、`local.properties` 等）。 |
| NFR-7 | 中文界面。 |

## 7. 目录结构（与 SCF 代码隔离）

在仓库根目录下新建独立 Android 工程目录（建议名 `android/`），与现有 SCF 代码分离：

```
oc-stock-scf-1_event/
├─ index.py                # SCF 入口（现有）
├─ stock_kline.py          # SCF/CLI 核心（现有）
├─ requirements.txt        # SCF 依赖（现有）
├─ src/                    # SCF 部署根（现有）
├─ doc/                    # 文档（现有）
├─ AGENTS.md
└─ android/                # ★ 新增：Android Studio 工程（独立）
   ├─ settings.gradle(.kts)
   ├─ build.gradle(.kts)          # 工程级
   ├─ gradle.properties           # 放 SCF_BASE_URL 等可配置项
   ├─ gradle/wrapper/...
   ├─ gradlew / gradlew.bat
   └─ app/
      ├─ build.gradle(.kts)       # 模块级
      └─ src/main/
         ├─ AndroidManifest.xml
         ├─ java/<pkg>/MainActivity.kt
         └─ res/layout/activity_main.xml、values/strings.xml ...
```

要点：
- Android 工程与 SCF 代码物理隔离，互不干扰；根仓库 `.gitignore` 增补 Android 相关忽略项。

## 8. 接口约定（与 SCF 对接）

### 8.1 请求
- 方法：`GET`
- URL：`<SCF_BASE_URL>?ts_code=<代码>&start_date=<YYYYMMDD>&end_date=<YYYYMMDD>`
- 示例：`https://1480388537-j4cnl3240r.ap-guangzhou.tencentscf.com/?ts_code=000001.SZ&start_date=20250101&end_date=20260918`
- 当前 SCF 函数 URL：`https://1480388537-j4cnl3240r.ap-guangzhou.tencentscf.com`（**须可配置**，见 §9）

### 8.2 成功响应
- 状态码 `200`，`Content-Type: text/html; charset=utf-8`，body 为完整 K 线 HTML（移动版）。

### 8.3 错误响应
- `400` + HTML 辅助提示页（参数非法）；`500` + 文本（服务内部错误）。

### 8.4 平台行为（重要，App 侧须知晓）
- 实测函数 URL 会**强制** `Content-Disposition: attachment`，并**注入**默认 `Content-Type: application/json`，形成与 `text/html` 的**重复 Content-Type**。
- **影响**：浏览器直接访问会下载而非渲染；但 **App 用 OkHttp 读 body，`Content-Disposition` 无影响**——这正是选方案 B 的原因。
- **编码处理**：因存在重复 `Content-Type`，**不要依赖响应头猜编码**；应以 `response.body.bytes()` 读出后按 **UTF-8** 显式解码为字符串，再交给 WebView。

### 8.5 可选：自定义下载名（仅浏览器场景）
- 与 App 无关；如需在浏览器保存为指定名称，把文件名放 URL 末段（如 `.../kline_000001.SZ.html?ts_code=...`）。

## 9. 配置项设计（SCF_BASE_URL 可配置）

**决策：仅编译期配置（做法 A）。** 地址在构建期注入，不在 App 内提供运行期修改入口。

### 9.1 编译期默认值（Gradle → BuildConfig）
- 在 `android/gradle.properties` 定义：
  ```properties
  SCF_BASE_URL=https://1480388537-j4cnl3240r.ap-guangzhou.tencentscf.com
  ```
- 在 `app/build.gradle(.kts)` 用 `buildConfigField` 注入：
  ```
  buildConfigField "String", "SCF_BASE_URL", "\"${SCF_BASE_URL}\""
  ```
- 代码读取 `BuildConfig.SCF_BASE_URL`。
- 末尾多余 `/` 须归一化，避免出现 `//?ts_code=...`。

### 9.2 变更流程
- 换地址 = 修改 `gradle.properties` 的 `SCF_BASE_URL` → 重新构建 APK → 重新安装/发布。
- 不提供 App 内设置界面，也不使用 `SharedPreferences`。

## 10. UI 设计（单页）

```
┌─────────────────────────────┐
│  股票K线           [收起参数] │
├─────────────────────────────┤
│  股票代码 [ 600519.SH      ] │
│  开始日期 [ 20250101       ] │
│  结束日期 [ 20260918       ] │
│           [   确认   ]       │
├─────────────────────────────┤
│  （加载中显示进度指示）        │
│                             │
│     WebView（K线图，恰好一屏） │
│                             │
└─────────────────────────────┘
```

- 顶部为标题栏（标题 + "收起/展开"按钮）；其下为可折叠的参数区；下部为 `WebView` 区。
- 参数区默认展开；点确认且校验通过后自动收起，图表占满整屏（`WebView` 用 `layout_weight=1` 自动扩展）。
- 日期采用**纯文本框**输入 `YYYYMMDD`：`inputType=number`，限制 8 位数字，带格式提示文案。
- `WebView` 尺寸变化（折叠/展开、旋转）后需通知页面内 echarts 重排（派发 `window` 的 `resize` 事件）。
- 键盘输入完成后收起键盘再发起查询。

## 11. 技术选型

| 项 | 选择 | 说明 |
|---|---|---|
| 语言 | Kotlin | Android Studio 默认 |
| 构建 | Gradle（Kotlin DSL 或 Groovy） | Android Studio 原生 |
| HTTP | **OkHttp** | 异步、超时可控 |
| 渲染 | **WebView** | 复用 SCF 的 pyecharts HTML |
| 配置 | gradle.properties + BuildConfig | 见 §9（仅编译期） |
| 依赖注入 | 不引入 | 保持精简 |

WebView 关键配置：`javaScriptEnabled = true`、`domStorageEnabled = true`、`webViewClient = WebViewClient()`（站内加载）。

## 12. 验收标准

1. 用 Android Studio 打开 `android/` 能成功 Sync、Build、Run。
2. 输入合法代码与日期，点"确认"→ 自动收起参数区并显示 K 线四区，恰好一屏、无需滚动。
3. 输入非法代码/日期（如 `abc`、`2025-01-01`、`start>end`）→ 原生提示，不发起请求。
4. 断网或超时 → 原生错误提示，可重试。
5. 修改 `SCF_BASE_URL`（编译期）后，请求正确指向新地址。
6. 目录与 SCF 代码互不影响；构建产物未入库。

## 13. 非目标 / 后续迭代

- 原生图表渲染（需 SCF 提供 `format=json`）。
- 多股票对比、自选、历史查询、分享/导出。
- 横屏/平板专门布局。

## 14. 风险与依赖

| 风险 | 说明 | 应对 |
|---|---|---|
| echarts CDN 不可达 | 手机网络访问不到 `assets.pyecharts.org` → 图表白屏 | 保证网络；必要时 SCF 侧改自托管 JS |
| SCF 冷启动慢 | 首次请求可能超时 | 超时设 15~30s；可对 SCF 配置预置并发 |
| 函数 URL 变更 | 端点可能变化 | 已设计为可配置（§9） |
| 响应重复 Content-Type | 误用响应头判编码会乱码 | 按 UTF-8 显式解码（§8.4） |
| 四区图较挤 | 竖屏窄，坐标轴拥挤 | 依赖 SCF 侧 `MOBILE_CHART_HEIGHT` 与边距调优 |

## 15. 决策记录

**已确认**
- SCF_BASE_URL：**仅编译期配置**（做法 A，见 §9）。
- 日期输入：**纯文本框**（`YYYYMMDD`，带格式提示）。
- 工程目录：`android/`；包名：`com.example.stockkline`（默认）。
- 最低版本：`minSdk 24`（默认）。
