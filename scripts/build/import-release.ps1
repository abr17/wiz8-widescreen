# Fills assets\ from a released Wizardry 8 Widescreen zip, so the repository can be built
# without any game-derived file in git.
#   pwsh -File scripts\build\import-release.ps1 -Zip <Wiz8Widescreen-x.y.z.zip> [-Force] [-Binaries]
# assets\ gets the release's files\Data\ (wide .STI art, FALCON.STI) and the dgVoodoo files
# (DDraw.dll, D3DImm.dll, dgVoodoo.conf), laid out like the game folder.
#   -Force     overwrite files already in assets\ (default: keep them and report differences)
#   -Binaries  also copy the prebuilt version.dll to build\ and wiz8hy.dll + wiz8hy_hooks.txt
#              to build\hybrid\, for working on the installer, the art or the package without
#              building the game code (they are build outputs: a real build replaces them)
param([Parameter(Mandatory)][string]$Zip, [switch]$Force, [switch]$Binaries)
$ErrorActionPreference = 'Stop'
$root = Resolve-Path (Join-Path $PSScriptRoot '..\..')
$zipPath = (Resolve-Path $Zip).Path
$tmp = Join-Path $root 'build\tmp\import-release'
if (Test-Path -LiteralPath $tmp) { Remove-Item -LiteralPath $tmp -Recurse -Force }
New-Item -ItemType Directory -Force -Path $tmp | Out-Null
Expand-Archive -LiteralPath $zipPath -DestinationPath $tmp
$files = Join-Path $tmp 'files'
if (-not (Test-Path -LiteralPath (Join-Path $files 'Data'))) {
    throw "no files\Data in $zipPath - is this a Wizardry 8 Widescreen release zip?"
}

$assets = Join-Path $root 'assets'
$copied = 0; $same = 0; $kept = @()
function Import([string]$src, [string]$rel) {
    $dst = Join-Path $assets $rel
    if (Test-Path -LiteralPath $dst) {
        if ((Get-FileHash -LiteralPath $src).Hash -eq (Get-FileHash -LiteralPath $dst).Hash) { $script:same++; return }
        if (-not $Force) { $script:kept += $rel; return }
    }
    New-Item -ItemType Directory -Force -Path (Split-Path $dst -Parent) | Out-Null
    Copy-Item -LiteralPath $src -Destination $dst -Force
    $script:copied++
}
foreach ($f in Get-ChildItem -LiteralPath (Join-Path $files 'Data') -Recurse -File) {
    Import $f.FullName $f.FullName.Substring($files.Length + 1)
}
foreach ($name in 'DDraw.dll', 'D3DImm.dll', 'dgVoodoo.conf') {
    Import (Join-Path $files $name) $name
}
"assets: $copied copied, $same already identical, $($kept.Count) different and kept (use -Force to overwrite)"
foreach ($k in $kept) { "  kept: $k" }

if ($Binaries) {
    New-Item -ItemType Directory -Force -Path (Join-Path $root 'build\hybrid') | Out-Null
    Copy-Item -LiteralPath (Join-Path $files 'version.dll') -Destination (Join-Path $root 'build\version.dll') -Force
    # the DLL and its hook list always travel together (a mismatch crashes the game at start-up)
    Copy-Item -LiteralPath (Join-Path $files 'wiz8hy.dll') -Destination (Join-Path $root 'build\hybrid\wiz8hy.dll') -Force
    Copy-Item -LiteralPath (Join-Path $files 'wiz8hy_hooks.txt') -Destination (Join-Path $root 'build\hybrid\wiz8hy_hooks.txt') -Force
    'binaries: build\version.dll, build\hybrid\wiz8hy.dll + wiz8hy_hooks.txt (prebuilt from the release)'
}
Remove-Item -LiteralPath $tmp -Recurse -Force
