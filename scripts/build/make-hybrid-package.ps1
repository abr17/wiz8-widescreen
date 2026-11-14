# Builds the hybrid package: build\package\Wiz8Widescreen\ and build\package\Wiz8Widescreen-<VERSION>.zip.
#   pwsh -File scripts\build\make-hybrid-package.ps1
#   pwsh -File scripts\build\make-hybrid-package.ps1 -Driver <path to srDD_D3D11.dll>
#   -AllowModifiedDriver: a trial package with a driver built from uncommitted changes
# First build version.dll (build.ps1), wiz8hy.dll (scripts\hybrid\build_hybrid.ps1 -Config
# scripts\hybrid\transplant_wide.json) and the render driver (drivers\srdd_d3d11, its own
# project: build.sh or build.ps1 there, the release build with embedded shaders). Package contents:
# Wiz8WideSetup.exe, files\ (what goes into the game folder; also usable for a manual install),
# README in four languages from dist\, LICENSE and THIRD-PARTY-NOTICES.txt (the licence of MinHook,
# which version.dll contains, from the submodule's own licence file).
# The render driver, files\Dll\srDD_D3D11.dll, is a dependency the package only carries: the
# built DLL is taken from -Driver, by default drivers\srdd_d3d11\out\srDD_D3D11.dll, with the
# build record its build script wrote beside it (srDD_D3D11.build.txt). It must be the driver's
# release build (not its reference build, out\ref\srDD_D3D11.dll, which the driver's tests use)
# with the shaders embedded as DXBC (a DLL without them compiles its shaders at every start with
# d3dcompiler_47.dll, which Windows 7/8 and some Wine prefixes do not have), built from the
# driver's present commit by a build that checked the driver's ABI (its build.ps1 needs
# llvm-objdump for that: Tools\llvm-mingw\bin, which Tools\env.ps1 puts on PATH and
# Tools\msvcenv.ps1 names in LLVM_OBJDUMP). The driver's own checker decides that, the same one
# its zip script asks: drivers\srdd_d3d11\tools\check_dll.py --package (Python 3).
# One package for everyone: wiz8ws.ini has [Debug] Diagnostics=0, and the installer's
# "Diagnostics mode" checkbox (or --diagnostics) turns it on (docs\loader.md).
# Finished releases are kept separately in release\ (this script does not write there).
param([string]$Driver, [switch]$AllowModifiedDriver)
$ErrorActionPreference = 'Stop'
$root = Resolve-Path (Join-Path $PSScriptRoot '..\..')
if (-not $Driver) { $Driver = Join-Path $root 'drivers\srdd_d3d11\out\srDD_D3D11.dll' }
$assets = Join-Path $root 'assets'
# the last hybrid build failed (a compile, link or binding guard error) or has not finished:
# build\hybrid holds an older pair than the sources
$guardFailed = Join-Path $root 'build\hybrid\GUARD_FAILED'
if (Test-Path -LiteralPath $guardFailed) {
    throw "build\hybrid\GUARD_FAILED exists: the last wiz8hy.dll build failed or has not finished (see that file and docs\hybrid.md, 'How wiz8hy.dll is built'); fix it and rebuild"
}
$out = Join-Path $root 'build\package\Wiz8Widescreen'
$files = Join-Path $out 'files'
$version = (Get-Content -LiteralPath "$root\VERSION" -TotalCount 1).Trim()
$zip = Join-Path $root "build\package\Wiz8Widescreen-$version.zip"
# The folder and the archive of an earlier run go first: a run that stops leaves no older package.
if (Test-Path -LiteralPath $out) { Remove-Item -LiteralPath $out -Recurse -Force }
if (Test-Path -LiteralPath $zip) { Remove-Item -LiteralPath $zip -Force }
New-Item -ItemType Directory -Force -Path $files | Out-Null

function Put([string]$src, [string]$rel) {
    if (-not (Test-Path -LiteralPath $src)) { throw "missing file: $src" }
    $dst = Join-Path $files $rel
    New-Item -ItemType Directory -Force -Path (Split-Path $dst -Parent) | Out-Null
    Copy-Item -LiteralPath $src -Destination $dst
}

& pwsh -NoProfile -File "$root\tools_src\setup\build.ps1" | Out-Null
if ($LASTEXITCODE) { throw 'installer build failed' }

# the 83 Bink forwarders of version.dll, each one "binkw32_wiz8wide.<name>" (forwarders.ps1)
. (Join-Path $PSScriptRoot 'forwarders.ps1')
Assert-BinkForwarders "$root\build\version.dll"

