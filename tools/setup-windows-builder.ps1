<#
  Wraith OS - set up this Windows PC as the build machine.

  What it does (safe to run again; finished steps are skipped):
    1. Installs WSL2 + Ubuntu (needs one restart)
    2. Gives WSL about two thirds of your RAM, plus swap
    3. Turns on systemd in Ubuntu and installs Docker
    4. Checks you have ~75 GB free on C:
    5. Stops the PC sleeping while plugged in
    6. Installs the GitHub Actions runner (label: wraith-builder)
    7. Puts a "Wraith Builder" shortcut on your desktop and starts it

  Run it:
    Right-click PowerShell > Run as administrator, then:
      Set-ExecutionPolicy -Scope Process Bypass -Force
      .\setup-windows-builder.ps1
#>

$ErrorActionPreference = "Stop"
# Never close silently: show any error and wait for Enter.
trap {
    Write-Host "`n[wraith] ERROR: $_" -ForegroundColor Red
    Write-Host "Take a photo of this screen and send it to Claude." -ForegroundColor Yellow
    Read-Host "Press Enter to close"
    exit 1
}
$Distro   = "Ubuntu"
$RepoUrl  = "https://github.com/servervcloud-glitch/wraith-os"
$Label    = "wraith-builder"

function Say($msg)  { Write-Host "`n[wraith] $msg" -ForegroundColor Magenta }
function Ok($msg)   { Write-Host "  OK  $msg" -ForegroundColor Green }
function Warn($msg) { Write-Host "  !!  $msg" -ForegroundColor Yellow }

# Run a bash script inside Ubuntu (as root, or as your normal user)
function InUbuntu([string]$script, [switch]$AsRoot) {
    # Send the script as one base64 block so nothing can cut it off on the way in.
    $clean = $script -replace "`r", ""
    $b64 = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($clean))
    $run = "echo $b64 | base64 -d > /tmp/wraith-step.sh && bash /tmp/wraith-step.sh; rc=`$?; rm -f /tmp/wraith-step.sh; exit `$rc"
    if ($AsRoot) { wsl.exe -d $Distro -u root -e bash -c $run }
    else         { wsl.exe -d $Distro -e bash -c $run }
    if ($LASTEXITCODE -ne 0) { throw "A step inside Ubuntu failed (exit code $LASTEXITCODE)." }
}

# ---- 0. Administrator ------------------------------------------------------
$admin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
         ).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $admin) {
    Say "Restarting as administrator..."
    Write-Host "A Windows prompt will ask for permission - click Yes. A new window then continues the setup."
    Start-Process powershell -Verb RunAs -ArgumentList "-NoProfile -ExecutionPolicy Bypass -NoExit -File `"$PSCommandPath`""
    Start-Sleep -Seconds 3
    exit
}

# ---- 1. WSL + Ubuntu -------------------------------------------------------
Say "Step 1/7: WSL and Ubuntu"
# Ask WSL for its distros without letting a "not installed" message stop the script.
$installed = $null
try {
    $old = $ErrorActionPreference; $ErrorActionPreference = "Continue"
    $list = & wsl.exe -l -q 2>&1 | Out-String
    $ErrorActionPreference = $old
    if ($LASTEXITCODE -eq 0) {
        $installed = ($list -replace "`0", "") -split "`r?`n" | Where-Object { $_.Trim() -eq $Distro }
    }
} catch { $installed = $null }
if (-not $installed) {
    wsl.exe --install -d $Distro
    Write-Host ""
    Warn "WSL and Ubuntu are installing. Next:"
    Write-Host "   1. Restart your PC."
    Write-Host "   2. Open 'Ubuntu' from the Start menu once and create a username + password."
    Write-Host "   3. Run this script again - it continues from here."
    Read-Host "`nPress Enter to close"
    exit
}
$ErrorActionPreference = "Continue"
wsl.exe -d $Distro -u root -- true 2>&1 | Out-Null
$ErrorActionPreference = "Stop"
if ($LASTEXITCODE -ne 0) {
    Warn "Ubuntu isn't set up yet. Open 'Ubuntu' from the Start menu, create a username + password, then run this script again."
    Read-Host "Press Enter to close"; exit
}
$User = (wsl.exe -d $Distro -- whoami).Trim()
if ($User -eq "root") {
    Warn "Ubuntu has no normal user yet. Open 'Ubuntu' from the Start menu and create one, then run this script again."
    Read-Host "Press Enter to close"; exit
}
Ok "Ubuntu is ready (user: $User)"

