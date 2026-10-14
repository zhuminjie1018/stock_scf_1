# 腾讯云函数 SCF 入口（事件函数 + 函数 URL 触发）
#
# 执行方法：index.main_handler
# 触发方式：函数 URL（GET、公网），query 参数兼容 apigw 格式，位于 event['queryString']
#   示例：https://<url>/?ts_code=600519.SH&start_date=20250101&end_date=20260918
# 返回：集成响应结构，body 为生成的 kline_chart.html 完整内容

from stock_kline import (
    var_ts_code,
    var_start_date,
    var_end_date,
    validate,
    generate_html,
)


def _resp(status_code, content_type, body):
    return {
        "isBase64Encoded": False,
        "statusCode": status_code,
        "headers": {"Content-Type": content_type},
        "body": body,
    }


def main_handler(event, context):
    try:
        qs = (event or {}).get("queryString") or {}
        ts_code = qs.get("ts_code") or var_ts_code
        start_date = qs.get("start_date") or var_start_date
        end_date = qs.get("end_date") or var_end_date

        html = generate_html(ts_code, start_date, end_date)
        return _resp(200, "text/html; charset=utf-8", html)
    except ValueError as e:
        return _resp(400, "text/plain; charset=utf-8", f"参数错误: {e}")
    except Exception as e:
        return _resp(500, "text/plain; charset=utf-8", f"服务内部错误: {e}")
