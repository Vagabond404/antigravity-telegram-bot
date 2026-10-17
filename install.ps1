# ==============================================================================
# 🚀 ANTIGRAVITY TELEGRAM AGENT v4.0 — UNIVERSAL WINDOWS INSTALLER (PowerShell)
# Works on Windows 10, Windows 11, and Windows Server.
# ==============================================================================
$ErrorActionPreference = "Stop"

Write-Host "==================================================================" -ForegroundColor Cyan
Write-Host "   🚀 ANTIGRAVITY TELEGRAM AGENT v4.0 — WINDOWS INSTALLER         " -ForegroundColor Cyan
Write-Host "==================================================================" -ForegroundColor Cyan

# If invoked via irm | iex outside the repo, clone or navigate to repo
if (-not (Test-Path ".\bot.py")) {
    $RepoUrl = if ($env:ANTIGRAVITY_BOT_REPO) { $env:ANTIGRAVITY_BOT_REPO } else { "https://github.com/antigravity-agent/antigravity-telegram-bot.git" }
    $TargetDir = if ($env:ANTIGRAVITY_BOT_DIR) { $env:ANTIGRAVITY_BOT_DIR } else { Join-Path $HOME "antigravity-telegram-bot" }
    if (-not (Test-Path (Join-Path $TargetDir "bot.py"))) {
        Write-Host "⬇️ Clonage du dépôt dans $TargetDir..." -ForegroundColor Cyan
        git clone $RepoUrl $TargetDir
    }
    Set-Location $TargetDir
}

$InstallDir = (Get-Location).Path
Write-Host "📍 Dossier d'installation : $InstallDir" -ForegroundColor Green

# 1. Check Python 3.10+
Write-Host "`n[1/5] Vérification de Python 3..." -ForegroundColor White
$PythonCmd = $null
foreach ($candidate in @("python", "py")) {
    if (Get-Command $candidate -ErrorAction SilentlyContinue) {
        try {
            $ver = & $candidate -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
            if ($ver -match "^3\.(1[0-9]|[2-9][0-9])") {
                $PythonCmd = $candidate
                Write-Host "  ✔ Python $ver détecté ($candidate)" -ForegroundColor Green
                break
            }
        } catch {}
    }
}

if (-not $PythonCmd) {
    Write-Host "  ⚡ Python 3.10+ non détecté. Installation automatique via winget..." -ForegroundColor Yellow
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
        $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
        $PythonCmd = "python"
    } else {
        Write-Host "  ❌ Veuillez installer Python 3.11+ depuis https://www.python.org/downloads/ (cochez 'Add Python to PATH')." -ForegroundColor Red
        exit 1
    }
}

# 2. Install or Update Antigravity CLI (agy.exe)
Write-Host "`n[2/5] Installation / Mise à jour d'Antigravity CLI (agy)..." -ForegroundColor White
$AgyDefaultPath = Join-Path $env:LOCALAPPDATA "agy\bin\agy.exe"
$AgyBin = $null
if (Get-Command agy -ErrorAction SilentlyContinue) {
    $AgyBin = (Get-Command agy).Source
} elseif (Test-Path $AgyDefaultPath) {
    $AgyBin = $AgyDefaultPath
}

if (-not $AgyBin) {
    Write-Host "  ⬇️ Téléchargement et installation officielle d'Antigravity CLI pour Windows..." -ForegroundColor Cyan
    try {
        irm https://antigravity.google/cli/install.ps1 | iex
    } catch {
        Write-Host "  ⚠ Impossible d'installer automatiquement Antigravity CLI : $_" -ForegroundColor Yellow
    }
    if (Test-Path $AgyDefaultPath) {
        $AgyBin = $AgyDefaultPath
    }
} else {
    Write-Host "  ✔ Antigravity CLI détecté : $AgyBin" -ForegroundColor Green
    try {
        & $AgyBin update
    } catch {}
}

# Ensure agy bin directory is in current session PATH
$AgyDir = Join-Path $env:LOCALAPPDATA "agy\bin"
if ((Test-Path $AgyDir) -and ($env:Path -notlike "*$AgyDir*")) {
    $env:Path = "$AgyDir;$env:Path"
}

# 3. Create Virtual Environment (.venv) & Install Requirements
Write-Host "`n[3/5] Création de l'environnement virtuel Python (.venv)..." -ForegroundColor White
$VenvDir = Join-Path $InstallDir ".venv"
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
    & $PythonCmd -m venv $VenvDir
}
& $VenvPython -m pip install --upgrade pip --quiet
& $VenvPython -m pip install -r (Join-Path $InstallDir "requirements.txt") --quiet
Write-Host "  ✔ Dépendances Python installées avec succès." -ForegroundColor Green

# 4. Generate start_bot.bat Launcher
$BatContent = @"
@echo off
title Antigravity Telegram Agent v4.0
cd /d "%~dp0"
set "PATH=%LOCALAPPDATA%\agy\bin;%PATH%"
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" bot.py
) else (
    python bot.py
)
pause
"@
Set-Content -Path (Join-Path $InstallDir "start_bot.bat") -Value $BatContent -Encoding UTF8

# 5. Run Interactive Setup Wizard
Write-Host "`n[4/5] Lancement de l'Assistant de Configuration..." -ForegroundColor White
& $VenvPython (Join-Path $InstallDir "setup_wizard.py")

# 6. Optional Windows Auto-Start Task
Write-Host "`n[5/5] Démarrage automatique avec Windows..." -ForegroundColor White
$AutoStart = Read-Host "  Voulez-vous lancer le bot automatiquement à l'ouverture de session Windows ? [o/N]"
if ($AutoStart -match "^[oOyY]$") {
    try {
        $TaskName = "AntigravityTelegramBot"
        $Action = New-ScheduledTaskAction -Execute $VenvPython -Argument "`"$InstallDir\bot.py`"" -WorkingDirectory $InstallDir
        $Trigger = New-ScheduledTaskTrigger -AtLogOn
        $Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit 0 -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
        Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Force | Out-Null
        Write-Host "  ✔ Tâche planifiée '$TaskName' enregistrée !" -ForegroundColor Green
    } catch {
        Write-Host "  ⚠ Impossible de créer la tâche planifiée automatiquement : $_" -ForegroundColor Yellow
    }
}

Write-Host "`n🎉 Installation terminée avec succès !" -ForegroundColor Green
$StartNow = Read-Host "  Voulez-vous démarrer le bot maintenant ? [O/n]"
if ($StartNow -eq "" -or $StartNow -match "^[oOyY]$") {
    & $VenvPython (Join-Path $InstallDir "bot.py")
} else {
    Write-Host "  Double-cliquez sur 'start_bot.bat' à tout moment pour lancer le bot." -ForegroundColor Cyan
}
