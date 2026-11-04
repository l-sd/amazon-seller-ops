$ErrorActionPreference = 'Stop'
$ProjectPath = $PSScriptRoot
$PythonPath = 'D:\venvs\ecommerce-analytics-agent\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $PythonPath)) {
    throw '未找到已有运行环境，请按照 README 配置 D 盘运行环境。'
}
$env:TEMP = 'D:\temp'
$env:TMP = 'D:\temp'
$env:PYTHONIOENCODING = 'utf-8'
$env:STREAMLIT_BROWSER_GATHER_USAGE_STATS = 'false'
Set-Location -LiteralPath $ProjectPath
& $PythonPath -m streamlit run app.py --server.address 127.0.0.1 --server.port 8521 --browser.gatherUsageStats false
if ($LASTEXITCODE -ne 0) { throw '工作台启动失败，请检查报错或端口占用。' }
