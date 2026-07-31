param(
    [int]$Devices = 6,
    [int]$Cycles = 0,
    [int]$IntervalSeconds = 300,
    [double]$SleepSeconds = 0
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$PythonPath = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$ScriptPath = Join-Path $ProjectRoot "scripts\simulate_fleet_realtime.py"

Write-Host ""
Write-Host "DJUA ENERGY - INTERNATIONAL JURY REALTIME FLEET DEMO" -ForegroundColor Cyan
Write-Host "====================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "This demo simulates several installed devices." -ForegroundColor White
Write-Host "Every simulated tick sends a complete telemetry payload per device." -ForegroundColor White
Write-Host "The API stores telemetry, runs the trained AI models, saves predictions, and updates device state." -ForegroundColor White
Write-Host ""

if (-not (Test-Path $PythonPath)) {
    Write-Host "Virtual Python not found: $PythonPath" -ForegroundColor Red
    Write-Host "Run first: .\scripts\create_venv.ps1"
    exit 1
}

Push-Location $ProjectRoot
try {
    & $PythonPath $ScriptPath --devices $Devices --cycles $Cycles --interval-seconds $IntervalSeconds --sleep-seconds $SleepSeconds
}
finally {
    Pop-Location
}
