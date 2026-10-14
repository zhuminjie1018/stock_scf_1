import tushare as ts
import pandas as pd

ENABLE_DBUG = True

if ENABLE_DBUG:
    print("Tushare script executed.")

ts.set_token('f6cae19604ad4f04ef7a0c02527deb4d7de30da8d0add9d611b869b4')
pro = ts.pro_api()

if __name__ == "__main__":
    var_ts_code    = '600519.SH'
    var_start_date = '20250101'
    var_end_date   = '20260428'
    df = pro.daily(ts_code=var_ts_code, start_date=var_start_date, end_date=var_end_date)

    if ENABLE_DBUG:
        print(df.head(3))       #缺省未排序处理的话，head是最新的3日的。倒序。
        print(df.tail(3))
        print("数据获取完成。")



