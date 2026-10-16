# AGENTS.md

保持所有的对话和交互，都使用中文。

## 环境与运行

- 依赖清单：
  - 本地：`doc/requirements_python.list`（pyecharts / tushare / pandas==3.0.2）。系统 Python 3.14 已装依赖可直接用，或按 `doc/prework.md` 自建 `.venv`。
  - 云端（SCF）：仓库根目录 `requirements.txt`（pandas==2.2.3，匹配 SCF Python 3.10 运行时；勿在 Windows 本地 `pip -t` 打包，须用 Web IDE 在线安装）。
- 仓库无测试 / lint / typecheck 配置。改动后验证方式：`python -m py_compile stock_kline.py index.py`，再实际运行主流程。
- **运行**（已实测，不带参数即可直接从 TuShare 读数据）：
  ```bash
  python stock_kline.py                                    # 默认股票/区间，从 TuShare 读数据并生成 kline_chart.html
  python stock_kline.py --ts-code 000001.SZ --start-date 20250101 --end-date 20260918
  ```
  - `--ts-code`（默认 600519.SH，格式 XXXXXX.SH/SZ/BJ）、`--start-date` / `--end-date`（YYYYMMDD，默认 20250101~20260918）可选。
  - 非法日期/代码或 start>end 会 `parser.error()` 退出（exit 2）。`python stock_kline.py --help` 查看说明。

## 关键事实（易踩坑）

- 图表输出：`draw_charts()` 渲染到唯一临时文件后**返回 HTML 字符串**（SCF 代码目录只读、仅 /tmp 可写，stock_kline.py:578）；CLI 把字符串写回 `kline_chart.html`。两者都在 `.gitignore` 中。
- TuShare Token：优先读环境变量 `TUSHARE_TOKEN`（云函数配置），本地未设置时用 `get_data_from_ts()` 内兜底值。
- **勿用 `ts.set_token()`**：它会把 token 写入 `~/tk.csv`（`tushare/util/upass.py` 用 `os.path.expanduser('~')`）；SCF 中 `HOME=/home/qcloud` 不存在且目录只读，pandas 写文件会抛 `Cannot save file into a non-existent directory: '/home/qcloud'`。正确做法是把 token 直接传给 `ts.pro_api(token)`（stock_kline.py:48），全程不落盘。
- 股票代码 / 日期范围的默认值在 stock_kline.py 全局 `var_ts_code`、`var_start_date`、`var_end_date`。
- 参数校验统一在 `validate(ts_code, start_date, end_date)`（抛 ValueError）；CLI 捕获后 `parser.error()`，云函数返回 400。
- 顶部有调试开关：`ENABLE_DBUG_GetData` / `ENABLE_DBUG_MainFlow`（默认 False），改行为先看这些开关。
- 控制台中文输出在 GBK 终端可能显示乱码，属编码问题，不是逻辑错误（云端 CLS 日志为 UTF-8，无此问题）。
- **函数 URL 会强制下载、不能内联渲染**：返回 HTML 时平台强制 `Content-Disposition: attachment` 并注入默认 `Content-Type: application/json`，覆盖函数返回的 `inline; filename=...`；浏览器直接访问会下载 HTML（非渲染）。下载名取 URL 末段（如 `.../kline_000001.SZ.html?ts_code=...`）。**不影响 WebView/OkHttp 取 body**（移动端方案 B）。详见 `doc/mobile-adaptation-plan.md`。

## 代码结构

两个 Python 文件：

- **`stock_kline.py`**（核心，CLI + 供云函数 import）：
  - 主流程：`generate_html(ts_code, start_date, end_date)` → `get_data_from_ts()` → `calc_zhibiao()` → `draw_charts()`（返回 HTML 字符串）。注意 `calc_zhibiao(p_df)` 入参名为 `p_df`。
  - 指标计算：MA、MACD、Boll、波段（自定义 J/D 指标），均基于日线。
  - 图表：`draw_charts()` 用 pyecharts Grid 输出 K线 + 成交量 + MACD + 波段四区，多图共缩放靠 `xaxis_index=[0,1,2,3]`。
  - `__main__`：argparse CLI，写回 `kline_chart.html`。
