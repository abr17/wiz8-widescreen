# Hybrid screenshots without mouse or keyboard (works even with the screen locked):
# the game (original + wiz8hy.dll) loads a save, then through the w8diff test stand (it lives inside
# the port's transplanted RenderFrame) the original's SetPendingScreenState(screen) is called,
# and the game saves the frame itself (wiz8shot.req).
#   powershell -File scripts\hybrid\hy_screens.ps1 [-Save "444"] [-Screens "6,8,10,11"]
param([string]$Save = '444', [string]$Screens = '6,8,10,11', [string]$Tag = 'hy')
$ErrorActionPreference = 'Stop'
$root = Resolve-Path (Join-Path $PSScriptRoot '..\..')
$work = Join-Path $root 'games\work'
. (Join-Path $root 'scripts\play\play.ps1')
$script:GameDir = $work; $script:Exe = 'Wiz8'

powershell -NoProfile -File (Join-Path $PSScriptRoot 'try_hybrid.ps1') -Save $Save -Wait 35 | Select-Object -Last 1
# enable the port's test stand inside wiz8hy.dll (it reads wiz8wide.ini on the first frame,
# so set it before launch; try_hybrid turns it off, so we enable it and restart)
$ini = Join-Path $work 'wiz8wide.ini'
(Get-Content $ini) -replace '^DiffHarness=.*', 'DiffHarness=1' | Set-Content $ini -Encoding ASCII
Get-Process Wiz8 -ErrorAction SilentlyContinue | Stop-Process -Force; Start-Sleep 2
$p = Start-Process -FilePath (Join-Path $work 'Wiz8.exe') -ArgumentList '/LOAD' -WorkingDirectory $work -PassThru
Start-Sleep 35
$names = @{ 6 = 'camp'; 7 = 'main'; 8 = 'automap'; 10 = 'options'; 11 = 'journal' }
$shots = @()
$shots += GShot "$Tag-main"
foreach ($s in ($Screens -split ',')) {
    $id = [int]$s
    $plan = "W8DIFF 1`ncase screen$id`nfn c 55EC50`narg $('{0:X}' -f $id)`nend`n"
    [IO.File]::WriteAllText((Join-Path $work 'w8diff_plan_port.txt'), $plan, (New-Object Text.ASCIIEncoding))
    Remove-Item (Join-Path $work 'w8diff_done_port.txt') -ErrorAction SilentlyContinue
    New-Item -ItemType File -Force (Join-Path $work 'w8diff_port.req') | Out-Null
    for ($i = 0; $i -lt 20 -and -not (Test-Path (Join-Path $work 'w8diff_done_port.txt')); $i++) { Start-Sleep -Milliseconds 500 }
    Start-Sleep 4
    $n = if ($names.ContainsKey($id)) { $names[$id] } else { "s$id" }
    $shots += GShot "$Tag-$n"
    "alive: $(-not $p.HasExited)"
}
(Get-Content $ini) -replace '^DiffHarness=.*', 'DiffHarness=0' | Set-Content $ini -Encoding ASCII
$shots
