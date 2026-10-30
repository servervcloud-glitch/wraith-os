# Wraith OS - turn the downloaded release parts into the ISO (Windows)
#
# 1. Download every  wraith-...-amd64.iso.gpg.partNN  file and the  .parts.sha256
#    file from the GitHub release into your Downloads folder.
# 2. Right-click this file > "Run with PowerShell".
#
# It checks the parts downloaded correctly, joins them and decrypts the ISO
# (asks for your WRAITH_ISO_KEY passphrase). Uses Ubuntu (WSL) if you have it,
# otherwise Gpg4win (https://gpg4win.org).
$ErrorActionPreference = 'Stop'
trap {
    Write-Host "`nSomething went wrong: $_" -ForegroundColor Red
    Read-Host 'Press Enter to close'
    exit 1
}
function Say($t, $c = 'Cyan') { Write-Host $t -ForegroundColor $c }

$dir = Join-Path $env:USERPROFILE 'Downloads'
Say "Wraith OS - ISO decrypt`n" 'Magenta'

# ---- find the parts (newest build if there are several) --------------------
$all = Get-ChildItem -Path $dir -Filter 'wraith-*-amd64.iso.gpg.part*' -File
if (-not $all) { throw "No 'wraith-...iso.gpg.partNN' files found in $dir. Download them from the release first." }
$name = ($all | ForEach-Object { $_.Name -replace '\.iso\.gpg\.part\d+$', '' } | Sort-Object -Descending | Select-Object -First 1)
$parts = $all | Where-Object { $_.Name -like "$name.iso.gpg.part*" } | Sort-Object Name
Say "Build: $name  ($($parts.Count) parts)"

# ---- check every part against the release checksums ------------------------
$sumFile = Join-Path $dir "$name.parts.sha256"
if (Test-Path $sumFile) {
    $expected = @{}
    foreach ($line in Get-Content $sumFile) {
        if ($line -match '^([0-9a-fA-F]{64})\s+\*?(.+)$') { $expected[$Matches[2].Trim()] = $Matches[1].ToLower() }
    }
    $missing = $expected.Keys | Where-Object { -not (Test-Path (Join-Path $dir $_)) }
    if ($missing) { throw "Missing part(s): $($missing -join ', '). Download them, then run this again." }
    $i = 0
    foreach ($p in $parts) {
        $i++
        Write-Progress -Activity 'Checking the download' -Status "$($p.Name) ($i of $($parts.Count))" -PercentComplete (($i - 1) * 100 / $parts.Count)
        $h = (Get-FileHash -Algorithm SHA256 -LiteralPath $p.FullName).Hash.ToLower()
        if ($expected.ContainsKey($p.Name) -and $h -ne $expected[$p.Name]) {
            throw "$($p.Name) is damaged (checksum differs). Delete it, download it again, and rerun."
        }
    }
    Write-Progress -Activity 'Checking the download' -Completed
    Say 'All parts downloaded correctly.' 'Green'
} else {
    Say "($name.parts.sha256 not found - skipping the download check)" 'Yellow'
}

$iso = Join-Path $dir "$name.iso"
if (Test-Path $iso) { throw "$iso already exists. Delete or rename it first." }
$total = ($parts | Measure-Object -Property Length -Sum).Sum
$free = (Get-PSDrive -Name ($dir.Substring(0, 1))).Free

# ---- decrypt: Ubuntu (WSL) streams the parts straight into gpg -------------
$useWsl = $false
try { wsl.exe -e sh -c 'command -v gpg >/dev/null' 2>$null; $useWsl = ($LASTEXITCODE -eq 0) } catch { $useWsl = $false }

if ($useWsl) {
    if ($free -lt $total + 1GB) { throw "Not enough free space: need about $([math]::Ceiling(($total + 1GB) / 1GB)) GB." }
    $wdir = (wsl.exe -e wslpath -a "$dir").Trim()
    Say "`nDecrypting with Ubuntu (WSL). Type your WRAITH_ISO_KEY when asked (nothing shows while you type)."
    $cmd = "cd '$wdir' && cat '$name'.iso.gpg.part* | gpg --pinentry-mode loopback --decrypt --output '$name.iso'"
    wsl.exe -e bash -c $cmd
    if ($LASTEXITCODE -ne 0) { if (Test-Path $iso) { Remove-Item $iso }; throw 'Decryption failed (wrong passphrase?).' }
} else {
    $gpg = @("${env:ProgramFiles(x86)}\GnuPG\bin\gpg.exe", "$env:ProgramFiles\GnuPG\bin\gpg.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
    if (-not $gpg) { throw 'Neither Ubuntu (WSL) nor Gpg4win was found. Install Gpg4win from https://gpg4win.org and run this again.' }
    if ($free -lt 2 * $total + 1GB) { throw "Not enough free space: need about $([math]::Ceiling((2 * $total + 1GB) / 1GB)) GB." }
    # Gpg4win route: join the parts into one file first
    $joined = Join-Path $dir "$name.iso.gpg"
    $out = [IO.File]::Create($joined)
    try {
        $i = 0
        foreach ($p in $parts) {
            $i++
            Write-Progress -Activity 'Joining the parts' -Status "$($p.Name) ($i of $($parts.Count))" -PercentComplete (($i - 1) * 100 / $parts.Count)
            $in = [IO.File]::OpenRead($p.FullName)
            try { $in.CopyTo($out, 8MB) } finally { $in.Close() }
        }
    } finally { $out.Close() }
    Write-Progress -Activity 'Joining the parts' -Completed
    Say "`nDecrypting with Gpg4win. A window asks for your WRAITH_ISO_KEY."
    & $gpg --decrypt --output $iso $joined
    $rc = $LASTEXITCODE
    Remove-Item $joined
    if ($rc -ne 0) { if (Test-Path $iso) { Remove-Item $iso }; throw 'Decryption failed (wrong passphrase?).' }
}

$sizeGB = [math]::Round((Get-Item $iso).Length / 1GB, 1)
Say "`nDone: $iso ($sizeGB GB)" 'Green'
Say 'You can delete the .part files now.'
Say "`nNext: create the virtual machine - 8 GB RAM, 2+ CPU cores, 80 GB+ disk," 'White'
Say '3D acceleration ON, Secure Boot OFF - and boot it from this ISO.' 'White'
Read-Host "`nPress Enter to close"
