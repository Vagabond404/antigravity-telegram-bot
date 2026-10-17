# Deploy-ToOracleCloud.ps1
# Script PowerShell pour déployer l'Agent IA Magma sur Oracle Cloud Free Tier

param(
    [Parameter(Mandatory=$true, HelpMessage="Adresse IP publique de votre instance Oracle Cloud")]
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
Write-Host "🚀 Déploiement de l'Agent IA Magma vers Oracle Cloud" -ForegroundColor Cyan
Write-Host "   Serveur : $RemoteUser@$ServerHost (Port: $Port)" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

# 1. Détection des exécutables SSH et SCP
$sshExe = if (Test-Path "C:\Program Files\Git\usr\bin\ssh.exe") { "C:\Program Files\Git\usr\bin\ssh.exe" } else { "ssh" }
$scpExe = if (Test-Path "C:\Program Files\Git\usr\bin\scp.exe") { "C:\Program Files\Git\usr\bin\scp.exe" } else { "scp" }

# Options SSH
$sshArgs = @("-o", "StrictHostKeyChecking=no", "-o", "ConnectTimeout=10", "-p", "$Port")
$scpArgs = @("-o", "StrictHostKeyChecking=no", "-o", "ConnectTimeout=10", "-P", "$Port")

if ($KeyPath -and (Test-Path $KeyPath)) {
    $sshArgs += @("-i", $KeyPath)
    $scpArgs += @("-i", $KeyPath)
    Write-Host "🔑 Utilisation de la clé SSH : $KeyPath" -ForegroundColor Gray
}

# 2. Test de connexion SSH
Write-Host "`n[1/4] Test de connexion SSH vers $ServerHost..." -ForegroundColor Yellow
$sshTest = & $sshExe @sshArgs "$RemoteUser@$ServerHost" "echo 'SSH_OK'" 2>&1
if ($LASTEXITCODE -ne 0 -or ($sshTest -notmatch "SSH_OK")) {
    Write-Warning "⚠️ Impossible de se connecter en SSH à $RemoteUser@$ServerHost."
    Write-Warning "Erreur : $sshTest"
    Write-Host "`nConseils pour Oracle Cloud :" -ForegroundColor Yellow
    Write-Host "  1. Vérifiez que le Security List de votre VCN autorise le port 22 en Ingress."
    Write-Host "  2. Vérifiez l'utilisateur : souvent 'ubuntu' pour Ubuntu, ou 'opc' pour Oracle Linux."
    Write-Host "  3. Vérifiez le chemin de votre clé SSH privée (.key ou .pem) avec le paramètre -KeyPath."
    exit 1
}
Write-Host "✅ Connexion SSH établie avec succès !" -ForegroundColor Green

# 3. Création du répertoire temporaire sur le serveur
Write-Host "`n[2/4] Préparation du dossier de transfert..." -ForegroundColor Yellow
& $sshExe @sshArgs "$RemoteUser@$ServerHost" "sudo mkdir -p $RemoteDir && sudo chown -R ${RemoteUser}:${RemoteUser} $RemoteDir"

# 4. Liste des fichiers à copier
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

Write-Host "`n[3/4] Envoi des fichiers de l'Agent vers $RemoteDir..." -ForegroundColor Yellow
foreach ($file in $files) {
    $src = Join-Path $localDir $file
    if (Test-Path $src) {
        Write-Host "  -> Copie de $file..." -ForegroundColor Gray
        & $scpExe @scpArgs $src "$RemoteUser@${ServerHost}:${RemoteDir}/$file"
    } else {
        Write-Warning "Fichier local non trouvé : $file"
    }
}

# 5. Exécution du script d'installation sur le serveur
Write-Host "`n[4/4] Exécution de setup_oracle.sh sur le serveur distant..." -ForegroundColor Yellow
& $sshExe @sshArgs "$RemoteUser@$ServerHost" "sudo bash ${RemoteDir}/setup_oracle.sh"

Write-Host "`n==========================================================" -ForegroundColor Green
Write-Host "✅ Déploiement terminé avec succès sur Oracle Cloud !" -ForegroundColor Green
Write-Host "==========================================================" -ForegroundColor Green
Write-Host "Votre bot Telegram est maintenant actif sur votre serveur Oracle Cloud."
Write-Host "Pour surveiller son activité : & $sshExe @sshArgs $RemoteUser@$ServerHost 'journalctl -u antigravity-bot.service -f'"
