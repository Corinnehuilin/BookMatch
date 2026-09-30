# Build a Windows package locally. Run from PowerShell in the repository root.
$ErrorActionPreference = 'Stop'
Set-Location (Join-Path $PSScriptRoot '..')

$python = Join-Path (Get-Location) '.venv\Scripts\python.exe'
if (-not (Test-Path $python)) {
    py -3 -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the Python environment.' }
}

& $python -m pip install -r requirements-build.txt
if ($LASTEXITCODE -ne 0) { throw 'Could not install build requirements.' }

$env:PYINSTALLER_CONFIG_DIR = Join-Path (Get-Location) '.pyinstaller-cache'
& $python -m PyInstaller --noconfirm --clean --windowed --name BookMatch `
    --icon assets\bookmatch-icon.ico `
    --add-data 'data/catalog.json;data' `
    --add-data 'data/cover_ids.json;data' `
    --add-data 'assets/bookmatch-icon.png;assets' `
    --add-data 'THIRD_PARTY_NOTICES.md;.' `
    --add-data 'third_party;third_party' `
    --add-data 'data/SOURCE.md;data' `
    --copy-metadata PySide6 `
    --copy-metadata PySide6_Essentials `
    --copy-metadata PySide6_Addons `
    --copy-metadata shiboken6 `
    --collect-all fastembed `
    --collect-all onnxruntime `
    run_bookmatch.py
if ($LASTEXITCODE -ne 0) { throw 'Windows packaging failed.' }

$env:QT_QPA_PLATFORM = 'offscreen'
$env:BOOKMATCH_DATA_DIR = Join-Path $env:TEMP 'bookmatch-package-check'
& .\dist\BookMatch\BookMatch.exe --self-test
if ($LASTEXITCODE -ne 0) { throw 'The packaged app failed its offline launch check.' }

Compress-Archive -Path .\dist\BookMatch -DestinationPath .\dist\BookMatch-windows-x64.zip -Force
Write-Host 'Built dist\BookMatch\BookMatch.exe and dist\BookMatch-windows-x64.zip'
