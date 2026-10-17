# Comparison test stand run: the same call plan in the original Wiz8.exe and in
# Wiz8Runtime.exe (both in games\work, the same save), then the comparison.
#   powershell -File scripts\w8diff\run.ps1 -Specs smoke [-Save "Before Bayjin"] [-Scale 1] [-Only retail|port]
#   -NoGen   do not regenerate plans (use the existing ones in games\work)
#   -Corpus  dump the save's characters into build\w8diff\corpus (retail only)
# Touches nothing outside C:\dev\wiz8-ws. On the first run Quick 1.SAV in games\work
# is copied to build\w8diff\saves_backup.
param(
    [string]$Specs = '',
    [string]$Save = 'Before Bayjin',
    [double]$Scale = 1.0,
    [ValidateSet('both', 'retail', 'port')][string]$Only = 'both',
    [int]$TimeoutSec = 900,
    [switch]$NoGen,
    [switch]$Corpus
)
$ErrorActionPreference = 'Stop'
$root = Resolve-Path (Join-Path $PSScriptRoot '..\..')
$work = Join-Path $root 'games\work'
$state = Join-Path $root 'build\w8diff'
New-Item -ItemType Directory -Force $state | Out-Null

function Set-IniValue([string]$path, [string]$section, [string]$key, [string]$value) {
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

# --- install fresh builds into games\work ---
Copy-Item (Join-Path $root 'build\vc2022\Wiz8Runtime.exe') $work -Force
Copy-Item (Join-Path $root 'build\w8diff\w8diff.dll') $work -Force
Copy-Item (Join-Path $root 'build\version.dll') $work -Force
Set-IniValue (Join-Path $work 'wiz8ws.ini') 'Debug' 'DiffHarness' '1'
Set-IniValue (Join-Path $work 'wiz8ws.ini') 'Hybrid' 'Enabled' '0'   # compare against the pure original
Set-IniValue (Join-Path $work 'wiz8wide.ini') 'Debug' 'DiffHarness' '1'

# --- save: Quick 1.SAV = the chosen save, newest (loaded by the /LOAD switch) ---
$saves = Join-Path $work 'Saves'
$backup = Join-Path $state 'saves_backup'
if (-not (Test-Path $backup)) {
    New-Item -ItemType Directory -Force $backup | Out-Null
    Get-ChildItem $saves -Filter 'Quick *.SAV' | Copy-Item -Destination $backup
}
$src = Join-Path $saves "$Save.SAV"
if (-not (Test-Path $src)) { throw "save not found: $src" }
Copy-Item $src (Join-Path $saves 'Quick 1.SAV') -Force
(Get-Item (Join-Path $saves 'Quick 1.SAV')).LastWriteTime = Get-Date

# --- plan ---
$env:PYTHONIOENCODING = 'utf-8'
if (-not $NoGen) {
    $specArg = if ($Corpus) { '_corpus_dump' } else { $Specs }
    & python -I (Join-Path $PSScriptRoot 'gen_plan.py') --specs $specArg --scale $Scale
    if ($LASTEXITCODE -ne 0) { throw 'gen_plan failed' }
}

# One exe. If a case did not return (a hang: output has not grown for $HangSec s,
# last line "S <id>") or the game crashed mid-case, that case is marked
# HANG/CRASH, the game is restarted with plan "resume <N>" and continues with the next one.
$HangSec = 45
function Run-One([string]$proc, [string]$exe) {
    foreach ($k in 'out_', 'done_') { Remove-Item (Join-Path $work "w8diff_$k$proc.txt") -ErrorAction SilentlyContinue }
    $planPath = Join-Path $work "w8diff_plan_$proc.txt"
    $fullPlan = Join-Path $state "plan_full_$proc.txt"
    Copy-Item $planPath $fullPlan -Force
    $outPath = Join-Path $work "w8diff_out_$proc.txt"
    $done = Join-Path $work "w8diff_done_$proc.txt"
    $name = [IO.Path]::GetFileNameWithoutExtension($exe)
    $sw = [Diagnostics.Stopwatch]::StartNew()
    $restarts = 0
    try {
        while ($true) {
            Get-Process $name -ErrorAction SilentlyContinue | Stop-Process -Force
            Start-Sleep 1
            $p = Start-Process -FilePath (Join-Path $work $exe) -ArgumentList '/LOAD' -WorkingDirectory $work -PassThru
            New-Item -ItemType File -Force (Join-Path $work "w8diff_$proc.req") | Out-Null
            $lastSize = -1; $still = [Diagnostics.Stopwatch]::StartNew(); $problem = $null
            while (-not (Test-Path $done)) {
                Start-Sleep 2
                $size = if (Test-Path $outPath) { (Get-Item $outPath).Length } else { 0 }
                if ($size -ne $lastSize) { $lastSize = $size; $still.Restart() }
                if ($p.HasExited) { $problem = 'CRASH'; break }
                if ($sw.Elapsed.TotalSeconds -gt $TimeoutSec) { Write-Warning "$proc timeout"; break }
                if ($still.Elapsed.TotalSeconds -gt $HangSec -and (Test-Path $outPath)) {
                    $tail = Get-Content $outPath -Tail 1
                    if ($tail -like 'S *') { $problem = 'HANG' }
                    elseif ($still.Elapsed.TotalSeconds -gt 240) { $problem = 'STALL' }
                    if ($problem) { break }
                }
            }
            if (-not $p.HasExited) { Stop-Process -Id $p.Id -Force; Start-Sleep 2 }
            if (-not $problem -or $restarts -ge 40 -or -not (Test-Path $outPath)) { break }
            # which case did not return and how many were started in total
            $lines = Get-Content $outPath
            $started = @($lines | Where-Object { $_ -like 'S *' })
            $last = $lines | Select-Object -Last 1
            if ($last -like 'S *') {
                $id = $last.Substring(2)
                Add-Content $outPath "R $id $problem a=- eax=00000000 edx=00000000 fp=- fd=0"
                Write-Warning "${proc}: case $id -> $problem, restarting after it"
            } else {
                Write-Warning "${proc}: $problem without an open case, restarting"
            }
            $restarts++
            $plan = [IO.File]::ReadAllText($fullPlan)
            $nl = $plan.IndexOf("`n")
            $resumed = $plan.Substring(0, $nl + 1) + ('resume {0:X}' -f $started.Count) + "`n" + $plan.Substring($nl + 1)
            [IO.File]::WriteAllText($planPath, $resumed, (New-Object Text.ASCIIEncoding))
        }
    } finally {
        Copy-Item $fullPlan $planPath -Force
    }
    $result = if (Test-Path $done) { (Get-Content $done -Raw).Trim() } else { 'NO RESULT' }
    "{0}: {1} ({2:N0} s, restarts {3})" -f $proc, $result, $sw.Elapsed.TotalSeconds, $restarts
    Start-Sleep 2
}

try {
    if ($Only -in 'both', 'retail') { Run-One 'retail' 'Wiz8.exe' }
    if (-not $Corpus -and $Only -in 'both', 'port') { Run-One 'port' 'Wiz8Runtime.exe' }
} finally {
    Set-IniValue (Join-Path $work 'wiz8ws.ini') 'Debug' 'DiffHarness' '0'
    Set-IniValue (Join-Path $work 'wiz8wide.ini') 'Debug' 'DiffHarness' '0'
}

if ($Corpus) {
    & python -I (Join-Path $PSScriptRoot 'collect_corpus.py') --save $Save
} elseif ($Only -eq 'both') {
    & python -I (Join-Path $PSScriptRoot 'compare.py')
}
