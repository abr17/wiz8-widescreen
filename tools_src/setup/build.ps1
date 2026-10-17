# Builds Wiz8WideSetup.exe (x86, static, no dependencies) into build\setup\.
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot '..\..\Tools\env.ps1')
$root = Resolve-Path (Join-Path $PSScriptRoot '..\..')
$out = Join-Path $root 'build\setup'
New-Item -ItemType Directory -Force $out | Out-Null
$manifest = Join-Path $PSScriptRoot 'setup.manifest'
$rc = Join-Path $out 'setup.rc'
"1 24 `"$($manifest -replace '\\','/')`"" | Set-Content -Encoding ascii $rc
$res = Join-Path $out 'setup_res.o'
& i686-w64-mingw32-windres $rc -O coff -o $res
if ($LASTEXITCODE) { throw 'windres failed' }
& i686-w64-mingw32-g++ -std=c++17 -O2 -municode -mwindows -static -s `
    (Join-Path $PSScriptRoot 'setup.cpp') $res -o (Join-Path $out 'Wiz8WideSetup.exe') `
    -lbcrypt -lcomctl32 -lshell32 -lole32
if ($LASTEXITCODE) { throw 'compile failed' }
Get-Item (Join-Path $out 'Wiz8WideSetup.exe')
