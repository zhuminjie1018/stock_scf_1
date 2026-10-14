import pyecharts
import tushare as ts
import pandas as pd
from datetime import datetime, timedelta

from pyecharts import options as opts
from pyecharts.commons.utils import JsCode
from pyecharts.charts import Kline, Line, Bar,Grid

import sys
import os
import re
import argparse
import tempfile

#命令行参数说明 
#python stock_kline.py                              <- 默认直接从TuShare获取数据并做check
#  可选（与上面组合使用）：
#    --ts-code 000001.SZ        股票代码，默认 600519.SH
#    --start-date 20250101      起始日期 YYYYMMDD，默认 20250101
#    --end-date 20260918        结束日期 YYYYMMDD，默认 20260918

# 调试开关
ENABLE_DBUG_GetData = False
ENABLE_DBUG_MainFlow = False

#参考代码：Candlestick
# https://gallery.pyecharts.org/#/Candlestick/README
# https://gallery.pyecharts.org/#/Candlestick/professional_kline_chart?id=pyecharts-%e4%bb%a3%e7%a0%81-%e6%95%88%e6%9e%9c
#Grid的效果和代码参考
# https://gallery.pyecharts.org/#/Grid/grid_vertical

#代码参数：
# deepseek -> python3的pyecharts库中，请解释说明一下.set_series_opts的每个参数的含义

# 设定全局输入参数（缺省值，可被命令行 --ts-code/--start-date/--end-date 覆盖）
## Tushare获取数据的参数
var_ts_code    = '600519.SH'
var_start_date = '20250101'
var_end_date   = '20260918'

# 获取TuShare数据
def get_data_from_ts(ts_code, start_date, end_date):
    
    # Token设置：云函数用环境变量 TUSHARE_TOKEN，本地未设置时用兜底值。
    # 直接把 token 传给 pro_api()，不使用 ts.set_token()——后者会写 ~/tk.csv，
    # 在 SCF 只读环境会因主目录 /home/qcloud 不存在而报错（133账号的Token）。
    pro = ts.pro_api(os.environ.get('TUSHARE_TOKEN', 'f6cae19604ad4f04ef7a0c02527deb4d7de30da8d0add9d611b869b4'))
    #获取daily数据(ts_code,trade_date,open,high,low,close,pre_close,change,pct_chg,vol,amount)
    #      ts_code trade_date   open   high    low  close  pre_close  change  pct_chg         vol       amount
    #0   000001.SZ   20250127  11.38  11.55  11.38  11.47      11.34    0.13   1.1464  1151934.71  1324270.607
    df = pro.daily(ts_code=ts_code, start_date=start_date, end_date=end_date)
    if ENABLE_DBUG_GetData:
        print('--从tushare获取的数据（默认按日期倒序）---')
        print(df.head(3))
    
    #日期整形：20250630->2025-01-02
    df['trade_date'] = pd.to_datetime(df['trade_date'])     
    
    #数据排序-1：TuShare 返回的数据默认按日期倒序，用 sort_values() 按trade_date正序排列。
    df = df.sort_values('trade_date') 
    if ENABLE_DBUG_GetData:
        print('--按trade_date正序排列后的数据（原index没变）：--')
        print(df.head(3))
    
    #数据排序-2：接上述步骤继续按trade_date重新排序后，重新reset_index（drop=True, inplace=True）重构index并替换之前的index，使之和trade_date一致。
    df.reset_index(drop=True, inplace=True)
    if ENABLE_DBUG_GetData:
        print('--按trade_date重新排序后  & 重新reset_index（drop=True, inplace=True）之后的数据：--')
        print(df.head(3))    
        print()
        
    #list_date = df['trade_date'].dt.strftime('%Y-%m-%d').tolist()
    #print(list_date)               #['2025-01-02', '2025-01-03', '2025-01-06', ...,'2025-09-02']
    
    return df

