param(
    [string]$Phone = "",
    [ValidateSet("bon", "moyen", "risque")]
    [string]$Scenario = "moyen",
    [string]$ExternalApiBaseUrl = "",
    [string]$Question = "",
    [switch]$UseOpenAI,
    [switch]$NoOpenAI,
    [switch]$RequireOpenAI
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$PythonPath = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$CliPath = Join-Path $ProjectRoot "scripts\customer_scoring_chat_cli.py"
$ModelPath = Join-Path $ProjectRoot "artifacts\customer_scoring_model.joblib"
$TrainPath = Join-Path $ProjectRoot "scripts\train_scoring.py"

Write-Host ""
Write-Host "DJUA ENERGY - CHAT IA SCORING CLIENT" -ForegroundColor Cyan
Write-Host "====================================" -ForegroundColor Cyan
Write-Host ""

if (-not (Test-Path $PythonPath)) {
    Write-Host "Python virtuel introuvable : $PythonPath" -ForegroundColor Red
    Write-Host "Lance d'abord : .\scripts\create_venv.ps1"
    exit 1
}

Push-Location $ProjectRoot
try {
    if (-not (Test-Path $ModelPath)) {
        Write-Host "Modele scoring absent. Entrainement automatique..." -ForegroundColor Yellow
        & $PythonPath $TrainPath
        Write-Host ""
    }

    $arguments = @($CliPath, "--scenario", $Scenario)
    if (-not [string]::IsNullOrWhiteSpace($Phone)) {
        $arguments += @("--phone", $Phone)
    }
    if (-not [string]::IsNullOrWhiteSpace($ExternalApiBaseUrl)) {
        $arguments += @("--external-api-base-url", $ExternalApiBaseUrl)
    }
    if (-not [string]::IsNullOrWhiteSpace($Question)) {
        $arguments += @("--question", $Question)
    }
    $OpenAIKeyDetected = -not [string]::IsNullOrWhiteSpace($env:OPENAI_API_KEY)

    if ($OpenAIKeyDetected -and -not $NoOpenAI) {
        Write-Host "OPENAI_API_KEY detectee : OpenAI sera utilise en mode strict." -ForegroundColor Green
        Write-Host ""
        $arguments += "--llm"
        $arguments += "--require-llm"
    }
    elseif ($UseOpenAI) {
        $arguments += "--llm"
    }
    if ($NoOpenAI) {
        $arguments += "--no-llm"
    }
    if ($RequireOpenAI -and -not $arguments.Contains("--require-llm")) {
        $arguments += "--require-llm"
    }

    & $PythonPath @arguments
}
finally {
    Pop-Location
}
