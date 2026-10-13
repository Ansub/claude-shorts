# Native Windows setup, compatible with Windows PowerShell 5.1 and PowerShell 7.
# Run: powershell -NoProfile -ExecutionPolicy Bypass -File .\setup.ps1
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$Cache = if ($env:CLAUDE_SHORTS_CACHE) { $env:CLAUDE_SHORTS_CACHE } else { Join-Path $HOME '.cache\claude-shorts' }
$env:CLAUDE_SHORTS_CACHE = $Cache
$env:PYTHONUTF8 = '1'
$Bin = Join-Path $Cache 'bin'
$Venv = Join-Path $Cache 'venv'
$Py = Join-Path $Venv 'Scripts\python.exe'
New-Item -ItemType Directory -Force -Path $Bin | Out-Null

function Refresh-Path {
    $env:PATH = "$Bin;" + [Environment]::GetEnvironmentVariable('Path', 'User') + ';' + [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' + $env:PATH
}
function Invoke-Checked {
    param([string]$Exe, [string[]]$Arguments)
    & $Exe @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Exe failed with exit code $LASTEXITCODE. Rerun setup after fixing the reported error." }
}
Refresh-Path
if (-not (Get-Command winget.exe -ErrorAction SilentlyContinue)) {
    # Microsoft's supported WinGet bootstrap; no Store navigation or manual install.
    Install-PackageProvider -Name NuGet -Force -Scope CurrentUser | Out-Null
    Install-Module Microsoft.WinGet.Client -Repository PSGallery -Force -Scope CurrentUser
    Import-Module Microsoft.WinGet.Client
    Repair-WinGetPackageManager
    Refresh-Path
}
function Install-UserPackage {
    param([string]$Id)
    Invoke-Checked 'winget.exe' @('install', '--id', $Id, '--exact', '--source', 'winget', '--scope', 'user', '--accept-package-agreements', '--accept-source-agreements', '--disable-interactivity')
    Refresh-Path
}
if (-not (Get-Command ffmpeg.exe -ErrorAction SilentlyContinue) -or -not (Get-Command ffprobe.exe -ErrorAction SilentlyContinue)) {
    Install-UserPackage 'Gyan.FFmpeg'
}
if (-not (Get-Command yt-dlp.exe -ErrorAction SilentlyContinue)) { Install-UserPackage 'yt-dlp.yt-dlp' }

# Prefer a known per-user Python over the Windows Store execution alias.
$Python = Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe'
if (-not (Test-Path $Python)) {
    $Candidate = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($Candidate -and $Candidate.Source -notlike '*\WindowsApps\*') {
        & $Candidate.Source -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)'
        if ($LASTEXITCODE -eq 0) { $Python = $Candidate.Source }
    }
}
if (-not (Test-Path $Python)) {
    # A custom/all-users Python may only be registered with the py launcher.
    $Launcher = Get-Command py.exe -ErrorAction SilentlyContinue
    if ($Launcher) {
        $Located = & $Launcher.Source -3 -c 'import sys; print(sys.executable) if sys.version_info >= (3, 10) else sys.exit(1)'
        if ($LASTEXITCODE -eq 0 -and $Located -and (Test-Path $Located)) { $Python = $Located }
    }
}
if (-not (Test-Path $Python)) { Install-UserPackage 'Python.Python.3.12' }
if (-not (Test-Path $Python)) { throw 'Python installation did not produce a usable interpreter. Check the winget output and rerun setup.' }