- **`index.py`**（腾讯云函数 SCF 入口）：
  - `main_handler(event, context)`：从 `event['queryString']` 取 `ts_code/start_date/end_date`（缺省用全局默认值），调 `generate_html()`。
  - 返回集成响应 `{isBase64Encoded, statusCode, headers, body}`：200 + `text/html`（完整 kline_chart.html 内容）、400 + `text/html`（参数非法/中文名时的辅助提示页，含代码格式与默认代码，`_help_page()`）、500（内部异常）。
  - 提示页须 >512 字节：浏览器对 4xx 且响应体 <512 字节的响应会丢弃内容、改显示自带错误页，故提示页要足够长才能被看到。
  - 执行方法 `index.main_handler`，触发方式为**函数 URL**（GET、公网）。**勿用 API 网关触发器**（2025-06-30 已下线）。
  - 移动适配：`main_handler` 调 `generate_html(..., mobile=True)`，注入 viewport meta + `html,body{margin:0;height:100%}` 复位样式，响应加 `Content-Disposition: inline` 与 CORS；`generate_html/draw_charts` 的 `mobile` 开关令图表 `width:100%/height:100vh`（=WebView 可视高度，恰好一屏；桌面 CLI 不传，行为不变）。
- 历史说明：原 `policies/` 交易策略子包（MACD 买卖对、波段回测、日线/周线联合信号）、周线 resample（`generate_weekly_from_daily`）及 step5 `check_spec_day` 已于 2026-10 全部移除。

## 云函数部署（腾讯云 SCF）

- 方案与步骤详见 `doc/scf-refactor-plan.md`（改造方案）、`doc/scf-implementation-plan.md`（实施计划）。
- 要点：事件函数、运行时 **Python 3.10**、内存 512MB、执行超时 60s、环境变量 `TUSHARE_TOKEN` + `TZ=Asia/Shanghai`。
- Web IDE 的代码根目录是 **`src/`**（部署时把 `src/` 内容打包为 zip 根，执行方法仍是 `index.main_handler`）：把 `index.py` + `stock_kline.py` + `requirements.txt` 都放进 `src/`，终端执行 `cd src && pip install -r requirements.txt -t .`，确认出现 `pyecharts/ pandas/ tushare/ lxml/` 等目录后再点「部署」，最后创建函数 URL（公网 GET）。
- **安装依赖的 Python 版本必须与运行时一致**：运行时选 3.11 时，`lxml`/`pandas` 等二进制扩展会在云端 `ImportError: cannot import name 'etree' from 'lxml'`（Web IDE 装出的 `.so` 与运行时不匹配）；实测运行时用 **Python 3.10** 正常。
- 访问示例：`https://<url>/?ts_code=000001.SZ&start_date=20250101&end_date=20260918`
- 自定义下载名（浏览器会下载而非渲染，见「关键事实」）：把文件名放 URL 末段，如 `https://<url>/kline_000001.SZ.html?ts_code=000001.SZ&start_date=...&end_date=...`
- 目前的函数URL（20261015）：
   https://1480388537-j4cnl3240r.ap-guangzhou.tencentscf.com
   https://1480388537-j4cnl3240r.ap-guangzhou.tencentscf.com/?ts_code=000001.SZ&start_date=20260501&end_date=20261016
   
## Android 客户端（`android/`）

- 独立的 Android Studio 工程（Kotlin），与 SCF 的 Python 代码**物理隔离**。需求见仓库根目录 `SRS_app.md`。
- 作用：单页输入 `股票代码 / 开始日期 / 结束日期` → 点确认 → **OkHttp** 异步 GET SCF 函数 URL → 取回 HTML → `WebView.loadDataWithBaseURL` 渲染（方案 B，复用 SCF 全部指标与图表）。
- 关键实现：`app/src/main/java/com/example/stockkline/MainActivity.kt`；客户端校验与 SCF `validate()` 一致（`\d{6}\.(SH|SZ|BJ)`、`YYYYMMDD`、`start<=end`）；响应体按 **UTF-8 显式解码**（平台会注入重复 `Content-Type`，勿依赖响应头猜编码）。
- **函数 URL 配置（仅编译期）**：`android/gradle.properties` 的 `SCF_BASE_URL` → `BuildConfig.SCF_BASE_URL`（`app/build.gradle.kts` 用 `buildConfigField` 注入）。换地址改这一处并重新构建。
- 版本：AGP 8.12.0 / Gradle 8.13 / Kotlin 2.2.10；`compileSdk 36`、`minSdk 24`、`targetSdk 34`（对齐本机 Android Studio `2025.3.1` 与已装 SDK 36，减少下载）。
- 本机无 Gradle CLI / Android SDK，**无法在此编译**；在 Android Studio 打开 `android/` 目录 Sync 后运行（版本与本机已缓存/已装的 Gradle 8.13、AGP 8.12.0、Kotlin 2.2.10、SDK 36 对齐）。

## 其他文件
- `SRS_app.md`：Android 客户端需求规格说明（SRS）。
- `doc/mobile-adaptation-plan.md`：SCF 移动端适配方案（含函数 URL 强制下载等实测结论）。
- `doc/prework.md`：.venv 创建 / 依赖安装步骤（含阿里云镜像源）。
- `doc/py-sample.py`：pyecharts 版本 / 主题试验脚本。
