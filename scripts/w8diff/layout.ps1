# Field offsets of the port's structs (with the same MSVC flags as the port build).
#   powershell -File scripts\w8diff\layout.ps1 -Header wiz8/layouts/character.h -Expr "sizeof(W8Character); offsetof(W8Character, skills); offsetof(W8Character, attributes[2].effective)"
# -Header: several, comma-separated; -Expr: expressions separated by ";". Prints "expression = 0xNNN".
param(
    [string]$Header = 'wiz8/layouts/character.h',
    [Parameter(Mandatory = $true)][string]$Expr
)
$ErrorActionPreference = 'Stop'
$root = Resolve-Path (Join-Path $PSScriptRoot '..\..')
. "$root\Tools\msvcenv.ps1"
$dir = Join-Path $root 'build\w8diff\layout'
New-Item -ItemType Directory -Force $dir | Out-Null
$src = Join-Path $dir 'probe.cpp'
$lines = @('#include <stddef.h>', '#include <stdio.h>')
foreach ($h in ($Header -split ',' | ForEach-Object { $_.Trim() } | Where-Object { $_ })) { $lines += "#include `"$h`"" }
$lines += 'int main() {'
foreach ($e in ($Expr -split ';' | ForEach-Object { $_.Trim() } | Where-Object { $_ })) {
    $esc = $e.Replace('\', '\\').Replace('"', '\"')
    $lines += "    printf(`"%s = 0x%x\n`", `"$esc`", (unsigned)($e));"
}
$lines += '    return 0;', '}'
Set-Content -Path $src -Value $lines -Encoding UTF8
$inc = "$root\decomp\include"
$ErrorActionPreference = 'Continue'
Push-Location $dir
try {
    $o = & cl /nologo /EHs- /DWIN32 /D_WINDOWS /DNDEBUG /DNOMINMAX /DWIN32_LEAN_AND_MEAN /D_CRT_SECURE_NO_WARNINGS `
        "/FI$inc\wiz8\compat\compiler.h" "/FI$inc\wiz8\compat\msvc2022.h" /Zc:wchar_t- /permissive /arch:IA32 `
        /source-charset:utf-8 /wd4430 /wd4996 /wd4068 /wd4530 /GR- `
        "/I$inc\wiz8\compat\modern_msvc" "/I$inc" "/I$inc\wiz8" "/I$inc\wiz8\engine_code" "/I$root\decomp\src\sgp" `
        probe.cpp /Fe:probe.exe 2>&1
    if ($LASTEXITCODE -ne 0) { $o | Where-Object { $_ -match 'error' } | Select-Object -First 15; throw 'probe compile failed' }
    & .\probe.exe
} finally { Pop-Location }
