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
- 历史说明：原 `policies/` 交易策略子包（MACD 买卖对、波段回测、日线/周线联合信号）、周线 resample（`generate_weekly_from_daily`）及 step5 `check_spec_day` 已于 2026-10 全部移除。

## 云函数部署（腾讯云 SCF）

- 方案与步骤详见 `doc/scf-refactor-plan.md`（改造方案）、`doc/scf-implementation-plan.md`（实施计划）。
- 要点：事件函数、运行时 **Python 3.10**、内存 512MB、执行超时 60s、环境变量 `TUSHARE_TOKEN` + `TZ=Asia/Shanghai`。
- Web IDE 的代码根目录是 **`src/`**（部署时把 `src/` 内容打包为 zip 根，执行方法仍是 `index.main_handler`）：把 `index.py` + `stock_kline.py` + `requirements.txt` 都放进 `src/`，终端执行 `cd src && pip install -r requirements.txt -t .`，确认出现 `pyecharts/ pandas/ tushare/ lxml/` 等目录后再点「部署」，最后创建函数 URL（公网 GET）。
- **安装依赖的 Python 版本必须与运行时一致**：运行时选 3.11 时，`lxml`/`pandas` 等二进制扩展会在云端 `ImportError: cannot import name 'etree' from 'lxml'`（Web IDE 装出的 `.so` 与运行时不匹配）；实测运行时用 **Python 3.10** 正常。
- 访问示例：`https://<url>/?ts_code=000001.SZ&start_date=20250101&end_date=20260918`

## 其他文件
- `doc/prework.md`：.venv 创建 / 依赖安装步骤（含阿里云镜像源）。
- `doc/py-sample.py`：pyecharts 版本 / 主题试验脚本。
