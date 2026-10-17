# Builds the hybrid package: build\package\Wiz8Widescreen\ and build\package\Wiz8Widescreen.zip.
#   pwsh -File scripts\build\make-hybrid-package.ps1
# First build version.dll (build.ps1) and wiz8hy.dll (scripts\hybrid\build_hybrid.ps1 -Config
# scripts\hybrid\transplant_wide.json). Package contents: Wiz8WideSetup.exe, files\ (what
# goes into the game folder; also usable for a manual install), README in four languages from dist\.
# Finished releases are kept separately in release\ (this script does not write there).
$ErrorActionPreference = 'Stop'
$root = Resolve-Path (Join-Path $PSScriptRoot '..\..')
$assets = Join-Path $root 'assets'
$out = Join-Path $root 'build\package\Wiz8Widescreen'
$files = Join-Path $out 'files'
if (Test-Path -LiteralPath $out) { Remove-Item -LiteralPath $out -Recurse -Force }
New-Item -ItemType Directory -Force -Path $files | Out-Null

function Put([string]$src, [string]$rel) {
    if (-not (Test-Path -LiteralPath $src)) { throw "missing file: $src" }
    $dst = Join-Path $files $rel
    New-Item -ItemType Directory -Force -Path (Split-Path $dst -Parent) | Out-Null
    Copy-Item -LiteralPath $src -Destination $dst
}

& pwsh -NoProfile -File "$root\tools_src\setup\build.ps1" | Out-Null
if ($LASTEXITCODE) { throw 'installer build failed' }

Put "$root\build\version.dll" 'version.dll'
# dll and hook list always as a pair (a mismatch = crash at startup)
Put "$root\build\hybrid\wiz8hy.dll" 'wiz8hy.dll'
Put "$root\build\hybrid\wiz8hy_hooks.txt" 'wiz8hy_hooks.txt'
Put "$root\dist\wiz8ws.ini" 'wiz8ws.ini'
Put "$root\dist\wiz8wide.ini" 'wiz8wide.ini'
# assets\ (not in git): wide art, FALCON.STI (the exit advertisement screen, which is
# missing from the Russian translation data) and dgVoodoo 2 (without it the game cannot open videos on modern Windows)
$count = 0
foreach ($f in Get-ChildItem -LiteralPath $assets -Recurse -File) {
    Put $f.FullName $f.FullName.Substring($assets.Length + 1); $count++
}
Copy-Item -LiteralPath "$root\build\setup\Wiz8WideSetup.exe" -Destination $out
foreach ($f in Get-ChildItem -LiteralPath "$root\dist" -Filter 'README_*.txt') {
    Copy-Item -LiteralPath $f.FullName -Destination $out
}

$zip = Join-Path $root 'build\package\Wiz8Widescreen.zip'
if (Test-Path -LiteralPath $zip) { Remove-Item -LiteralPath $zip -Force }
Compress-Archive -Path "$out\*" -DestinationPath $zip
$size = [math]::Round((Get-Item -LiteralPath $zip).Length / 1MB, 1)
"package: $out ($count files from assets), archive: $zip ($size MB)"
