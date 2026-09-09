$ErrorActionPreference = 'Stop'
$VfaRoot = Split-Path $PSScriptRoot -Parent
$ProductRoot = $VfaRoot
if (Test-Path "$VfaRoot/product-root") { $ProductRoot = (Get-Content "$VfaRoot/product-root" -Raw).Trim() }
if (!(Test-Path $ProductRoot -PathType Container)) { throw 'DIRECT_CREDENTIAL_NOT_FOUND: Selected product directory is unavailable.' }
$Image = 'vfa-evaluator:source'
if (Test-Path "$VfaRoot/image") { $Image = (Get-Content "$VfaRoot/image" -Raw).Trim() }
if ($Image -notmatch '^vfa-evaluator:[a-zA-Z0-9._-]+$') { throw 'INSTALLATION_FAILED' }
docker info *> $null
if ($LASTEXITCODE -ne 0) { throw 'DOCKER_NOT_RUNNING: Start Docker Desktop, then run vfa start.' }
$DockerArgs = @('run', '--rm', '-it', '-v', '/var/run/docker.sock:/var/run/docker.sock', '-v', "${VfaRoot}:/install", '-e', "VFA_HOST_ROOT=$($VfaRoot.Replace('\','/'))")
if (Test-Path "$ProductRoot/credentials" -PathType Container) { $DockerArgs += @('-v', "${ProductRoot}/credentials:/credentials/product:ro") }
foreach ($Folder in @('Downloads','Desktop')) {
    $Local = Join-Path $env:USERPROFILE $Folder
    if (Test-Path $Local) { $DockerArgs += @('-v', "${Local}:/credentials/$($Folder.ToLower()):ro") }
}
& docker @DockerArgs $Image python -m installer.cli @args
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
if ((Test-Path "$VfaRoot/open-browser") -and ((Get-Content "$VfaRoot/open-browser" -Raw).Trim() -eq 'http://127.0.0.1:4173')) {
    Start-Process 'http://127.0.0.1:4173'
}
