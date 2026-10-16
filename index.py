# 腾讯云函数 SCF 入口（事件函数 + 函数 URL 触发）
#
# 执行方法：index.main_handler
# 触发方式：函数 URL（GET、公网），query 参数兼容 apigw 格式，位于 event['queryString']
#   示例：https://<url>/?ts_code=600519.SH&start_date=20250101&end_date=20260918
# 返回：集成响应结构，statusCode 200 时 body 为生成的 kline_chart.html 完整内容；
#       ts_code 等参数非法（含中文股票名）时返回 400 + 辅助提示页（含代码格式与默认代码）。

from html import escape

from stock_kline import (
    var_ts_code,
    var_start_date,
    var_end_date,
    validate,
    generate_html,
)


VIEWPORT = '<meta name="viewport" content="width=device-width, initial-scale=1">'
RESET_CSS = '<style>html,body{margin:0;padding:0;height:100%;}</style>'


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


def _inject_viewport(html):
    return html.replace("<head>", "<head>\n" + VIEWPORT + RESET_CSS, 1)


def _help_page(message, ts_code):
    # 参数非法时的辅助提示页：说明 ts_code 格式，并给出默认股票代码与默认区间
    demo_url = (
        f"?ts_code={var_ts_code}"
        f"&start_date={var_start_date}&end_date={var_end_date}"
    )
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>股票代码提示 - K线图</title>
<style>
  body {{ font-family: -apple-system, "Microsoft YaHei", Arial, sans-serif; max-width: 720px; margin: 40px auto; padding: 0 20px; line-height: 1.7; color: #333; }}
  h1 {{ font-size: 20px; }}
  h2 {{ font-size: 16px; margin-top: 28px; }}
  code {{ background: #f2f3f5; padding: 2px 6px; border-radius: 4px; font-family: Consolas, monospace; }}
  table {{ border-collapse: collapse; width: 100%; margin: 12px 0; }}
  th, td {{ border: 1px solid #e0e0e0; padding: 8px 10px; text-align: left; }}
  th {{ background: #fafafa; }}
  .err {{ color: #c0392b; }}
  .btn {{ display: inline-block; margin-top: 12px; padding: 10px 18px; background: #1677ff; color: #fff; text-decoration: none; border-radius: 6px; }}
</style>
</head>
<body>
  <h1>股票代码填写有误</h1>
  <p class="err">{escape(message)}</p>
  <p>当前 <code>ts_code</code> 输入为：<code>{escape(ts_code)}</code>，无法识别。</p>

  <h2>股票代码格式：6 位数字 + 交易所后缀</h2>
  <table>
    <tr><th>交易所</th><th>后缀</th><th>示例</th></tr>
    <tr><td>上海证券交易所</td><td><code>.SH</code></td><td><code>600519.SH</code>（贵州茅台）</td></tr>
    <tr><td>深圳证券交易所</td><td><code>.SZ</code></td><td><code>000001.SZ</code>（平安银行）</td></tr>
    <tr><td>北京证券交易所</td><td><code>.BJ</code></td><td><code>430047.BJ</code></td></tr>
  </table>

  <h2>默认参数</h2>
  <p>股票代码：<code>{var_ts_code}</code>　起始日期：<code>{var_start_date}</code>　结束日期：<code>{var_end_date}</code></p>
  <a class="btn" href="{demo_url}">使用默认参数查看 K 线图</a>
</body>
</html>"""


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
