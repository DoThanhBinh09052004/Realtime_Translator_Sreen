param(
    [Parameter(Mandatory=$true)][string]$PythonPath,
    [Parameter(Mandatory=$true)][string]$ModelDir,
    [string]$DistPath,
    [string]$WorkPath
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$python = (Resolve-Path -LiteralPath $PythonPath).Path
$models = (Resolve-Path -LiteralPath $ModelDir).Path
if (-not $DistPath) { $DistPath = Join-Path $projectRoot 'dist' }
if (-not $WorkPath) { $WorkPath = Join-Path $projectRoot 'build' }
$DistPath = [System.IO.Path]::GetFullPath($DistPath)
$WorkPath = [System.IO.Path]::GetFullPath($WorkPath)
$previousModels = $env:TRANSLATEHUD_OCR_MODELS_DIR
$previousLocation = Get-Location
$exitCode = 0
try {
    $env:TRANSLATEHUD_OCR_MODELS_DIR = $models
    Set-Location -LiteralPath $projectRoot
    & $python -c "import sys; from pathlib import Path; from tools.bundle_layout import bundle_data; bundle_data(Path(sys.argv[1]), Path(sys.argv[2]))" $projectRoot $models
    if ($LASTEXITCODE -ne 0) { $exitCode=$LASTEXITCODE; throw 'OCR bundle preflight failed.' }
    & $python -m PyInstaller --clean --noconfirm --distpath $DistPath --workpath $WorkPath (Join-Path $projectRoot 'main.spec')
    if ($LASTEXITCODE -ne 0) { $exitCode=$LASTEXITCODE; throw 'PyInstaller failed.' }
} catch {
    Write-Error $_ -ErrorAction Continue
    if ($exitCode -eq 0) { $exitCode=1 }
} finally {
    $env:TRANSLATEHUD_OCR_MODELS_DIR = $previousModels
    Set-Location -LiteralPath $previousLocation
}
exit $exitCode
