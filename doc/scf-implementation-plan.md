# 实施计划：stock-kline → 腾讯云函数

> 生成日期：2026-10-14
> 配套改造方案：`doc/scf-refactor-plan.md`

## 阶段 1：本地代码改造

### 1.1 重命名主文件

- `stock-kline.py` → `stock_kline.py`
- 原因：Python 模块名不能含连字符，否则 `index.py` 无法 import

### 1.2 改造 `draw_charts(df)`

- 现状：固定写 `kline_chart.html`（`grid.render("kline_chart.html")`）
- 改为：渲染到 `/tmp` 唯一临时文件 → 读回 HTML 字符串 → 删除临时文件 → `return html`

```python
import tempfile, os

def draw_charts(df) -> str:
    ...（图表构建不变）...
    path = os.path.join(tempfile.gettempdir(), f"kline_{os.getpid()}_{id(df)}.html")
    grid.render(path)
    with open(path, encoding="utf-8") as f:
        html = f.read()
    os.remove(path)
    return html
```

要点：
- SCF 代码目录只读，**只有 `/tmp` 可写**
- 唯一文件名避免并发覆盖/残留写满 `/tmp`

### 1.3 新增核心流水线函数 `generate_html()`

```python
def generate_html(ts_code, start_date, end_date) -> str:
    df = get_data_from_ts(ts_code, start_date, end_date)
    df = calc_zhibiao(df)
    return draw_charts(df)
```

供 CLI 与云函数两边共用。

### 1.4 Token 改为环境变量

```python
ts.set_token(os.environ.get('TUSHARE_TOKEN', 'f6cae1...'))  # 云上用环境变量，本地兜底
```

### 1.5 保留本地 CLI（`__main__`）

- argparse/参数校验逻辑不变
- 将原校验逻辑抽成 `validate(ts_code, start_date, end_date)` 函数复用（CLI 内仍可 `parser.error()`，云函数侧改为抛 `ValueError`）
- 最后把 `generate_html()` 返回的字符串写回 `kline_chart.html`（本地使用习惯不变）

```python
html = generate_html(args.ts_code, args.start_date, args.end_date)
with open("kline_chart.html", "w", encoding="utf-8") as f:
    f.write(html)
```

### 1.6 新建 `index.py`（SCF 入口）

```python
def main_handler(event, context):
    try:
        qs = (event or {}).get('queryString') or {}
        ts_code    = qs.get('ts_code',    var_ts_code)
        start_date = qs.get('start_date', var_start_date)
        end_date   = qs.get('end_date',   var_end_date)
        validate(ts_code, start_date, end_date)      # 复用原校验逻辑，失败抛 ValueError
        html = generate_html(ts_code, start_date, end_date)
        return {"isBase64Encoded": False, "statusCode": 200,
                "headers": {"Content-Type": "text/html; charset=utf-8"},
                "body": html}
    except ValueError as e:
        return {"isBase64Encoded": False, "statusCode": 400,
                "headers": {"Content-Type": "text/plain; charset=utf-8"},
                "body": f"参数错误: {e}"}
    except Exception as e:
        return {"isBase64Encoded": False, "statusCode": 500,
                "headers": {"Content-Type": "text/plain; charset=utf-8"},
                "body": f"服务内部错误: {e}"}
```

要点：
- 函数 URL 的 query 参数在 `event['queryString']`（兼容 apigw 格式）
- 400（参数错误）/ 500（内部异常）返回 `text/plain`

### 1.7 依赖清单

- 新建 `requirements.txt`（云函数用）：
  ```
  pyecharts==2.1.0
  tushare==1.4.29
  pandas==2.2.3    # 若 SCF 运行时为 Python 3.10；若控制台提供 ≥3.11 可用 3.0.2
  ```
- 与 `doc/requirements_python.list`（本地 pandas==3.0.2）的差异需注明
- 同步更新 `doc/requirements_python.list` 说明

### 1.8 更新 `AGENTS.md`

- 文件名 `stock-kline.py` → `stock_kline.py`
- 新增 `index.py` SCF 入口说明
- 云函数部署/验证方式
- requirements 差异说明（本地 vs 云）
- 更新运行命令示例

### 1.9 本地验证

```bash
python -m py_compile stock_kline.py index.py
python stock_kline.py            # 确认仍生成 kline_chart.html
python stock_kline.py --ts-code 000001.SZ --start-date 20250101 --end-date 20260918
```

## 阶段 2：云端部署（控制台操作清单）

### 2.1 创建函数

1. Serverless 控制台 → 新建 → 自定义创建
2. 函数类型：**事件函数**
3. 运行环境：**Python 3.10**（以控制台实际可选为准）
4. 执行方法：`index.main_handler`

### 2.2 资源配置

| 配置项 | 值 | 说明 |
|---|---|---|
| 内存 | 512MB | pandas 计算需要 |
| 执行超时 | 60s | 默认 3s 不够（冷启动 import + tushare 请求） |
| 初始化超时 | 60~120s | 冷启动加载依赖 |

### 2.3 环境变量

| Key | Value |
|---|---|
| `TUSHARE_TOKEN` | 你的 TuShare token |
| `TZ` | `Asia/Shanghai`（SCF 默认 UTC） |

### 2.4 代码部署（Web IDE 在线安装依赖）

1. Web IDE 打开函数项目
2. 上传 `index.py`、`stock_kline.py`、`requirements.txt` 到代码根目录
   （注意：入口文件必须在 zip/代码包**根目录**）
3. Web IDE 终端执行：
   ```bash
   pip install -r requirements.txt -t .
   ```
   （Web IDE 环境与 SCF 运行环境一致，规避 Windows 打包二进制不兼容问题）
4. 点击"部署"

### 2.5 创建函数 URL

1. 函数详情 → 触发管理 / 函数 URL
2. 创建函数 URL：访问类型选**公网**、方法 **GET**
3. 记录默认域名 URL
4. **不要创建 API 网关触发器**（2025-06-30 已下线）

### 2.6 可选优化

- 预置并发 1~2，缓解冷启动首访慢

## 阶段 3：测试与验证

1. **控制台测试**："测试"→ 选函数 URL 事件模板 → 确认返回体含完整 HTML
2. **浏览器访问**：
   - `https://<url>/`（默认 600519.SH）
   - `https://<url>/?ts_code=000001.SZ&start_date=20250101&end_date=20260918`
   - 确认 K线四区（K线+成交量+MACD+波段）正常渲染
3. **异常路径**：访问非法参数（如 `?ts_code=xxx`）确认返回 400 文本；制造内部错误确认 500
4. **日志**：CLS 查看 print 输出（云端 UTF-8，无 GBK 乱码问题）
5. **本地回归**：`python -m py_compile stock_kline.py index.py` + `python stock_kline.py` 确认仍生成 `kline_chart.html`

## 交付物清单

| 文件 | 类型 | 说明 |
|---|---|---|
| `stock_kline.py` | 改造 | 原 stock-kline.py 重命名；draw_charts 返回字符串；新增 generate_html/validate；CLI 保留 |
| `index.py` | 新增 | SCF 入口 `main_handler`，集成响应 |
| `requirements.txt` | 新增 | 云函数依赖清单 |
| `AGENTS.md` | 更新 | 文件名、入口、部署/验证方式 |
| `doc/requirements_python.list` | 更新 | 注明本地与云的 pandas 版本差异 |
| `doc/scf-refactor-plan.md` | 新增 | 改造方案 |
| `doc/scf-implementation-plan.md` | 新增 | 本文档 |