#计算MA（收盘价的5日简单移动平均）
def calc_ma(p_df):
    p_df['MA5']  = p_df['close'].rolling(window= 5).mean()
    p_df['MA10'] = p_df['close'].rolling(window=10).mean()
    return p_df

#计算MACD指标
#参数:
#    p_df: 包含收盘价的DataFrame
#    fastperiod: 快速EMA周期（默认12）
#    slowperiod: 慢速EMA周期（默认26）
#    signalperiod: 信号线周期（默认9）
#返回:
#    添加了MACD相关列的DataFrame
def calc_macd(p_df, fastperiod=12, slowperiod=26, signalperiod=9):
    # 计算EMA
    p_EMA_12 = p_df['close'].ewm(span=fastperiod, adjust=False).mean()
    p_EMA_26 = p_df['close'].ewm(span=slowperiod, adjust=False).mean()
    # 计算DIF（差离值）
    p_dif = p_EMA_12 - p_EMA_26
    p_df['DIF'] = p_dif.__round__(3)
    # 计算DEA（信号线）
    p_dea = p_dif.ewm(span=signalperiod, adjust=False).mean()
    p_df['DEA'] = p_dea.__round__(3)
    # 计算MACD柱状图
    p_macd = 2 * (p_dif - p_dea)
    p_df['MACD'] = p_macd.__round__(3)
    # 计算MACD柱状图颜色（此处颜色代码暂未验证）
    #p_df['COLOR'] = ['#ef232a' if x >= 0 else '#14b143' for x in p_df['MACD']]
    return p_df

#  计算波段
def calc_boduan(p_df):
    ## 波段代码(THS指标源代码)
    ## VAR1:=(2*CLOSE+HIGH+LOW)/4;
    ## VAR2:=EMA(EMA(EMA(VAR1,4),4),4);
    ## J: (VAR2-REF(VAR2,1))/REF(VAR2,1)*100,COLORSTICK;    #此处REF是取前一天
    ## D: MA(J,3); 
    ## K: MA(J,1);
  
    VAR1 = (2*p_df['close']+p_df['high']+p_df['low'])/4
    VAR2 = VAR1.ewm(span=4, adjust=False).mean()
    VAR2 = VAR2.ewm(span=4, adjust=False).mean()
    VAR2 = VAR2.ewm(span=4, adjust=False).mean()    #按公式，计算3次EMA。

    J_data = ((VAR2-VAR2.shift(1)) / VAR2.shift(1) *100)
    D = J_data.rolling(3).mean().round(3)
    J = J_data.round(3)
    K = J.rolling(1).mean().round(3)   #K=J 可以不用输出 

    p_df['J'] = J
    p_df['D'] = D

    return p_df

#  计算boll指标值
def calc_boll(p_df):
    closes = p_df['close']
    # 计算中轨：20日简单移动平均线（SMA）
    middle_band = closes.rolling(window=20).mean()

    # 计算20日收盘价的标准差
    std_dev = closes.rolling(window=20).std()

    # 计算上轨和下轨，这里k=2
    k = 2
    upper_band = middle_band + (k * std_dev)
    lower_band = middle_band - (k * std_dev)

    # 将计算出的布林带值添加到原始的DataFrame中
    p_df['Upper'] =  upper_band.__round__(3)
    p_df['Mid']   = middle_band.__round__(3)
    p_df['Lower'] =  lower_band.__round__(3)
    
    return p_df

# 处理日线df数据，并计算各个指标值
def calc_zhibiao(p_df):
        
    # 2-1 计算涨幅
    p_df['rise'] =  (p_df['close'] - p_df['close'].shift(1))/p_df['close'].shift(1)

    # 2-2 计算MA（收盘价的5日简单移动平均）
    p_df = calc_ma(p_df)
    
    # 2-3 计算MACD
    p_df = calc_macd(p_df)

    # 2-4 计算波段
    p_df = calc_boduan(p_df)

    # 2-5 计算Boll指标
    p_df = calc_boll(p_df)
  
    return p_df


