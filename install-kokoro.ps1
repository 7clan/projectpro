$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
if (-not (Test-Path ".venv\Scripts\python.exe")) { python -m venv .venv; if ($LASTEXITCODE) { throw "Virtual environment creation failed" } }
& ".\.venv\Scripts\python.exe" -m pip install -r requirements-kokoro.txt
if ($LASTEXITCODE) { throw "Kokoro installation failed" }
$dir = "voices\kokoro"
New-Item -ItemType Directory -Force $dir | Out-Null
$base = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0"
foreach ($file in @("kokoro-v1.0.onnx","voices-v1.0.bin")) {
    $dest = Join-Path $dir $file
    if (-not (Test-Path $dest)) {
        curl.exe --fail --location --retry 2 "$base/$file" --output "$dest.part"
        if ($LASTEXITCODE) { throw "Model download failed: $file" }
        Move-Item -Force "$dest.part" $dest
    }
}
& ".\.venv\Scripts\python.exe" -c "import asyncio; from app.kokoro_voice import synthesize_kokoro; a,m,b=asyncio.run(synthesize_kokoro('Welcome to Declic.','en',[0])); assert b=='kokoro-neural',b; print('Kokoro offline voice ready')"
if ($LASTEXITCODE) { throw "Kokoro smoke test failed" }
