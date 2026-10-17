# Adds portable MSVC 2022 (x86) to the current PowerShell session.
#   . C:\dev\wiz8-ws\Tools\msvcenv.ps1
$M = Join-Path $PSScriptRoot 'msvc'
$vc = Get-ChildItem "$M\VC\Tools\MSVC" | Select-Object -First 1 -ExpandProperty FullName
$sdkv = Get-ChildItem "$M\Windows Kits\10\bin" -Directory | Where-Object Name -like '10.*' | Select-Object -First 1 -ExpandProperty Name
$K = "$M\Windows Kits\10"
$env:PATH = "$vc\bin\Hostx64\x86;$K\bin\$sdkv\x64;$K\bin\$sdkv\x64\ucrt;$PSScriptRoot\cmake\bin;$env:PATH"
$env:INCLUDE = "$vc\include;$K\Include\$sdkv\ucrt;$K\Include\$sdkv\shared;$K\Include\$sdkv\um;$K\Include\$sdkv\winrt"
$env:LIB = "$vc\lib\x86;$K\Lib\$sdkv\ucrt\x86;$K\Lib\$sdkv\um\x86"
$env:TMP = $env:TEMP = Join-Path $PSScriptRoot '..\build\tmp'
New-Item -ItemType Directory -Force $env:TMP | Out-Null
