# Builds wiz8ws (version.dll) and, optionally, installs it into the working copy of the game.
#   .\build.ps1            — build
#   .\build.ps1 -Install   — build and copy into games\work
#   .\build.ps1 -Uninstall — remove the patch DLLs (version.dll, wiz8hy.dll + hooks) and logs from games\work
param([switch]$Install, [switch]$Uninstall, [string]$Config = 'Release')
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
. "$root\Tools\env.ps1"
$work = "$root\games\work"

if ($Uninstall) {
    Remove-Item "$work\version.dll", "$work\wiz8hy.dll", "$work\wiz8hy_hooks.txt",
        "$work\wiz8ws.log", "$work\wiz8hy.log", "$work\wiz8wide.log" -ErrorAction SilentlyContinue
    Write-Host "Removed the patch DLLs and logs from $work (inis and wide art kept)"
    return
}

$build = "$root\build"
cmake -S $root -B $build -G "MinGW Makefiles" `
    -DCMAKE_TOOLCHAIN_FILE="$root\cmake\llvm-mingw-i686.cmake" `
    -DCMAKE_MAKE_PROGRAM="$root\Tools\llvm-mingw\bin\mingw32-make.exe" `
    -DCMAKE_BUILD_TYPE=$Config | Out-Null
if ($LASTEXITCODE) { throw "cmake configure failed" }
cmake --build $build -j 8
if ($LASTEXITCODE) { throw "build failed" }

$dll = "$build\version.dll"
Write-Host "Built: $dll ($((Get-Item $dll).Length) bytes)"

if ($Install) {
    Copy-Item $dll $work -Force
    if (-not (Test-Path "$work\wiz8ws.ini")) { Copy-Item "$root\dist\wiz8ws.ini" $work }
    Write-Host "Installed to $work"
}
