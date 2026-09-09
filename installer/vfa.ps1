$ErrorActionPreference = 'Stop'
$VfaRoot = Split-Path $PSScriptRoot -Parent
$ProductRoot = $VfaRoot
if (Test-Path "$VfaRoot/product-root") { $ProductRoot = (Get-Content "$VfaRoot/product-root" -Raw).Trim() }
if (!(Test-Path $ProductRoot -PathType Container)) { throw 'DIRECT_CREDENTIAL_NOT_FOUND: Selected product directory is unavailable.' }
foreach ($Name in @('image','revision','image-digest')) { if (!(Test-Path "$VfaRoot/$Name")) { throw 'RUNTIME_IMAGE_IDENTITY_NOT_RESOLVED' } }
$Image = (Get-Content "$VfaRoot/image" -Raw).Trim()
$Revision = (Get-Content "$VfaRoot/revision" -Raw).Trim()
$Digest = (Get-Content "$VfaRoot/image-digest" -Raw).Trim()
if ($Image -ne $Digest -or $Revision -notmatch '^[a-f0-9]{40}$' -or $Digest -notmatch '^sha256:[a-f0-9]{64}$') { throw 'RUNTIME_IMAGE_IDENTITY_NOT_RESOLVED' }
docker info *> $null
if ($LASTEXITCODE -ne 0) { throw 'DOCKER_NOT_RUNNING: Start Docker Desktop, then run vfa start.' }
$DockerArgs = @('run', '--rm', '-it', '-v', '/var/run/docker.sock:/var/run/docker.sock', '-v', "${VfaRoot}:/install", '-e', "VFA_HOST_ROOT=$($VfaRoot.Replace('\','/'))")
if (Test-Path "$ProductRoot/credentials" -PathType Container) { $DockerArgs += @('-v', "${ProductRoot}/credentials:/credentials/product:ro") }
foreach ($Folder in @('Downloads','Desktop')) {
    $Local = Join-Path $env:USERPROFILE $Folder
    if (Test-Path $Local) { $DockerArgs += @('-v', "${Local}:/credentials/$($Folder.ToLower()):ro") }
}
& docker @DockerArgs $Image python -m installer.cli --image $Image --expected-revision $Revision --expected-image-digest $Digest @args
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
if ((Test-Path "$VfaRoot/open-browser") -and ((Get-Content "$VfaRoot/open-browser" -Raw).Trim() -eq 'http://127.0.0.1:4173')) {
    Start-Process 'http://127.0.0.1:4173'
}
