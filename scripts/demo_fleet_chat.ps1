param(
    [string]$Question = "",
    [switch]$NoOpenAI,
    [switch]$RequireOpenAI
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$PythonPath = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$CliPath = Join-Path $ProjectRoot "scripts\chat_device_cli.py"
$DatasetPath = Join-Path $ProjectRoot "data\generated\mvp_dataset.csv"
$MaintenanceModelPath = Join-Path $ProjectRoot "artifacts\maintenance_model.joblib"
$SecurityModelPath = Join-Path $ProjectRoot "artifacts\security_model.joblib"
$GenerateDataPath = Join-Path $ProjectRoot "scripts\generate_synthetic_data.py"
$TrainPipelinePath = Join-Path $ProjectRoot "scripts\train_scoring.py"

Write-Host ""
Write-Host "DJUA ENERGY - CHAT IA SURVEILLANCE DU PARC" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""

if (-not (Test-Path $PythonPath)) {
    Write-Host "Python virtuel introuvable : $PythonPath" -ForegroundColor Red
    Write-Host "Lance d'abord : .\scripts\create_venv.ps1"
    exit 1
}

Push-Location $ProjectRoot
try {
    if (-not (Test-Path $DatasetPath)) {
        Write-Host "Dataset parc absent. Generation automatique..." -ForegroundColor Yellow
        & $PythonPath $GenerateDataPath
        Write-Host ""
    }

    if ((-not (Test-Path $MaintenanceModelPath)) -or (-not (Test-Path $SecurityModelPath))) {
        Write-Host "Modeles maintenance/security absents." -ForegroundColor Red
        Write-Host "Lancez l'entrainement pipeline avant la demo parc."
        exit 1
    }

    $arguments = @($CliPath)
    if (-not [string]::IsNullOrWhiteSpace($Question)) {
        $arguments += @("--question", $Question)
    }
    if ($NoOpenAI) {
        $arguments += "--no-llm"
    }
    elseif (-not [string]::IsNullOrWhiteSpace($env:OPENAI_API_KEY)) {
        Write-Host "OPENAI_API_KEY detectee : OpenAI sera utilise si disponible." -ForegroundColor Green
        Write-Host ""
        if ($RequireOpenAI) {
            $arguments += "--require-llm"
        }
    }
    elseif ($RequireOpenAI) {
        $arguments += "--require-llm"
    }

    & $PythonPath @arguments
}
finally {
    Pop-Location
}
