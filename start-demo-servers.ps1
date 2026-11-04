$ErrorActionPreference = 'Stop'
$ProjectPath = $PSScriptRoot
$PythonPath = 'D:\venvs\ecommerce-analytics-agent\Scripts\python.exe'
$env:TEMP = 'D:\temp'
$env:TMP = 'D:\temp'
$env:PYTHONIOENCODING = 'utf-8'
$RuntimePath = Join-Path $ProjectPath 'outputs\runtime'
New-Item -ItemType Directory -Path $RuntimePath -Force | Out-Null
if (-not (Get-NetTCPConnection -LocalPort 8522 -State Listen -ErrorAction SilentlyContinue)) {
    Start-Process -FilePath $PythonPath -ArgumentList @('-m','http.server','8522','--bind','127.0.0.1','--directory','docs') -WorkingDirectory $ProjectPath -WindowStyle Hidden -RedirectStandardOutput (Join-Path $RuntimePath 'showcase.log') -RedirectStandardError (Join-Path $RuntimePath 'showcase-error.log') | Out-Null
}
if (-not (Get-NetTCPConnection -LocalPort 8521 -State Listen -ErrorAction SilentlyContinue)) {
    Start-Process -FilePath $PythonPath -ArgumentList @('-m','streamlit','run','app.py','--server.address','127.0.0.1','--server.port','8521','--server.headless','true','--browser.gatherUsageStats','false') -WorkingDirectory $ProjectPath -WindowStyle Hidden -RedirectStandardOutput (Join-Path $RuntimePath 'workbench.log') -RedirectStandardError (Join-Path $RuntimePath 'workbench-error.log') | Out-Null
}
Write-Output 'Local previews: http://127.0.0.1:8522 and http://127.0.0.1:8521'
