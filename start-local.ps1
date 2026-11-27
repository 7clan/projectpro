param(
    [string]$Model = "",
    [string]$CloudModel = "",
    [switch]$Hybrid
)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
# Load private settings without executing the file or printing secrets.
if (Test-Path ".env") {
    Get-Content ".env" | ForEach-Object {
        if ($_ -match '^\s*([A-Za-z_][A-Za-z0-9_]*)=(.*)$') {
            Set-Item "Env:$($Matches[1])" $Matches[2].Trim()
        }
    }
}
if (-not $CloudModel) { $CloudModel = $env:DECLIC_OLLAMA_CLOUD_MODEL }
if ($CloudModel) {
    if ($CloudModel -notmatch '^[A-Za-z0-9][A-Za-z0-9._/-]{0,160}:cloud$') { throw "Cloud model must use its Ollama :cloud name." }
    $env:DECLIC_OLLAMA_CLOUD_MODEL = $CloudModel
    if ($PSBoundParameters.ContainsKey("CloudModel")) { $Hybrid = $true }
}

try {
    $installed = @((Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/tags" -TimeoutSec 5).models)
} catch {
    throw "Ollama is not responding. Open Ollama from the Windows Start menu, then rerun this script."
}
$local = @($installed | Where-Object { $_.name -and $_.name -notmatch "cloud" -and -not $_.remote_model -and -not $_.remote_host })
if ($local.Count -eq 0 -and (-not $CloudModel -or -not $Hybrid)) { throw "No local model found. Select an Ollama Cloud model with -CloudModel or install a local model." }
if (-not $Model -and $local.Count -gt 0) {
    Write-Host "Available local models:"
    for ($i=0; $i -lt $local.Count; $i++) {
        Write-Host ("{0}. {1}" -f ($i+1), $local[$i].name)
    }
    $selection = Read-Host "Enter model number"
    $number = 0
    if (-not [int]::TryParse($selection,[ref]$number) -or $number -lt 1 -or $number -gt $local.Count) {
        throw "Invalid model selection."
    }
    $Model = $local[$number-1].name
}
if ($Model -and $Model -notin @($local | ForEach-Object { $_.name })) { throw "Model not installed locally: $Model" }
$env:DECLIC_OLLAMA_MODEL = $Model
$env:DECLIC_OLLAMA_TIMEOUT = "240"
if ($Hybrid) { $env:DECLIC_LOCAL_ONLY = "0" } else { $env:DECLIC_LOCAL_ONLY = "1" }
if (-not (Test-Path ".venv\Scripts\python.exe")) {
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw "Could not create Python virtual environment." }
}
$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
& $python -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw "Dependency installation failed." }
Write-Host "DÉCLIC local model: $Model | Ollama cloud: $CloudModel | local-only: $env:DECLIC_LOCAL_ONLY"
Write-Host "Open http://127.0.0.1:8000 in Chrome or Edge."
Write-Host "For fully offline speech, install Piper voices as explained in docs/NEURAL_VOICE.md."
& $python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
