# Run all specs in batches (the whole plan would not fit in the game's memory):
# each batch is one run.ps1 call, then results go to build\w8diff\runs\<batch>\.
#   powershell -File scripts\w8diff\run_all.ps1 [-Batch 4] [-Only "magic_a,magic_b"]
# A spec can require its own save with a line SAVE = 'Name' (for example,
# a level with live monsters); batches are made of specs that share a save.
param([int]$Batch = 4, [string]$Only = '', [string]$Save = 'Before Bayjin')
$ErrorActionPreference = 'Continue'
$root = Resolve-Path (Join-Path $PSScriptRoot '..\..')
$specDir = Join-Path $PSScriptRoot 'specs'
$specs = if ($Only) { $Only -split ',' } else {
    Get-ChildItem $specDir -Filter '*.py' | Where-Object { $_.Name -notlike '_*' -and $_.Name -ne 'smoke.py' } |
        ForEach-Object { $_.BaseName } }
$bySave = [ordered]@{}
foreach ($s in $specs) {
    $sv = $Save
    $m = Select-String -Path (Join-Path $specDir "$s.py") -Pattern "^SAVE\s*=\s*'([^']+)'" | Select-Object -First 1
    if ($m) { $sv = $m.Matches[0].Groups[1].Value }
    if (-not $bySave.Contains($sv)) { $bySave[$sv] = New-Object System.Collections.Generic.List[string] }
    $bySave[$sv].Add($s)
}
$runs = Join-Path $root 'build\w8diff\runs'
New-Item -ItemType Directory -Force $runs | Out-Null
foreach ($sv in $bySave.Keys) {
    $list = @($bySave[$sv])
    for ($i = 0; $i -lt $list.Count; $i += $Batch) {
        $part = $list[$i..([math]::Min($i + $Batch, $list.Count) - 1)]
        $group = $part -join ','
        $name = $part[0] + "+$($part.Count)"
        "=== $group ($sv)"
        powershell -NoProfile -File (Join-Path $PSScriptRoot 'run.ps1') -Specs $group -Save $sv -TimeoutSec 3600 2>&1 | Select-Object -Last 3
        $dir = Join-Path $runs $name
        New-Item -ItemType Directory -Force $dir | Out-Null
        foreach ($f in 'report.txt', 'report.json', 'meta.json') { Copy-Item (Join-Path $root "build\w8diff\$f") $dir -Force -ErrorAction SilentlyContinue }
        foreach ($p in 'retail', 'port') { Copy-Item (Join-Path $root "games\work\w8diff_out_$p.txt") $dir -Force -ErrorAction SilentlyContinue
                                          Copy-Item (Join-Path $root "games\work\w8diff_plan_$p.txt") $dir -Force -ErrorAction SilentlyContinue }
        Set-Content (Join-Path $dir 'save.txt') $sv -Encoding UTF8
    }
}
"all batches done"