$Whisper = Join-Path $Bin 'whisper-cli.exe'
if (-not (Test-Path $Whisper) -and -not (Get-Command whisper-cli.exe -ErrorAction SilentlyContinue)) {
    $Arch = if ($env:PROCESSOR_ARCHITEW6432) { $env:PROCESSOR_ARCHITEW6432 } else { $env:PROCESSOR_ARCHITECTURE }
    if ($Arch -notin @('AMD64', 'ARM64')) { throw 'Windows requires a 64-bit PC (x64 or ARM64).' }
    # CPU build needs no GPU/CUDA. ARM64 uses Windows 11 x64 emulation if no native asset exists.
    $Headers = @{ 'User-Agent' = 'claude-shorts-setup'; 'Accept' = 'application/vnd.github+json' }
    $Releases = Invoke-RestMethod 'https://api.github.com/repos/ggml-org/whisper.cpp/releases?per_page=30' -Headers $Headers
    $Asset = $null
    foreach ($Release in $Releases) {
        if ($Release.prerelease -or $Release.draft) { continue }
        if ($Arch -eq 'ARM64') {
            $Asset = $Release.assets | Where-Object { $_.name -eq 'whisper-bin-arm64.zip' } | Select-Object -First 1
        }
        if (-not $Asset) { $Asset = $Release.assets | Where-Object { $_.name -eq 'whisper-bin-x64.zip' } | Select-Object -First 1 }
        if ($Asset) { break }
    }
    if (-not $Asset) { throw 'No official Windows CPU release found. Rerun later; do not download an unofficial executable.' }
    $Zip = Join-Path $Cache 'whisper.zip'
    Invoke-WebRequest $Asset.browser_download_url -OutFile $Zip -UseBasicParsing
    if ($Asset.PSObject.Properties.Name -contains 'digest' -and $Asset.digest -like 'sha256:*') {
        $Expected = $Asset.digest.Substring(7)
        if ((Get-FileHash $Zip -Algorithm SHA256).Hash -ne $Expected) { throw 'Whisper archive checksum mismatch.' }
    }
    $Stage = Join-Path $Cache ('whisper-' + [Guid]::NewGuid().ToString('N'))
    try {
        Expand-Archive -Path $Zip -DestinationPath $Stage
        $Cli = Get-ChildItem $Stage -Filter whisper-cli.exe -Recurse | Select-Object -First 1
        if (-not $Cli) { throw 'Official release did not contain whisper-cli.exe.' }
        # Keep all sibling DLLs (ggml, whisper, runtime) alongside the executable.
        Copy-Item (Join-Path $Cli.DirectoryName '*') $Bin -Recurse -Force
    } finally {
        if (Test-Path $Stage) { Remove-Item $Stage -Recurse -Force }
        Remove-Item $Zip -Force
    }
}
# Some official builds require Microsoft's VC++ runtime. Install it only if the DLL loader fails.
$WhisperCommand = Get-Command whisper-cli.exe -ErrorAction SilentlyContinue
$WhisperTest = if (Test-Path $Whisper) { $Whisper } elseif ($WhisperCommand) { $WhisperCommand.Source } else { throw 'Whisper CLI not found.' }
$Probe = Start-Process -FilePath $WhisperTest -ArgumentList '--help' -Wait -PassThru -NoNewWindow
if ($Probe.ExitCode -eq -1073741515) {
    Write-Host 'Installing the Microsoft C++ runtime; Windows may show a UAC prompt.'
    Invoke-Checked 'winget.exe' @('install', '--id', 'Microsoft.VCRedist.2015+.x64', '--exact', '--source', 'winget', '--accept-package-agreements', '--accept-source-agreements')
} elseif ($Probe.ExitCode -ne 0) { throw "Whisper failed to start (exit $($Probe.ExitCode)). Check CPU compatibility and rerun setup." }
$UserPath = [Environment]::GetEnvironmentVariable('Path', 'User')
if (($UserPath -split ';') -notcontains $Bin) {
    [Environment]::SetEnvironmentVariable('Path', "$Bin;$UserPath", 'User')
}
Refresh-Path
if (-not (Test-Path $Py)) { Invoke-Checked $Python @('-m', 'venv', $Venv) }
Invoke-Checked $Py @('-m', 'pip', 'install', '--quiet', '--only-binary=:all:', 'pillow', 'resvg-py>=0.3,<1', 'yt-dlp')
Invoke-Checked $Py @((Join-Path $PSScriptRoot 'scripts\check_setup.py'))
Invoke-Checked $Py @('-c', 'import sys; sys.path.insert(0, sys.argv[1]); from platform_tools import download_model; download_model()', (Join-Path $PSScriptRoot 'scripts'))
New-Item -ItemType Directory -Force -Path (Join-Path $HOME '.config\claude-shorts\fonts') | Out-Null
Write-Host 'claude-shorts is ready. In Claude Code, type /claude-shorts. New sessions will inherit the updated PATH.'
