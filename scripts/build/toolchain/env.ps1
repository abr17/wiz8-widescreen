# Adds the project's portable tools to the current PowerShell session only.
# Usage:  . C:\dev\wiz8-ws\Tools\env.ps1
# The system PATH and registry are not changed.
$T = $PSScriptRoot
$env:JAVA_HOME = "$T\jdk21"
$env:GHIDRA_INSTALL_DIR = "$T\ghidra"
$env:REA_ANALYSIS_PROVIDER = "ghidra"
$env:REA_GHIDRA_STARTUP_TIMEOUT_MS = "1800000"
$env:PATH = @(
    "$T\git\cmd",
    "$T\node",
    "$T\jdk21\bin",
    "$T\cmake\bin",
    "$T\llvm-mingw\bin",
    $env:PATH
) -join ';'
