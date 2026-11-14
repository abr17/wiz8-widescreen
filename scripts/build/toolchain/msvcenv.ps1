# Adds portable MSVC 2022 (x86) to the current PowerShell session.
#   . .\Tools\msvcenv.ps1   (from the workspace folder)
$M = Join-Path $PSScriptRoot 'msvc'
$vc = Get-ChildItem "$M\VC\Tools\MSVC" | Select-Object -First 1 -ExpandProperty FullName
$sdkv = Get-ChildItem "$M\Windows Kits\10\bin" -Directory | Where-Object Name -like '10.*' | Select-Object -First 1 -ExpandProperty Name
$K = "$M\Windows Kits\10"
$env:PATH = "$vc\bin\Hostx64\x86;$K\bin\$sdkv\x64;$K\bin\$sdkv\x64\ucrt;$PSScriptRoot\cmake\bin;$env:PATH"
$env:INCLUDE = "$vc\include;$K\Include\$sdkv\ucrt;$K\Include\$sdkv\shared;$K\Include\$sdkv\um;$K\Include\$sdkv\winrt"
$env:LIB = "$vc\lib\x86;$K\Lib\$sdkv\ucrt\x86;$K\Lib\$sdkv\um\x86"
$env:TMP = $env:TEMP = Join-Path $PSScriptRoot '..\build\tmp'
New-Item -ItemType Directory -Force $env:TMP | Out-Null
# The render driver's build (drivers\srdd_d3d11\build.ps1 loads this script when cl.exe is not on
# PATH) checks the driver's ABI with llvm-objdump, which it takes from LLVM_OBJDUMP or PATH: name
# the one of Tools\llvm-mingw unless the caller named another.
if (-not $env:LLVM_OBJDUMP -and (Test-Path -LiteralPath "$PSScriptRoot\llvm-mingw\bin\llvm-objdump.exe")) {
    $env:LLVM_OBJDUMP = "$PSScriptRoot\llvm-mingw\bin\llvm-objdump.exe"
}
