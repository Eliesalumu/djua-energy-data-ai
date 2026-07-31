param(
    [string]$DeviceId = ""
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$PythonPath = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$DatasetPath = Join-Path $ProjectRoot "data\generated\mvp_dataset.csv"
$CliPath = Join-Path $ProjectRoot "scripts\predict_device_cli.py"

Write-Host ""
Write-Host "DJUA ENERGY - DEMO IA PAR DEVICE" -ForegroundColor Cyan
Write-Host "================================" -ForegroundColor Cyan
Write-Host ""

if (-not (Test-Path $PythonPath)) {
    Write-Host "Python virtuel introuvable : $PythonPath" -ForegroundColor Red
    Write-Host "Lance d'abord : .\scripts\create_venv.ps1"
    exit 1
}

if (-not (Test-Path $DatasetPath)) {
    Write-Host "Dataset introuvable : $DatasetPath" -ForegroundColor Red
    Write-Host "Lance d'abord : .\.venv\Scripts\python.exe scripts\generate_synthetic_data.py"
    exit 1
}

if ([string]::IsNullOrWhiteSpace($DeviceId)) {
    $DeviceId = Read-Host "Entre le device a analyser, par exemple device-2"
}

Write-Host ""
Write-Host "Analyse IA en cours pour $DeviceId ..." -ForegroundColor Yellow
Write-Host ""

Push-Location $ProjectRoot
try {
    & $PythonPath $CliPath --jury --device $DeviceId
}
finally {
    Pop-Location
}