# 3 描画K线及各种计算指标图，返回HTML字符串
# 说明：SCF 代码目录只读、仅 /tmp 可写，故渲染到唯一临时文件后读回字符串并删除临时文件
def draw_charts(df):
    
    # 3-1. 准备K线数据
    xaxis_data = df['trade_date'].dt.strftime('%Y-%m-%d').tolist()
    kline_data = df[['open', 'close', 'low', 'high']].values.tolist()

    # 3-2. 绘制K线图
    kline = (
        Kline()
        .add_xaxis(xaxis_data)
        .add_yaxis(
            "KLINE CandleStick",                #series_name="XXXX"
            kline_data,
            itemstyle_opts=opts.ItemStyleOpts(    #ItemStyleOpts 图形样式。建议：不需额外进行设置，缺省的式样更好看。
                #color="#ec0000",                #柱体色，上升
                #color0="#00da3c",               #柱体色，下降
                #border_color="#8A0000",         #柱体边框+引线，上升
                #border_color0="#008F28",        #柱体边框+引线，下降
            ),
            
            #kline中画线
            markline_opts=opts.MarkLineOpts(
                #is_silent=True,                                        #是否不响应鼠标事件（缺省is_silent=False）
                symbol=["none", "none"],                                #首尾不显示符号。不设置的话，缺省首尾是点和箭头。
                data=[
                    opts.MarkLineItem(type_="max", value_dim="close"),  #画线，max(close)            
                    #opts.MarkLineItem(type_="average"),                #可画多条线，比如average线
                ]
            ),
            
        )   
        .set_global_opts(
            legend_opts=opts.LegendOpts(                
                    #is_show=False,        #is_show=False -> series_name="XXXX"不显示。此处为："KLINE CandleStick"（第一个参数）, 加上后续的"MA5","MA10"
                    pos_top=30, 
                    pos_left="center",            
            ),
            
            title_opts=opts.TitleOpts(title="Kline-基本示例(XX)"),   #Kline的Tiitle，缺省左上角
            xaxis_opts=opts.AxisOpts(is_scale=True),
            yaxis_opts=opts.AxisOpts(
                is_scale=True,                      #Y轴缩放，最大化显示Y轴有效数字区域
                splitarea_opts=opts.SplitAreaOpts(                              #???这个参数含义待调查
                    is_show=True, areastyle_opts=opts.AreaStyleOpts(opacity=1)  
                ),
            ),
            #datazoom_opts=[opts.DataZoomOpts(type_="inside")],    
            #datazoom_opts=[opts.DataZoomOpts(type_="slider",pos_left="20%",pos_right="20%",range_start=50,range_end=100)],  
                #type_="slider"，缺省：下方的横向slider选择缩放
                #type_="inside"，内置鼠标缩放（中间滚轮）
                #range_start=50,range_end=100，初始显示50%-100%的数据  
                #pos_left="20%",pos_right="20%",组件离容器左/右侧的距离
            
            datazoom_opts=[                    #同时设定2-N种缩放type：inside 和 slider，
                           
                    # 方法1：效果能预期显示。（https://gallery.pyecharts.org/#/Candlestick/professional_kline_chart 的示例）
                    #opts.DataZoomOpts(
                    #    is_show=False, type_="inside", xaxis_index=[0, 0], range_end=100   ##inside只控制0
                    #),
                    #opts.DataZoomOpts(
                    #    is_show=True, xaxis_index=[0, 1], pos_top="97%", range_end=100      #缺省是slider，控制0和1
                    #),
                    #opts.DataZoomOpts(
                    #    is_show=False, xaxis_index=[0, 2], range_end=100       #同时控制0和2
                    #),
                    
                    # 方法2: 多图共缩放(x轴)
                    opts.DataZoomOpts(
                        is_show=False,
                        type_="inside",
                        xaxis_index=[0,1,2,3],      #这是多图共缩放(x轴)的关键。同时控制多个图表的x轴，xaxis_index=[0, 1, 2]是3个.也可设置[0,2]之类
                        range_start=0,
                        range_end=100,
                    ),
                    opts.DataZoomOpts(
                        is_show=True,
                        type_="slider",
                        xaxis_index=[0,1,2,3],     #这是多图共缩放(x轴)的关键。同时控制多个图表的x轴，xaxis_index=[0, 1, 2]是3个.也可设置[0,2]之类
                        range_start=0,
                        range_end=100,
                    ),

            ],
            
            #提示框配置（触发方式、格式化等）, 鼠标移动时的浮动提示框（不配置的话，鼠标只有移动到柱体才会出现提示框）
            tooltip_opts=opts.TooltipOpts(
                trigger="axis",
                is_confine=True,  # 限制tooltip在图表区域内，防止超出边界
                formatter=JsCode("""
                    function(params) {
                        if (!params || params.length === 0) return '';
                        var date = params[0].axisValue || params[0].name || '';
                        var res = '<div style="margin-bottom:8px;font-weight:bold;">' + date + '</div>';
                        var shownSeries = {};
                        for (var i = 0; i < params.length; i++) {
                            var p = params[i];
                            if (!p.seriesName || p.value === undefined) continue;
                            if (shownSeries[p.seriesName]) continue;
                            shownSeries[p.seriesName] = true;
                            var val;
                            if (Array.isArray(p.value)) {
                                if (p.seriesName.indexOf('KLINE') !== -1) {
                                    val = p.value.slice(1).join(', ');
                                } else {
                                    val = p.value.length > 1 ? p.value[p.value.length - 1] : p.value[0];
                                }
                            } else {
                                val = p.value;
                            }
                            res += '<div style="margin:3px 0;">' + p.marker + p.seriesName + ': ' + val + '</div>';
                        }
                        return res;
                    }
                """),
                #axis_pointer_type="cross",  #line 单竖线；cross 十字交叉线，x轴数字也显示(多grid时，有时会遮挡，可以缺省设置会line)
                background_color="rgba(245, 245, 245, 0.8)",
                border_width=1,         #提示框边框
                border_color="#ccc",
                textstyle_opts=opts.TextStyleOpts(color="#000"),    #提示框内字体
            ),
            
            #视觉映射组件（用于颜色映射、区间筛选等）    
            #???在左下角显示一个 颜色的图例说明，以及?？（is_show=True可显示出来）
            visualmap_opts=opts.VisualMapOpts(
                is_show=False,
                dimension=2,
                series_index=5,
                is_piecewise=True,
                pieces=[
                    {"value": 1, "color": "#00da3c"},
                    {"value": -1, "color": "#ec0000"},
                ],
            ),
            
            #用于配置坐标轴指示器的类，它可以增强图表交互时的视觉反馈效果。 
            #??? tooltip_opts中设置后，感觉这个设置没效果？why
            axispointer_opts=opts.AxisPointerOpts(
                    is_show=True,
                    link=[{"xAxisIndex": "all"}],
                    label=opts.LabelOpts(background_color="#777"),
            ),

            #用于配置区域选择组件的选项，它允许用户通过鼠标拖动来选择图表中的特定区域。 （右上角4个框）
            brush_opts=opts.BrushOpts(
                x_axis_index="all",
                brush_link="all",
                out_of_brush={"colorAlpha": 0.1},
                brush_type="lineX",
            ),
            
        )
    )

    # 3-3. 添加MA线
    line = (
        Line()
        .add_xaxis(xaxis_data)
        .add_yaxis(
            "MA5", 
            df['MA5'].round(2).tolist(),
            is_smooth=True,
            is_hover_animation=False,
            linestyle_opts=opts.LineStyleOpts(width=3, opacity=0.5),
            label_opts=opts.LabelOpts(is_show=False),
        )
        .add_yaxis(
            "MA10", 
            df['MA10'].round(2).tolist(),
            is_smooth=True,
            is_hover_animation=False,
            linestyle_opts=opts.LineStyleOpts(width=3, opacity=0.5),
            label_opts=opts.LabelOpts(is_show=False),    
        )
        
        .set_series_opts(
            symbol= "none",    #隐藏数据点(缺省是小圆圈)。"None"的时候，label_opts无法显示。
            #symbol_size=5,    #数据点的大小。0 = none
            #label_opts=opts.LabelOpts(is_show=False)  #关闭标签显示。即：不显示每个点的数值（标签）。此处设置，能覆盖.add_yaxis()中的设置
        )
        
        #type_="category"：1.x 轴上的数据点是离散的类别（如名称、标签等）2.数据点会均匀分布在轴上 3.轴上的顺序和间距不代表数值关系，只是类别的排列
        #type_="value"：1.连续数值 2，按实际数值比例 3.温度、销售额 等
        .set_global_opts(
            xaxis_opts=opts.AxisOpts(type_="category")
        )
        
    )

    # 组合图表（Kline+Line）
    overlap_kline_line = kline.overlap(line)

    # 3-4. 添加成交量柱状图
    bar = ( 
        Bar()
        .add_xaxis(xaxis_data)
        .add_yaxis(
            "成交量", 
            df['vol'].tolist(),
            xaxis_index=1,
            yaxis_index=1,
            label_opts=opts.LabelOpts(is_show=False),
            itemstyle_opts=opts.ItemStyleOpts(    #ItemStyleOpts 图形样式。建议：不需额外进行设置，缺省的式样更好看。
                color="#050FCF7D",             
            )
            
        )
        
        #.set_series_opts(
        #    label_opts=opts.LabelOpts(is_show=False),  # 关键参数：关闭标签显示
        #    xaxis_index=1,
        #    yaxis_index=1,
        #)            
        .set_global_opts(
            xaxis_opts=opts.AxisOpts(
                type_="category",
                is_scale=True,
                grid_index=1,
                #split_number=20,
                #boundary_gap=False,

                axisline_opts=opts.AxisLineOpts(is_on_zero=False),
                splitline_opts=opts.SplitLineOpts(is_show=False),

                axistick_opts=opts.AxisTickOpts(is_show=False),     # 可选：隐藏刻度线
                axislabel_opts=opts.LabelOpts(is_show=False),        # 隐藏Bar的整个 X轴标     
                    
            ),    
            yaxis_opts=opts.AxisOpts(
                is_scale=True,
                grid_index=1,
                #split_number=2,

                axisline_opts=opts.AxisLineOpts(is_show=False),
                splitline_opts=opts.SplitLineOpts(is_show=False),
                
                axislabel_opts=opts.LabelOpts(is_show=False),  # 隐藏Y轴数字
                axistick_opts=opts.AxisTickOpts(is_show=False),  # 可选：隐藏刻度线
            ),
            legend_opts=opts.LegendOpts(is_show=False),                              # 隐藏Bar的legend_opts整个标签（Kline和Bar组合时，2个legend标签会挤在顶上一起）
        )
    )
  
    # 3-5. 添加MACD指标
    bar_2 = (
        Bar()
        .add_xaxis(xaxis_data)
        .add_yaxis(
            "MACD图", 
            df['MACD'].round(3).tolist(),
            xaxis_index=2,
            yaxis_index=2,
            label_opts=opts.LabelOpts(is_show=False),

            #方法1（无效）： =>初步确认，颜色按列表[]指定不生效。
            #itemstyle_opts=opts.ItemStyleOpts(color=colors),     # 传入颜色列表=>经测试，无效
            #itemstyle_opts=opts.ItemStyleOpts(color='#ef232a'),  # 指定单一颜色    =>有效
                        
            #方法2（有效）：JsCode实现颜色灵活控制，>0用红色， <0用绿色。                
            itemstyle_opts=opts.ItemStyleOpts(
                color=JsCode(
                        """
                        function(params) {
                            var colorList;
                            if (params.data >= 0) { colorList = 'orange'; } else { colorList = '#14b143'; }
                            return colorList;
                        }
                        """
                )
            ),
             
        )     
        .set_global_opts(
            xaxis_opts=opts.AxisOpts(
                type_="category",
                grid_index=2,
                axislabel_opts=opts.LabelOpts(is_show=False),
            ),
            yaxis_opts=opts.AxisOpts(
                grid_index=2,
                split_number=4,
                axisline_opts=opts.AxisLineOpts(is_on_zero=False),
                axistick_opts=opts.AxisTickOpts(is_show=False),
                splitline_opts=opts.SplitLineOpts(is_show=False),
                axislabel_opts=opts.LabelOpts(is_show=True),
            ),
            legend_opts=opts.LegendOpts(is_show=False),
        )           
    )
    
    
    # 标记策略抽取的点（rule1,2,3,···）
    markpoint_data = []
    for i in range(len(xaxis_data)):
        if (i >= 1 and
            df['DIF'].tolist()[i] >= df['DEA'].tolist()[i] and
            df['DIF'].tolist()[i-1] < df['DEA'].tolist()[i-1] and
            df['MACD'].tolist()[i] >= 0 and
            df['MA5'].tolist()[i] >= df['MA5'].tolist()[i-1]):
            markpoint_data.append(
                opts.MarkPointItem(
                    coord=[xaxis_data[i], df['DIF'].tolist()[i]],
                    symbol="arrow",
                    symbol_size=10,
                    itemstyle_opts=opts.ItemStyleOpts(color="blue"),
                )
            )

    line_2_MACD = (
        Line()
        .add_xaxis(xaxis_data=xaxis_data)
        .add_yaxis(
            series_name="DIF",
            y_axis=df['DIF'].round(3),
            xaxis_index=2,
            yaxis_index=2,
            linestyle_opts=opts.LineStyleOpts(color="red"),
            label_opts=opts.LabelOpts(is_show=False),
            markpoint_opts=opts.MarkPointOpts(data=markpoint_data),
        )
        .add_yaxis(
            series_name="DEA",
            y_axis=df['DEA'].round(3).tolist(),
            xaxis_index=2,
            yaxis_index=2,
            linestyle_opts=opts.LineStyleOpts(color="green"),
            label_opts=opts.LabelOpts(is_show=False),   #label_opts是 DEA数值，设置为不显示
        )
        .set_series_opts(
            symbol= "none",    #隐藏数据点(缺省是小圆圈)。"None"的时候，label_opts无法显示。
        )        
        .set_global_opts(legend_opts=opts.LegendOpts(is_show=False))
    )
 
    # 最下面的MACD柱状图和DEA/DIF折线图
    overlap_bar2_line2 = bar_2.overlap(line_2_MACD)       
    
    
    # 3-6. 添加波段指标
    line_BD = (
        Line()
        .add_xaxis(xaxis_data)
        .add_yaxis(
            "波段-J",
            df['J'].tolist(),  
            is_smooth= True,
            label_opts=opts.LabelOpts(is_show=False),    
                
        )
        .add_yaxis(
            "波段-D",
            df['D'].tolist(),    
            is_smooth= True,
            label_opts=opts.LabelOpts(is_show=False),                
        )    
        .set_series_opts(
            symbol= "none",    #隐藏数据点(缺省是小圆圈)。"None"的时候，label_opts无法显示。
        )        
        .set_global_opts(
            legend_opts=opts.LegendOpts(is_show=False),       #不显示legend_opts标签（series_name）
            xaxis_opts=opts.AxisOpts(
                axislabel_opts=opts.LabelOpts(is_show=False)  #不显示标签
            ),
        )
        
    )

    # 4. 用Grid，分屏显示Kline和Bar等各区域
    grid = (
        Grid(
            init_opts=opts.InitOpts(
                animation_opts=opts.AnimationOpts(animation=False),
            )        
        )
        
        #K线图区域（预留10%给x轴日期区域）
        .add(
            overlap_kline_line,
            #顶部起点0，往下45%
            grid_opts=opts.GridOpts(pos_left="10%", pos_right="10%", height="45%"),
        )
        #成交量区域
        .add(
            bar, 
            #距离顶部60%，往下10%
            grid_opts=opts.GridOpts(pos_left="10%", pos_right="10%", pos_top="60%", height="10%"),    
        )
        #MACD区域
        .add(
            overlap_bar2_line2,
            #距离顶部70%，往下10%
            grid_opts=opts.GridOpts(pos_left="10%", pos_right="10%", pos_top="70%", height="10%"),                 
        )
        #波段区域
        .add(
            line_BD,
            #距离顶部80%，往下10%
            grid_opts=opts.GridOpts(pos_left="10%", pos_right="10%", pos_top="80%", height="10%"),
        )
        #slider区域（最后）
        #缺省占据高度大概90往下10。所以，之前的pos_top+height到90%比较合适，预留10%的slider空间
    )
    render_path = os.path.join(tempfile.gettempdir(), f"kline_{os.getpid()}_{id(df)}.html")
    grid.render(render_path)
    with open(render_path, encoding="utf-8") as f:
        html = f.read()
    try:
        os.remove(render_path)
    except OSError:
        pass
    return html

