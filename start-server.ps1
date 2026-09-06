# Start App Server (SQLite persist, no Docker sandbox).
# Usage (repo root):  .\start-server.ps1
# Stop: Ctrl+C. Already-running :8765 will fail to bind — close the old process first.

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Backend = Join-Path $Root "backend"

$Candidates = @(
    (Join-Path $env:CONDA_PREFIX "python.exe"),
    "D:\miniconda3\envs\deepagents\python.exe",
    (Join-Path $env:USERPROFILE "miniconda3\envs\deepagents\python.exe"),
    (Join-Path $env:USERPROFILE "anaconda3\envs\deepagents\python.exe")
)
$Python = $Candidates | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1
if (-not $Python) {
    Write-Error "找不到 conda 环境 deepagents 的 python。先: conda activate deepagents"
}

$env:HARNESS_ENV = "production"
$env:HARNESS_SANDBOX = "false"

Set-Location $Backend
Write-Host "python  $Python"
Write-Host "config  HARNESS_ENV=$env:HARNESS_ENV  SANDBOX=$env:HARNESS_SANDBOX"
Write-Host "cwd     $Backend"
& $Python -m server @args
