
import pyecharts

#输出pyecharts的版本号
print(pyecharts.__version__)

from pyecharts.globals import ThemeType

# 内置主题类型可查看 pyecharts.globals.ThemeType
print([item for item in dir(ThemeType) if not item.startswith('_')])
