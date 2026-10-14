# 改造方案：stock-kline → 腾讯云函数（返回 kline_chart.html）

> 生成日期：2026-10-14
> 配套实施计划：`doc/scf-implementation-plan.md`

## 一、选型结论

| 决策项 | 选择 | 理由 |
|---|---|---|
| 函数类型 | **事件函数**（非 Web 函数） | 无需写 Web Server/监听 9000/scf_bootstrap，改动最小 |
| 触发方式 | **函数 URL**（GET、公网） | API 网关触发器 2025-06-30 已下线，不可新建；函数 URL 是官方指定替代且"兼容 apigw 响应集成，无需改造" |
| 响应格式 | 集成响应结构 | 返回 `Content-Type: text/html` 的完整页面，浏览器直接渲染 |
| 参数化 | 支持 URL query 参数 | `?ts_code=000001.SZ&start_date=...&end_date=...`，缺省用现有默认值 |
| 依赖打包 | **方式 A：控制台 Web IDE 在线安装** | 无需本地 Linux/Docker，环境天然匹配 SCF（CentOS 7） |
| 本地 CLI | **保留** | 重构共用函数，`python stock_kline.py` 仍生成 `kline_chart.html`，现有使用习惯与 AGENTS.md 验证流程不变 |

### 已确认的两个关键决策

1. **依赖打包方式 A（Web IDE 在线安装）**：创建函数后在控制台 Web IDE 终端执行 `pip install -r requirements.txt -t .`，无需本地 Linux/Docker。
2. **保留本地命令行用法**：重构 `generate_html()` 供 CLI 与云函数两边共用，CLI 只是把返回的 HTML 写回文件。

## 二、响应格式

函数 URL / 事件函数返回集成响应结构：

```json
{
  "isBase64Encoded": false,
  "statusCode": 200,
  "headers": { "Content-Type": "text/html; charset=utf-8" },
  "body": "<!DOCTYPE html>...kline_chart.html 全文..."
}
```

## 三、架构与数据流

```
浏览器 GET https://<函数URL>/?ts_code=600519.SH&start_date=20250101&end_date=20260918
        │
        ▼
   函数 URL（公网 GET，兼容 apigw 集成响应）
        │  event = { queryString: {...}, headers, httpMethod, path, body }
        ▼
   index.py: main_handler(event, context)
        │  1. 从 event['queryString'] 取参数（缺省用全局默认值）
        │  2. validate() 校验（复用原 argparse 校验逻辑）
        │  3. 调用 generate_html()
        ▼
   stock_kline.py: generate_html(ts_code, start_date, end_date) -> str
        │  get_data_from_ts()  → TuShare 拉日线（token 来自环境变量）
        │  calc_zhibiao()      → MA/MACD/波段/Boll
        │  draw_charts()       → 渲染到 /tmp 临时文件 → 读回字符串 → 删除
        ▼
   返回 { statusCode:200, headers:{"Content-Type":"text/html; charset=utf-8"}, body:html }
        │
        ▼
   浏览器渲染 K线四区（echarts JS 走 assets.pyecharts.org CDN，浏览器端加载）
```

## 四、关键注意点（风险）

- **勿选"API 网关触发器"**：2025-06-30 已下线，控制台可能不可见；只用函数 URL。
- **SCF 代码目录只读，仅 `/tmp` 可写**：`grid.render()` 不能写当前目录，需渲染到唯一临时文件后读回。
- **依赖不能在 Windows 本地 `pip install -t .` 打包**：会装成 win_amd64 二进制（pandas/numpy），在 SCF（CentOS 7）上直接 `ImportError`。已选 Web IDE 在线安装规避。
- **pandas 版本需匹配云函数 Python 运行时**：SCF 文档当前列出的最高版本为 Python 3.10（以控制台实际可选为准）。pandas 3.0.2 要求 Python ≥3.11，若运行时仅 3.10，需降为 `pandas==2.2.3`（本项目只用了 rolling/ewm/groupby 等基础 API，2.x 完全兼容）。
- **同步响应上限 6MB**：pyecharts HTML 引用 CDN 不内嵌 JS，体积仅数百 KB，无风险。
- **`/tmp` 写满问题**：用唯一文件名 + 用后即删。
- **计费**：调用次数 + 计算时长 + 公网出流量（tushare 请求 + HTML 响应）。
- **Token 安全**：硬编码 token 改为环境变量 `TUSHARE_TOKEN`，本地保留兜底值。
- **时区**：SCF 默认 UTC，需配置环境变量 `TZ=Asia/Shanghai`。
- **超时**：默认 3s 不够（冷启动 import + tushare 网络请求），执行超时设 60s，初始化超时 60~120s。
- **内存**：pandas 计算建议 512MB。
- **控制台中文日志**：云端 UTF-8，无本地 GBK 乱码问题。

## 五、云端配置概要

1. **创建函数**：Serverless 控制台 → 新建 → 自定义创建 → 事件函数，运行环境 Python 3.10（以实际为准），执行方法 `index.main_handler`
2. **资源配置**：内存 512MB、执行超时 60s、初始化超时 60~120s
3. **环境变量**：`TUSHARE_TOKEN=<你的token>`、`TZ=Asia/Shanghai`
4. **代码部署**：Web IDE 上传代码 + `pip install -r requirements.txt -t .` → 部署
5. **创建函数 URL**：函数详情 → 触发管理/函数 URL → 创建 → 访问类型选公网、方法 GET → 记录默认域名 URL
6. （可选）预置并发 1~2，缓解冷启动首访慢

## 六、测试与验证

1. 控制台"测试"→ 选函数 URL 事件模板 → 确认返回体含完整 HTML
2. 浏览器访问：
   - `https://<url>/`（默认 600519.SH）
   - `https://<url>/?ts_code=000001.SZ&start_date=20250101&end_date=20260918`
   - 确认 K线四区正常渲染
3. 异常参数访问，确认返回 400 文本
4. 日志：CLS 查看 print 输出
5. 本地回归：`python -m py_compile stock_kline.py index.py` + `python stock_kline.py` 确认仍生成 `kline_chart.html`

## 七、参考资料

- API 网关触发器功能下线通知：https://cloud.tencent.com/document/product/583/107631
- 函数 URL 概述：https://cloud.tencent.com/document/product/583/96099
- 云函数依赖安装：https://cloud.tencent.com/document/product/583/39780
- 云函数环境说明 - Python：https://cloud.tencent.com/document/product/583/55592
