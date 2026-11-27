param(
    [string]$Model = "",
    [switch]$Hybrid
)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
try {
    $installed = @((Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/tags" -TimeoutSec 5).models)
} catch {
    throw "Ollama is not responding. Open Ollama from the Windows Start menu, then rerun this script."
}
$local = @($installed | Where-Object { $_.name -and $_.name -notmatch "cloud" -and -not $_.remote_model -and -not $_.remote_host })
if ($local.Count -eq 0) { throw "No local model found. Run ollama pull qwen2.5:3b-instruct first." }
if (-not $Model) {
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
if ($Model -notin @($local | ForEach-Object { $_.name })) { throw "Model not installed locally: $Model" }
$env:DECLIC_OLLAMA_MODEL = $Model
$env:DECLIC_OLLAMA_TIMEOUT = "240"
if ($Hybrid) { $env:DECLIC_LOCAL_ONLY = "0" } else { $env:DECLIC_LOCAL_ONLY = "1" }
if (-not (Test-Path ".venv\Scripts\python.exe")) {
    py -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw "Could not create Python virtual environment." }
}
$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
& $python -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw "Dependency installation failed." }
Write-Host "DÉCLIC model: $Model | local-only: $env:DECLIC_LOCAL_ONLY"
Write-Host "Open http://127.0.0.1:8000 in Chrome or Edge."
Write-Host "For fully offline speech, install Piper voices as explained in docs/NEURAL_VOICE.md."
& $python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
