# Build wiz8hy.dll (the hybrid: port functions for the original Wiz8.exe).
#   powershell -File scripts\hybrid\build_hybrid.ps1 [-Install] [-NoCompile]
# -Install: copy wiz8hy.dll and wiz8hy_hooks.txt into games\work. Details: docs\hybrid.md.
param([switch]$Install, [switch]$NoCompile, [string]$Config = '')
$ErrorActionPreference = 'Stop'
$root = Resolve-Path (Join-Path $PSScriptRoot '..\..')
. "$root\Tools\msvcenv.ps1"
$ErrorActionPreference = 'Continue'
$env:PYTHONIOENCODING = 'utf-8'
$args2 = @()
if ($NoCompile) { $args2 += '--no-compile' }
if ($Config) { $args2 += @('--config', (Resolve-Path $Config).Path) }
& python -I (Join-Path $PSScriptRoot 'build_hybrid.py') @args2
if ($LASTEXITCODE -ne 0) { throw 'build_hybrid failed' }
if ($Install) {
    Copy-Item "$root\build\hybrid\wiz8hy.dll", "$root\build\hybrid\wiz8hy_hooks.txt" "$root\games\work" -Force
    'installed to games\work'
}
