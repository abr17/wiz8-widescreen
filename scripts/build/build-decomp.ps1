# Builds Wiz8Runtime.exe from the decompilation (decomp) with the MSVC 2022 x86 compiler.
#   powershell -File C:\dev\wiz8-ws\scripts\build\build-decomp.ps1            # configure + build
#   powershell -File C:\dev\wiz8-ws\scripts\build\build-decomp.ps1 -Clean     # from scratch
#   ... -Target wiz8_recovered_objects -KeepGoing                       # debugging errors
# Log: build\vc2022\build.log. Touches nothing outside C:\dev\wiz8-ws.
param(
    [switch]$Clean,
    [switch]$KeepGoing,
    [string]$Target = 'WIZ8_RUNTIME'
)
$ErrorActionPreference = 'Stop'
$Root  = 'C:\dev\wiz8-ws'
$Src   = "$Root\decomp"
$Bin   = "$Root\build\vc2022"
$Zlib  = "$Root\Tools\zlib\zlib-1.0.4"

. "$Root\Tools\msvcenv.ps1"   # cl/link/lib/nmake/rc + CMake on PATH for this session only
# From here on exit codes are checked explicitly: in Windows PowerShell 5.1 the Stop mode
# would turn any stderr line (e.g. D9035 from cl) into a fatal error.
$ErrorActionPreference = 'Continue'

if ($Clean -and (Test-Path $Bin)) { Remove-Item -Recurse -Force $Bin }

# CMAKE_BUILD_TYPE empty and CMAKE_CXX_FLAGS without /EHsc: the project sets the flags itself
# (cmake/CompileSettings.cmake + cmake/ModernMsvc.cmake), as in the original VC6 build.
& cmake -S $Src -B $Bin -G 'NMake Makefiles' `
    '-DCMAKE_BUILD_TYPE=' `
    '-DCMAKE_C_FLAGS=/DWIN32 /D_WINDOWS' `
    '-DCMAKE_CXX_FLAGS=/DWIN32 /D_WINDOWS' `
    "-DZLIB_SOURCE=$($Zlib -replace '\\','/')"
if ($LASTEXITCODE -ne 0) { throw "configure failed ($LASTEXITCODE)" }

$extra = @()
if ($KeepGoing) { $extra = @('--', '/K') }
& cmake --build $Bin --target $Target @extra 2>&1 | Tee-Object -FilePath "$Bin\build.log" |
    Where-Object { $_ -notmatch "D9035 : option 'Zc:forScope-' has been deprecated" }
$code = $LASTEXITCODE
if ($code -ne 0) { throw "build failed ($code), see $Bin\build.log" }

$exe = Join-Path $Bin 'Wiz8Runtime.exe'
if ($Target -eq 'WIZ8_RUNTIME' -and (Test-Path $exe)) {
    $item = Get-Item $exe
    "OK: $($item.FullName)  $($item.Length) bytes"
}
