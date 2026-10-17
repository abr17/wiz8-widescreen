# Start the original Wiz8.exe (games\work) with the hybrid: version.dll + wiz8hy.dll.
#   powershell -File scripts\hybrid\try_hybrid.ps1 [-Save "Before Bayjin"] [-ViewDistance 2.0] [-Off]
# Loads a save with the /LOAD switch (Quick 1.SAV = the chosen save), waits and prints logs.
# -Off: disable the hybrid in wiz8ws.ini (original + regular patch).
param([string]$Save = 'Before Bayjin', [string]$ViewDistance = '2.0', [int]$Wait = 30, [switch]$Off,
      [switch]$NoLaunch)
$ErrorActionPreference = 'Stop'
$root = Resolve-Path (Join-Path $PSScriptRoot '..\..')
$work = Join-Path $root 'games\work'

function Set-Ini([string]$path, [string]$section, [string]$key, [string]$value) {
    $lines = @(); if (Test-Path $path) { $lines = Get-Content $path }
    $out = New-Object System.Collections.Generic.List[string]
    $in = $false; $done = $false
    foreach ($l in $lines) {
        if ($l -match '^\s*\[(.+)\]\s*$') {
            if ($in -and -not $done) { $out.Add("$key=$value"); $done = $true }
            $in = ($Matches[1] -eq $section)
        } elseif ($in -and $l -match "^\s*$key\s*=") { $out.Add("$key=$value"); $done = $true; continue }
        $out.Add($l)
    }
    if (-not $done) { if (-not $in) { $out.Add("[$section]") }; $out.Add("$key=$value") }
    Set-Content -Path $path -Value $out -Encoding ASCII
}

Get-Process Wiz8, Wiz8Runtime -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep 2
Set-Ini (Join-Path $work 'wiz8ws.ini') 'Hybrid' 'Enabled' $(if ($Off) { '0' } else { '1' })
Set-Ini (Join-Path $work 'wiz8ws.ini') 'Debug' 'DiffHarness' '0'
Set-Ini (Join-Path $work 'wiz8wide.ini') 'Debug' 'DiffHarness' '0'
Set-Ini (Join-Path $work 'wiz8wide.ini') 'Display' 'ViewDistance' $ViewDistance
Copy-Item (Join-Path $root 'build\version.dll') $work -Force
if (-not $Off) {
    Copy-Item (Join-Path $root 'build\hybrid\wiz8hy.dll'), (Join-Path $root 'build\hybrid\wiz8hy_hooks.txt') $work -Force
}
if ($NoLaunch) { return }

$saves = Join-Path $work 'Saves'
Copy-Item (Join-Path $saves "$Save.SAV") (Join-Path $saves 'Quick 1.SAV') -Force
(Get-Item (Join-Path $saves 'Quick 1.SAV')).LastWriteTime = Get-Date
Get-Process Wiz8, Wiz8Runtime -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep 1
Remove-Item (Join-Path $work 'wiz8hy.log') -ErrorAction SilentlyContinue
$p = Start-Process -FilePath (Join-Path $work 'Wiz8.exe') -ArgumentList '/LOAD' -WorkingDirectory $work -PassThru
Start-Sleep $Wait
"alive: $(-not $p.HasExited)"
if (Test-Path (Join-Path $work 'wiz8hy.log')) { Get-Content (Join-Path $work 'wiz8hy.log') }
Get-Content (Join-Path $work 'wiz8ws.log') | Select-Object -Last 3