Put "$root\build\version.dll" 'version.dll'
# dll and hook list always as a pair (a mismatch = crash at startup)
Put "$root\build\hybrid\wiz8hy.dll" 'wiz8hy.dll'
Put "$root\build\hybrid\wiz8hy_hooks.txt" 'wiz8hy_hooks.txt'
Put "$root\dist\wiz8ws.ini" 'wiz8ws.ini'
Put "$root\dist\wiz8wide.ini" 'wiz8wide.ini'
# the installer's diagnostics checkbox writes this line; it must be there and off
if ([IO.File]::ReadAllText("$files\wiz8ws.ini") -notmatch '(?m)^Diagnostics=0\r?$') { throw 'dist\wiz8ws.ini has no "Diagnostics=0" line' }
# the render driver (see the head of this file). What a package demands of the DLL is written
# once, in the driver's checker: a 32-bit DLL with the driver's exports and no import outside its
# lists, the release build, of the version in the driver's src\version.h, with exactly the
# release build's shaders embedded, and with a build record that belongs to this very file, says
# that the build checked the driver's ABI and names the driver's present commit (no uncommitted
# changes, unless -AllowModifiedDriver).
if (-not (Test-Path -LiteralPath $Driver)) { throw "the render driver is missing: $Driver (build drivers\srdd_d3d11 first, or pass -Driver)" }
. (Join-Path $root 'drivers\srdd_d3d11\tools\find_python.ps1')
$python = @(Find-Python)
$pyArgs = @($python | Select-Object -Skip 1)
# The checker asks git for the commit the driver's folder is at now: git on PATH, or the one in
# the workspace's Tools folder.
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    $gitDir = Join-Path $root 'Tools\git\cmd'
    if (Test-Path -LiteralPath (Join-Path $gitDir 'git.exe')) { $env:PATH = "$gitDir;$env:PATH" }
}
$checkArgs = @((Resolve-Path -LiteralPath $Driver).Path, '--package')
if ($AllowModifiedDriver) { $checkArgs += '--allow-modified' }
$driverCheck = & $python[0] @pyArgs -I "$root\drivers\srdd_d3d11\tools\check_dll.py" @checkArgs
if ($LASTEXITCODE) { throw "the render driver $Driver is refused (the reason is above): build its release build from a commit with drivers\srdd_d3d11\build.ps1 and make the package again" }
Put $Driver 'Dll\srDD_D3D11.dll'
# assets\ (not in git): wide art and FALCON.STI (the exit advertisement screen, which is
# missing from the Russian translation data). dgVoodoo 2 was part of the package up to 1.0.2
# (the game's DirectX 7 driver needed it on modern Windows); an assets\ filled before 1.0.3 may
# still hold its three files, which are left out.
$dgVoodoo = 'DDraw.dll', 'D3DImm.dll', 'dgVoodoo.conf'
# The art of the experimental features (docs\experimental.md) is not in the release zips before
# 1.0.2, so an assets\ filled from an older zip lacks it; without it the game silently falls back.
foreach ($n in 'MENU_ANIM.AVI', 'OPTIONS_BASE_EXP.STI', 'OPTIONS_BUTTONS_EXP_EN.STI', 'OPTIONS_BUTTONS_EXP_RU.STI',
               'OPTIONS_COMPUTER_EXP.STI', 'OPTIONS_COMPUTER_EXP169.STI') {
    if (-not (Test-Path -LiteralPath "$assets\Data\WIDE\$n")) { throw "assets\Data\WIDE\$n is missing (release zips before 1.0.2 do not have it)" }
}
$count = 0
foreach ($f in Get-ChildItem -LiteralPath $assets -Recurse -File) {
    $rel = $f.FullName.Substring($assets.Length + 1)
    if ($dgVoodoo -contains $rel) { "left out: assets\$rel (dgVoodoo is not part of the package since 1.0.3)"; continue }
    Put $f.FullName $rel; $count++
}
Copy-Item -LiteralPath "$root\build\setup\Wiz8WideSetup.exe" -Destination $out
foreach ($f in Get-ChildItem -LiteralPath "$root\dist" -Filter 'README_*.txt') {
    Copy-Item -LiteralPath $f.FullName -Destination $out
}
# The licence of the patch, and the notice of the third-party code in its binaries: MinHook is
# linked into version.dll (CMakeLists.txt, third_party\minhook), and its licence asks that the
# text go with binary copies. The text is the submodule's own licence file, read now; nothing of
# it is written here.
Copy-Item -LiteralPath "$root\LICENSE" -Destination $out
$minhookLicence = 'LICENSE.txt', 'LICENSE', 'LICENSE.md', 'COPYING' | ForEach-Object { Join-Path $root "third_party\minhook\$_" } |
    Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1
if (-not $minhookLicence) {
    throw 'third_party\minhook has no licence file (LICENSE.txt, LICENSE, LICENSE.md or COPYING): check the submodule out (git submodule update --init third_party/minhook); the package is not made without its notice'
}
$notices = "Third-party notices for Wizardry 8 Widescreen.`r`n" +
           "version.dll contains MinHook (third_party/minhook); the text below is that project's licence file, unchanged.`r`n`r`n" +
           [IO.File]::ReadAllText($minhookLicence)
[IO.File]::WriteAllText((Join-Path $out 'THIRD-PARTY-NOTICES.txt'), $notices, (New-Object Text.UTF8Encoding $false))

Compress-Archive -Path "$out\*" -DestinationPath $zip
$size = [math]::Round((Get-Item -LiteralPath $zip).Length / 1MB, 1)
"$driverCheck"
"package: $out ($count files from assets, LICENSE and THIRD-PARTY-NOTICES.txt beside the READMEs), archive: $zip ($size MB)"
