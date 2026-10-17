# Deploy-ToOracleCloud.ps1
# PowerShell script to deploy Antigravity Telegram Agent to an Oracle Cloud / Linux VPS over SSH

param(
    [Parameter(Mandatory=$true, HelpMessage="Public IP address or hostname of your remote Linux server")]
    [string]$ServerHost,

    [Parameter(Mandatory=$false)]
    [string]$RemoteUser = "ubuntu",

    [Parameter(Mandatory=$false)]
    [string]$KeyPath = "",

    [Parameter(Mandatory=$false)]
    [int]$Port = 22,

    [Parameter(Mandatory=$false)]
    [string]$RemoteDir = "/opt/antigravity-bot"
)

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "🚀 Deploying Antigravity Telegram Agent to Remote Server" -ForegroundColor Cyan
Write-Host "   Target : $RemoteUser@$ServerHost (Port: $Port)" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

# 1. Detect SSH and SCP binaries
$sshExe = if (Test-Path "C:\Program Files\Git\usr\bin\ssh.exe") { "C:\Program Files\Git\usr\bin\ssh.exe" } else { "ssh" }
$scpExe = if (Test-Path "C:\Program Files\Git\usr\bin\scp.exe") { "C:\Program Files\Git\usr\bin\scp.exe" } else { "scp" }

# SSH connection options
$sshArgs = @("-o", "StrictHostKeyChecking=no", "-o", "ConnectTimeout=10", "-p", "$Port")
$scpArgs = @("-o", "StrictHostKeyChecking=no", "-o", "ConnectTimeout=10", "-P", "$Port")

if ($KeyPath -and (Test-Path $KeyPath)) {
    $sshArgs += @("-i", $KeyPath)
    $scpArgs += @("-i", $KeyPath)
    Write-Host "🔑 Using SSH private key: $KeyPath" -ForegroundColor Gray
}

# 2. Test SSH connectivity
Write-Host "`n[1/4] Testing SSH connectivity to $ServerHost..." -ForegroundColor Yellow
$sshTest = & $sshExe @sshArgs "$RemoteUser@$ServerHost" "echo 'SSH_OK'" 2>&1
if ($LASTEXITCODE -ne 0 -or ($sshTest -notmatch "SSH_OK")) {
    Write-Warning "⚠️ Unable to connect via SSH to $RemoteUser@$ServerHost."
    Write-Warning "Error: $sshTest"
    exit 1
}
Write-Host "✅ SSH connection established!" -ForegroundColor Green

# 3. Create target directory on remote server
Write-Host "`n[2/4] Preparing remote directory..." -ForegroundColor Yellow
& $sshExe @sshArgs "$RemoteUser@$ServerHost" "sudo mkdir -p $RemoteDir && sudo chown -R ${RemoteUser}:${RemoteUser} $RemoteDir"

# 4. Copy project files to remote server
$files = @(
    "config.py",
    "bot.py",
    "setup_wizard.py",
    "agent_runner.py",
    "command_manager.py",
    "custom_commands.json",
    "ui_helpers.py",
    "tg_send.py",
    "server_watchdog.py",
    "auto_heal_config.json",
    "log_scanner.py",
    "auth_manager.py",
    "memory_manager.py",
    "mem.py",
    "updater.py",
    "VERSION.json",
    "browser_tool.py",
    "requirements.txt",
    ".env.example",
    "install.sh",
    "setup_oracle.sh"
)

$localDir = $PSScriptRoot

Write-Host "`n[3/4] Uploading agent files to $RemoteDir..." -ForegroundColor Yellow
foreach ($file in $files) {
    $src = Join-Path $localDir $file
    if (Test-Path $src) {
        Write-Host "  -> Uploading $file..." -ForegroundColor Gray
        & $scpExe @scpArgs $src "$RemoteUser@${ServerHost}:${RemoteDir}/$file"
    } else {
        Write-Warning "Local file not found: $file"
    }
}

# 5. Execute remote installation script
Write-Host "`n[4/4] Running setup_oracle.sh on remote server..." -ForegroundColor Yellow
& $sshExe @sshArgs "$RemoteUser@$ServerHost" "sudo bash ${RemoteDir}/setup_oracle.sh"

Write-Host "`n==========================================================" -ForegroundColor Green
Write-Host "✅ Deployment completed successfully!" -ForegroundColor Green
Write-Host "==========================================================" -ForegroundColor Green
