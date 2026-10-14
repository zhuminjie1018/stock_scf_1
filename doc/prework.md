
# 安装.venv

# 激活 .venv
.\.venv\Scripts\Activate.ps1

# 安装依赖包
pip install tushare 
pip install -r ./doc/requirements_python.list 
pip install -r ./doc/requirements_python.list -i https://mirrors.aliyun.com/pypi/simple/ 

# 查看依赖包版本号
pip show tushare
