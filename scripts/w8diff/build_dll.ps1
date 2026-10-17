# Build w8diff.dll (the comparison test stand core for the original Wiz8.exe) with portable MSVC x86.
#   powershell -File scripts\w8diff\build_dll.ps1 [-Install]
# Output: build\w8diff\w8diff.dll; -Install copies it into games\work.
param([switch]$Install)
$ErrorActionPreference = 'Stop'
$root = Resolve-Path (Join-Path $PSScriptRoot '..\..')
. "$root\Tools\msvcenv.ps1"
$out = Join-Path $root 'build\w8diff'
New-Item -ItemType Directory -Force $out | Out-Null
$core = Join-Path $root 'decomp\src\w8diff'
Push-Location $out
try {
    & cl /nologo /O2 /MT /GS- /W3 /LD /arch:IA32 "/I$core" `
        "$core\w8diff_core.c" "$root\src\w8diff_dll\w8diff_dll.c" `
        /Fe:w8diff.dll /link /NOLOGO kernel32.lib 2>&1 | Where-Object { $_ -and $_ -notmatch '^(w8diff_core|w8diff_dll)\.c$' }
    if ($LASTEXITCODE -ne 0) { throw "cl failed ($LASTEXITCODE)" }
} finally { Pop-Location }
"built: $out\w8diff.dll"
if ($Install) {
    Copy-Item "$out\w8diff.dll" (Join-Path $root 'games\work') -Force
    "installed to games\work"
}