# 校验输入参数（ts_code/start_date/end_date），非法时抛 ValueError
def validate(ts_code, start_date, end_date):
    if not re.fullmatch(r'\d{6}\.(SH|SZ|BJ)', ts_code):
        raise ValueError(f'ts-code 格式不正确: {ts_code}（应为 XXXXXX.SH/SZ/BJ，如 600519.SH）')
    for name, value in (('start_date', start_date), ('end_date', end_date)):
        try:
            datetime.strptime(value, '%Y%m%d')
        except ValueError:
            raise ValueError(f'{name.replace("_", "-")} 日期格式不正确或日期非法: {value}（应为 YYYYMMDD）')
    if start_date > end_date:
        raise ValueError(f'start-date({start_date}) 不能晚于 end-date({end_date})')

# 核心流水线：取数 -> 计算指标 -> 生成图表HTML（CLI 与云函数共用）
def generate_html(ts_code, start_date, end_date):
    validate(ts_code, start_date, end_date)
    df = get_data_from_ts(ts_code, start_date, end_date)
    if ENABLE_DBUG_MainFlow:
        print(df.head(3))
        print(df.tail(3))
        print()

    df = calc_zhibiao(df)
    if ENABLE_DBUG_MainFlow:
        print(df.head(5))
        print(df.tail(5))
        print()

    return draw_charts(df)

