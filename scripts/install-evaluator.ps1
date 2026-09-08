param([string]$Version)
$ErrorActionPreference = 'Stop'
$VfaSource = if ($PSScriptRoot) { Split-Path $PSScriptRoot -Parent } else { '' }
$VfaRoot = Join-Path $env:LOCALAPPDATA 'Verifiable Financial Agent'
$SourceMode = $true
if (!(Test-Path "$VfaSource/installer/Dockerfile") -or $Version) {
    $SourceMode = $false
    $Ref = 'latest'
    if ($Version) {
        if ($Version -notmatch '^[a-zA-Z0-9._-]+$') { throw 'PUBLICATION_REQUIRED' }
        $Ref = "tags/$Version"
    }
    try {
        $Release = Invoke-RestMethod "https://api.github.com/repos/linyiji/verifiable-financial-ai-agent/releases/$Ref"
        if ($Release.draft -or ($Ref -eq 'latest' -and $Release.prerelease)) { throw 'Invalid release' }
        $Version = $Release.tag_name
        if ($Version -notmatch '^[a-zA-Z0-9._-]+$') { throw 'Invalid release' }
        $Prefix = "https://github.com/linyiji/verifiable-financial-ai-agent/releases/download/$Version/"
        $Manifest = Invoke-RestMethod "${Prefix}evaluator-manifest.json"
    } catch { throw 'PUBLICATION_REQUIRED: No accepted installer package is published.' }
    if ($Manifest.schema -ne 1 -or $Manifest.version -ne $Version -or !$Manifest.archive_url.StartsWith($Prefix) -or $Manifest.sha256 -notmatch '^[a-f0-9]{64}$') { throw 'INTEGRITY_FAILED' }
    $Download = Join-Path $VfaRoot "packages/$([guid]::NewGuid())"
    New-Item -ItemType Directory -Force $Download | Out-Null
    Invoke-WebRequest $Manifest.archive_url -OutFile "$Download/product.zip"
    if ((Get-FileHash "$Download/product.zip" -Algorithm SHA256).Hash.ToLower() -ne $Manifest.sha256) { throw 'INTEGRITY_FAILED' }
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $Archive = [System.IO.Compression.ZipFile]::OpenRead("$Download/product.zip")
    try {
        foreach ($Entry in $Archive.Entries) {
            if ($Entry.FullName -match '(^/|(^|/)\.\.(/|$)|\\|:)') { throw 'INTEGRITY_FAILED' }
        }
    } finally { $Archive.Dispose() }
    Expand-Archive "$Download/product.zip" "$Download/app"
    $VfaSource = "$Download/app"
}
if (!(Get-Command docker -ErrorAction SilentlyContinue)) {
    $Answer = Read-Host 'Install Docker Desktop using Windows Package Manager? [y/N]'
    if ($Answer -eq 'y' -and (Get-Command winget -ErrorAction SilentlyContinue)) {
        winget install --exact --id Docker.DockerDesktop
        if ($LASTEXITCODE -in @(3010, 1641)) {
            Write-Host 'REBOOT_REQUIRED: Restart Windows once, then run the same install command again.'
            exit 1
        }
    } else { Start-Process 'https://docs.docker.com/desktop/setup/install/windows-install/' }
    Write-Host 'DOCKER_NOT_INSTALLED: Complete Docker Desktop setup, then run this command again.'
    exit 1
}
docker info *> $null
if ($LASTEXITCODE -ne 0) { throw 'DOCKER_NOT_RUNNING: Start Docker Desktop and run this command again.' }
docker compose version *> $null
if ($LASTEXITCODE -ne 0) { throw 'DOCKER_NOT_INSTALLED: Docker Compose is required. Repair Docker Desktop.' }
New-Item -ItemType Directory -Force "$VfaRoot/bin", "$VfaRoot/logs" | Out-Null
# Protect generated infrastructure secrets and installer metadata with the current user ACL.
$Identity = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
icacls $VfaRoot /inheritance:r /grant:r "${Identity}:(OI)(CI)F" *> $null
if ($LASTEXITCODE -ne 0) { throw 'INSTALLATION_FAILED: Could not protect the local data directory.' }
Write-Host 'Verifiable Financial Agent — Preparing product (first build can take several minutes).'
docker build -f "$VfaSource/installer/Dockerfile" -t vfa-evaluator:source $VfaSource *> "$VfaRoot/logs/build.log"
if ($LASTEXITCODE -ne 0) { throw 'INSTALLATION_FAILED: Run this command again; private build logs are retained.' }
Copy-Item "$VfaSource/installer/vfa.ps1" "$VfaRoot/bin/vfa.ps1" -Force
Copy-Item "$VfaSource/installer/vfa.cmd" "$VfaRoot/bin/vfa.cmd" -Force
$UserPath = [Environment]::GetEnvironmentVariable('Path', 'User')
if (($UserPath -split ';') -notcontains "$VfaRoot/bin") {
    [Environment]::SetEnvironmentVariable('Path', "$VfaRoot/bin;$UserPath", 'User')
}
$env:Path = "$VfaRoot/bin;$env:Path"
if ($SourceMode) { & "$VfaRoot/bin/vfa.ps1" install --source }
else { & "$VfaRoot/bin/vfa.ps1" install --version $Version }
