# Builds Wiz8WideSetup.exe (x86, static, no dependencies) into build\setup\.
# The version comes from VERSION in the repository root (window title, manifest list, file properties).
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot '..\..\Tools\env.ps1')
$root = Resolve-Path (Join-Path $PSScriptRoot '..\..')
$out = Join-Path $root 'build\setup'
New-Item -ItemType Directory -Force $out | Out-Null
$version = (Get-Content -LiteralPath (Join-Path $root 'VERSION') -TotalCount 1).Trim()
if ($version -notmatch '^\d+\.\d+\.\d+$') { throw "VERSION must look like 1.2.3, got '$version'" }
$numbers = "$version.0" -replace '\.', ','
$utf8 = New-Object System.Text.UTF8Encoding $false

[IO.File]::WriteAllText((Join-Path $out 'setup_version.h'), "#define WIZ8WIDE_VERSION L`"$version`"`r`n", $utf8)
$manifest = Join-Path $out 'setup.manifest'
$template = [IO.File]::ReadAllText((Join-Path $PSScriptRoot 'setup.manifest'))
[IO.File]::WriteAllText($manifest, $template.Replace('@VERSION@', "$version.0"), $utf8)

$rc = Join-Path $out 'setup.rc'
@"
1 24 "$($manifest -replace '\\','/')"
1 VERSIONINFO
FILEVERSION $numbers
PRODUCTVERSION $numbers
BEGIN
  BLOCK "StringFileInfo"
  BEGIN
    BLOCK "040904B0"
    BEGIN
      VALUE "FileDescription", "Wizardry 8 Widescreen installer"
      VALUE "FileVersion", "$version"
      VALUE "ProductName", "Wizardry 8 Widescreen"
      VALUE "ProductVersion", "$version"
    END
  END
  BLOCK "VarFileInfo"
  BEGIN
    VALUE "Translation", 0x409, 1200
  END
END
"@ | Set-Content -Encoding ascii $rc
$res = Join-Path $out 'setup_res.o'
& i686-w64-mingw32-windres $rc -O coff -o $res
if ($LASTEXITCODE) { throw 'windres failed' }
& i686-w64-mingw32-g++ -std=c++17 -O2 -municode -mwindows -static -s -I $out `
    (Join-Path $PSScriptRoot 'setup.cpp') $res -o (Join-Path $out 'Wiz8WideSetup.exe') `
    -lbcrypt -lcomctl32 -lshell32 -lole32
if ($LASTEXITCODE) { throw 'compile failed' }
Get-Item (Join-Path $out 'Wiz8WideSetup.exe')
