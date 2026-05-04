$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$pythonExe = Join-Path $projectRoot ".venv\Scripts\python.exe"
$mainScript = Join-Path $projectRoot "main.py"
$logsDir = Join-Path $projectRoot "logs"
$stdoutLog = Join-Path $logsDir "tracker_scheduler.log"
$stderrLog = Join-Path $logsDir "tracker_scheduler.error.log"

if (-not (Test-Path $pythonExe)) {
    throw "Python virtual environment executable not found: $pythonExe"
}

if (-not (Test-Path $logsDir)) {
    New-Item -ItemType Directory -Path $logsDir | Out-Null
}

Set-Location $projectRoot

& $pythonExe $mainScript scheduler 1>> $stdoutLog 2>> $stderrLog
