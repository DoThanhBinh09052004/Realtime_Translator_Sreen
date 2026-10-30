$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

$PythonPath = Join-Path $ScriptDir ".venv\Scripts\python.exe"

if (Test-Path $PythonPath) {
    & $PythonPath (Join-Path $ScriptDir "main.py")
} else {
    Write-Host "[ERROR] Khong tim thay Python trong $PythonPath" -ForegroundColor Red
    pause
}