if __name__ == "__main__":

    # 解析命令行参数
    parser = argparse.ArgumentParser(
        description='K线指标计算与策略回测',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            '示例:\n'
            '  python stock_kline.py                从 tushare 读数据并做 check\n'
            '  python stock_kline.py --ts-code 000001.SZ --start-date 20250101 --end-date 20260918\n'
            '                                       分析指定股票与日期区间'
        ),
    )
    parser.add_argument(
        '--ts-code',
        default=var_ts_code,
        help=f'股票代码，格式 XXXXXX.SH/SZ/BJ，默认 {var_ts_code}',
    )
    parser.add_argument(
        '--start-date',
        default=var_start_date,
        help=f'起始日期 YYYYMMDD，默认 {var_start_date}',
    )
    parser.add_argument(
        '--end-date',
        default=var_end_date,
        help=f'结束日期 YYYYMMDD，默认 {var_end_date}',
    )
    args = parser.parse_args()

    # 参数校验（与云函数共用 validate()，CLI 侧转为 parser.error 退出）
    try:
        validate(args.ts_code, args.start_date, args.end_date)
    except ValueError as e:
        parser.error(str(e))

    # 取数 -> 计算指标 -> 生成图表HTML（generate_html 内含 debug 打印）
    html = generate_html(args.ts_code, args.start_date, args.end_date)

    # 输出到图表文件（本地使用习惯不变）
    with open("kline_chart.html", "w", encoding="utf-8") as f:
        f.write(html)