# ---- 2. Memory for WSL -----------------------------------------------------
Say "Step 2/7: memory and CPU for the build"
$ramGB = [math]::Floor((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory / 1GB)
$cores = (Get-CimInstance Win32_ComputerSystem).NumberOfLogicalProcessors
$memGB = [math]::Max(4, [math]::Floor($ramGB * 2 / 3))
$cpus  = [math]::Max(2, $cores - 1)
@"
[wsl2]
memory=${memGB}GB
processors=$cpus
swap=8GB
"@ | Out-File -Encoding ascii "$env:USERPROFILE\.wslconfig"
Ok "WSL gets ${memGB} GB of your ${ramGB} GB RAM, $cpus of $cores CPU threads, 8 GB swap"

# ---- 3. systemd + Docker ---------------------------------------------------
Say "Step 3/7: Docker inside Ubuntu"
InUbuntu -AsRoot @'
set -e
if ! grep -q '^systemd=true' /etc/wsl.conf 2>/dev/null; then
    printf '[boot]\nsystemd=true\n' > /etc/wsl.conf
fi
'@
wsl.exe --shutdown
Start-Sleep -Seconds 3
InUbuntu -AsRoot @"
set -e
export DEBIAN_FRONTEND=noninteractive
if ! command -v docker >/dev/null; then
    apt-get update -qq
    apt-get install -y -qq docker.io curl tar >/dev/null
fi
usermod -aG docker $User
systemctl enable --now docker >/dev/null 2>&1 || service docker start
docker run --rm hello-world >/dev/null && echo docker-works
"@
Ok "Docker works"

# ---- 4. Disk space ---------------------------------------------------------
Say "Step 4/7: disk space"
$freeGB = [math]::Floor((Get-PSDrive C).Free / 1GB)
if ($freeGB -lt 75) { Warn "Only $freeGB GB free on C:. The build needs about 70 GB - free some space before building." }
else { Ok "$freeGB GB free on C:" }

# ---- 5. No sleep while plugged in ------------------------------------------
Say "Step 5/7: keep the PC awake while plugged in"
powercfg /change standby-timeout-ac 0
powercfg /change hibernate-timeout-ac 0
Ok "Sleep set to Never (on mains power)"

# ---- 6. GitHub runner ------------------------------------------------------
Say "Step 6/7: GitHub Actions runner"
wsl.exe -d $Distro -- test -f /home/$User/actions-runner/.runner
if ($LASTEXITCODE -eq 0) {
    Ok "Runner already installed"
} else {
    Write-Host ""
    Write-Host "  Open this page in your browser:"
    Write-Host "    $RepoUrl/settings/actions/runners/new?arch=x64&os=linux" -ForegroundColor Cyan
    Write-Host "  Find the line that starts with ./config.sh and copy the value after --token"
    Write-Host "  (a long code like AB12CD...). It expires after 1 hour."
    $Token = (Read-Host "`n  Paste the token here").Trim()
    if (-not $Token) { throw "No token given." }
    InUbuntu @"
set -e
mkdir -p ~/actions-runner && cd ~/actions-runner
VER=`$(curl -fsSL --retry 5 https://api.github.com/repos/actions/runner/releases/latest 2>/dev/null | sed -n -E 's/.*"tag_name": *"v([^"]+)".*/\1/p' | head -n1)
[ -n "`$VER" ] || VER=2.338.2
echo "Downloading runner `$VER"
URL="https://github.com/actions/runner/releases/download/v`$VER/actions-runner-linux-x64-`$VER.tar.gz"
# Retries and resumes if the connection drops; shows % done, MB, speed and time left
echo ""
echo "Downloading the GitHub runner (about 180 MB):"
echo "  %  = done   Received = downloaded so far   Speed   Time Left"
for i in 1 2 3 4 5 6 7 8; do
    curl -fL -C - --retry 5 --retry-delay 3 --retry-all-errors -o runner.tgz "`$URL" && break
    echo "Connection dropped, retrying (`$i/8)..."; sleep 5
done
tar tzf runner.tgz >/dev/null 2>&1 || { echo "Download incomplete - check your internet and run the script again"; exit 1; }
tar xzf runner.tgz && rm runner.tgz
./config.sh --unattended --url $RepoUrl --token $Token --labels $Label --name "$env:COMPUTERNAME-wsl" --replace
"@
    Ok "Runner registered with label '$Label'"
}

# ---- 7. Shortcut + start ---------------------------------------------------
Say "Step 7/7: Wraith Builder shortcut"
$desktop = [Environment]::GetFolderPath("Desktop")
$lnk = (New-Object -ComObject WScript.Shell).CreateShortcut("$desktop\Wraith Builder.lnk")
$lnk.TargetPath = "wsl.exe"
$lnk.Arguments = "-d $Distro -- bash -lc `"cd ~/actions-runner && ./run.sh`""
$lnk.Description = "Wraith OS build machine - keep this window open while building"
$lnk.Save()
Ok "Shortcut 'Wraith Builder' is on your desktop"

Start-Process wsl.exe -ArgumentList "-d $Distro -- bash -lc `"cd ~/actions-runner && ./run.sh`""

Write-Host ""
Write-Host "All set." -ForegroundColor Green
Write-Host "  - A window called 'Wraith Builder' is now open. It should say 'Listening for Jobs'. Keep it open."
Write-Host "  - Start a build: $RepoUrl/actions  >  Build Wraith OS  >  Run workflow"
Write-Host "  - The ISO appears in:  \\wsl$\$Distro\home\$User\wraith-builds"
Write-Host "  - Next time, just double-click 'Wraith Builder' on your desktop first."
Read-Host "`nPress Enter to close"
