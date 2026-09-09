param([Parameter(Mandatory=$true)][string]$SourceRoot)
$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path -LiteralPath $SourceRoot).Path
if (Test-Path -LiteralPath "$Root/.git") {
    if (!(Get-Command git -ErrorAction SilentlyContinue)) { throw 'BUILD_INPUT_GIT_REQUIRED' }
    $Scope = @('src','apps','contracts','installer','scripts','alembic','zk','runtime','pyproject.toml','.dockerignore')
    git -C $Root diff --quiet HEAD -- @Scope
    if ($LASTEXITCODE -ne 0) { throw 'BUILD_INPUT_DIRTY' }
    $Untracked = git -C $Root ls-files --others --exclude-standard -- @Scope
    if ($LASTEXITCODE -ne 0 -or $Untracked) { throw 'BUILD_INPUT_UNDECLARED' }
    Write-Host 'BUILD_INPUTS = REVIEWED_GIT'
    return
}
$Manifest = Join-Path $Root 'evaluator-build-inputs.sha256'
if (!(Test-Path -LiteralPath $Manifest -PathType Leaf)) { throw 'BUILD_INPUT_MANIFEST_REQUIRED' }
$Seen = @{}
foreach ($Line in Get-Content -LiteralPath $Manifest) {
    if ($Line -notmatch '^([a-f0-9]{64})  ([A-Za-z0-9_./-]+)$') { throw 'BUILD_INPUT_PATH_UNSAFE' }
    $Digest, $Relative = $Matches[1], $Matches[2]
    if ($Relative.StartsWith('/') -or $Relative -match '(^|/)\.\.?(/|$)|//' -or $Seen.ContainsKey($Relative)) { throw 'BUILD_INPUT_PATH_UNSAFE' }
    $Path = Join-Path $Root $Relative
    if (!(Test-Path -LiteralPath $Path -PathType Leaf)) { throw 'BUILD_INPUT_MISSING' }
    $Item = Get-Item -LiteralPath $Path
    if ($Item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'BUILD_INPUT_PATH_UNSAFE' }
    if ((Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLower() -ne $Digest) { throw 'BUILD_INPUT_CONTENT_MISMATCH' }
    $Seen[$Relative] = $true
}
if ($Seen.Count -eq 0) { throw 'BUILD_INPUT_MANIFEST_EMPTY' }
foreach ($Directory in @('src','apps','installer','scripts','contracts','alembic','zk','runtime')) {
    $Path = Join-Path $Root $Directory
    if (!(Test-Path -LiteralPath $Path)) { continue }
    foreach ($Item in Get-ChildItem -LiteralPath $Path -File -Recurse) {
        $Relative = $Item.FullName.Substring($Root.Length + 1).Replace('\','/')
        if ($Relative -match '(^|/)(__pycache__|node_modules|dist)/') { continue }
        if (!$Seen.ContainsKey($Relative)) { throw 'BUILD_INPUT_UNDECLARED' }
    }
}
Write-Host 'BUILD_INPUTS = MANIFEST_VERIFIED'
