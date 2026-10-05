# Start the App Server with the project's uv-managed virtual environment.
# Usage (repo root): .\start-server-uv.ps1 [--host 127.0.0.1] [--port 8765]
# Stop: Ctrl+C

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Backend = Join-Path $Root "backend"
$Python = Join-Path $Backend ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $Python)) {
    Write-Error "未找到 uv 虚拟环境：$Python`n请先在 backend 目录执行：uv sync --extra dev --extra persist"
}

$env:HARNESS_ENV = "production"
$env:HARNESS_SANDBOX = "false"

Set-Location $Backend
Write-Host "python  $Python"
Write-Host "config  HARNESS_ENV=$env:HARNESS_ENV  SANDBOX=$env:HARNESS_SANDBOX"
Write-Host "cwd     $Backend"

& $Python -m server @args
exit $LASTEXITCODE
