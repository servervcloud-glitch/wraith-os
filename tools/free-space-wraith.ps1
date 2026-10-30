# Wraith OS - free the disk space the old PC build setup used
#
# The old "build on this PC" setup left its build cache (tens of GB) and old
# ISOs inside Ubuntu (WSL). WSL never gives that space back to Windows by
# itself, so this script deletes it and then shrinks Ubuntu's virtual disk.
# Your own files in Ubuntu are not touched. Also removes failed Chrome
# downloads (*.crdownload) from Downloads.
#
# Right-click > "Run with PowerShell" (it asks for administrator rights).
$ErrorActionPreference = 'Stop'
trap {
    Write-Host "`nSomething went wrong: $_" -ForegroundColor Red
    Read-Host 'Press Enter to close'
    exit 1
}
function Say($t, $c = 'Cyan') { Write-Host $t -ForegroundColor $c }
function FreeGB { [math]::Round((Get-PSDrive -Name C).Free / 1GB, 1) }

# ---- administrator rights (needed to shrink the virtual disk) --------------
$admin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $admin) {
    Start-Process powershell.exe -Verb RunAs -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`""
    exit
}

Say "Wraith OS - free disk space`n" 'Magenta'
$before = FreeGB
Say "Free on C: now: $before GB"

# ---- 1. failed browser downloads -------------------------------------------
$dl = Join-Path $env:USERPROFILE 'Downloads'
$partial = Get-ChildItem -Path $dl -Filter '*.crdownload' -File -ErrorAction SilentlyContinue
if ($partial) {
    $partial | Remove-Item -Force
    Say "Removed $($partial.Count) unfinished download(s)."
}

# ---- 2. build cache and old ISOs inside Ubuntu (WSL) ------------------------
$distros = @()
try {
    $distros = (wsl.exe -l -q 2>$null) | ForEach-Object { ($_ -replace "`0", '').Trim() } | Where-Object { $_ -match 'Ubuntu' }
} catch { $distros = @() }
if (-not $distros) {
    Say 'No Ubuntu (WSL) found - nothing to clean there.' 'Yellow'
} else {
    # one line, no double quotes: Windows PowerShell mangles those when passing arguments
    $clean = 'docker rm -f wraith-build >/dev/null 2>&1; docker image rm -f kalilinux/kali-rolling >/dev/null 2>&1; ' +
             'docker builder prune -af >/dev/null 2>&1; docker container prune -f >/dev/null 2>&1; ' +
             'for h in /root /home/*; do rm -rf $h/wraith $h/wraith-builds $h/wraith-cache $h/wraith-work; done; ' +
             'fstrim -av >/dev/null 2>&1; true'
    foreach ($d in $distros) {
        Say "Cleaning the Wraith build files in $d (this can take a few minutes)..."
        wsl.exe -d $d -u root -e bash -c $clean
    }
}

# ---- 3. shrink Ubuntu's virtual disk so Windows gets the space back ---------
Say 'Shutting down WSL...'
wsl.exe --shutdown
Start-Sleep -Seconds 5
$vhds = @()
$vhds += Get-ChildItem -Path "$env:LOCALAPPDATA\Packages\*\LocalState\ext4.vhdx" -ErrorAction SilentlyContinue
$vhds += Get-ChildItem -Path "$env:LOCALAPPDATA\wsl\*\ext4.vhdx" -ErrorAction SilentlyContinue
foreach ($v in $vhds) {
    $gb = [math]::Round($v.Length / 1GB, 1)
    Say "Shrinking $($v.FullName) ($gb GB)..."
    $script = Join-Path $env:TEMP 'wraith-compact.txt'
    @(
        "select vdisk file=`"$($v.FullName)`""
        'attach vdisk readonly'
        'compact vdisk'
        'detach vdisk'
        'exit'
    ) | Set-Content -Path $script -Encoding ASCII
    diskpart.exe /s $script | Out-Null
    Remove-Item $script -ErrorAction SilentlyContinue
    $gb2 = [math]::Round((Get-Item $v.FullName).Length / 1GB, 1)
    Say "  now $gb2 GB"
}

$after = FreeGB
Say "`nFree on C: before: $before GB   now: $after GB   (gained $([math]::Round($after - $before, 1)) GB)" 'Green'
if ($after -lt 100) {
    Say 'For the ISO (about 30 GB while decrypting) plus the virtual machine (about 60 GB),' 'Yellow'
    Say 'around 100 GB free is comfortable. If you have another drive (D: etc.),' 'Yellow'
    Say 'download the parts there and create the VM there too.' 'Yellow'
}
Read-Host "`nPress Enter to close"
