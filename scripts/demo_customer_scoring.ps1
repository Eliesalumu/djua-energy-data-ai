param(
    [string]$Phone = "",
    [ValidateSet("bon", "moyen", "risque")]
    [string]$Scenario = "bon",
    [string]$ExternalApiBaseUrl = "",
    [string]$ApiUrl = "",
    [switch]$ExplainWithLlm,
    [switch]$Json
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$PythonPath = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$CliPath = Join-Path $ProjectRoot "scripts\customer_scoring_cli.py"
$ModelPath = Join-Path $ProjectRoot "artifacts\customer_scoring_model.joblib"
$TrainPath = Join-Path $ProjectRoot "scripts\train_scoring.py"

Write-Host ""
Write-Host "DJUA ENERGY - DEMO SCORING CLIENT ML" -ForegroundColor Cyan
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

    if (-not [string]::IsNullOrWhiteSpace($ApiUrl)) {
        if ([string]::IsNullOrWhiteSpace($Phone)) {
            $Phone = Read-Host "Numero Orange Money a scorer"
        }

        $query = if ($ExplainWithLlm) { "?explain_with_llm=true" } else { "" }
        $url = "$($ApiUrl.TrimEnd('/'))/scoring/customers/$Phone$query"

        Write-Host "Appel endpoint FastAPI local/deploye :" -ForegroundColor Yellow
        Write-Host $url -ForegroundColor Gray
        Write-Host ""

        $response = Invoke-RestMethod -Method Get -Uri $url
        if ($Json) {
            $response | ConvertTo-Json -Depth 10
        }
        else {
            Write-Host "Client        : $($response.client_name)"
            Write-Host "Telephone     : $($response.phone)"
            Write-Host "Kit           : $($response.subscription.kit_id)"
            Write-Host "Score         : $($response.score)/100" -ForegroundColor Green
            Write-Host "Niveau risque : $($response.risk_level)"
            Write-Host "Defaut 90j    : $($response.default_probability_90d)"
            Write-Host "Decision      : $($response.decision)"
            Write-Host ""
            Write-Host "Explication:" -ForegroundColor Yellow
            Write-Host $response.explanation.summary
        }
        exit 0
    }

    if (-not [string]::IsNullOrWhiteSpace($ExternalApiBaseUrl)) {
        $env:DJUA_EXTERNAL_API_BASE_URL = $ExternalApiBaseUrl.TrimEnd("/")
    }

    $arguments = @($CliPath)
    if (-not [string]::IsNullOrWhiteSpace($Phone)) {
        $arguments += @("--phone", $Phone)
    }
    else {
        $arguments += @("--scenario", $Scenario)
        Write-Host "Mode demo local sans API externe. Scenario : $Scenario" -ForegroundColor Yellow
        Write-Host "Pour l'API reelle, utilisez -ExternalApiBaseUrl et -Phone." -ForegroundColor Gray
        Write-Host ""
    }
    if ($ExplainWithLlm) {
        $arguments += "--llm"
    }
    if ($Json) {
        $arguments += "--json"
    }

    & $PythonPath @arguments
}
finally {
    Pop-Location
}
