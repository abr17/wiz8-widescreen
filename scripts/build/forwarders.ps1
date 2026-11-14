# forwarders.ps1 - the check of the Bink forwarders in a built version.dll, as a function for the
# scripts that need it (the root build.ps1 runs it after the build, scripts\build\make-hybrid-package.ps1
# before it packs the DLL).
# Dot-source it, then:
#
#   Assert-BinkForwarders <path to version.dll>
#
# version.def lists the 83 Bink functions as forwarders (the binkw32.dll copy under Wine,
# src\loader_route.h). Each must read "binkw32_wiz8wide.<name>": an older lld (Ubuntu's LLVM 18)
# writes "_binkw32_wiz8wide." there, Wine then finds no such DLL and the game dies at its first
# video. The function throws when the DLL does not hold exactly 83 forwarders of that form.
function Assert-BinkForwarders([string]$Dll) {
    $readobj = Join-Path $PSScriptRoot '..\..\Tools\llvm-mingw\bin\llvm-readobj.exe'
    $forwarders = @(& $readobj --coff-exports $Dll |
        Select-String '^\s*ForwardedTo:\s*(\S+)' | ForEach-Object { $_.Matches[0].Groups[1].Value })
    if ($LASTEXITCODE) { throw "llvm-readobj failed on $Dll" }
    $wrong = @($forwarders | Where-Object { -not $_.StartsWith('binkw32_wiz8wide.') })
    if ($forwarders.Count -ne 83 -or $wrong.Count) {
        throw "$Dll has $($forwarders.Count) Bink forwarders (83 expected), $($wrong.Count) not starting with binkw32_wiz8wide. ($($wrong | Select-Object -First 1)): rebuild it with build.ps1"
    }
}
