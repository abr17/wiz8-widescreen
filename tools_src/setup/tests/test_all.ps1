# Full installer scenario run on a fresh copy of games\reference (read-only flags cleared, like a
# real GOG/Steam folder): update from the previous release, the game running, rollback from a
# faked newer version, a newer manifest format, a copy failing halfway, a manual install, an
# empty manifest, uninstall back to the original byte for byte, the diagnostics checkbox and
# --diagnostics / --no-diagnostics (fresh, reinstall, update, failure). Prints PASS/FAIL per check.
#   pwsh -File tools_src\setup\tests\test_all.ps1 [-PreviousZip release\Wiz8Widescreen-1.0.0.zip]
# First build the package (scripts\build\make-hybrid-package.ps1). The scripts expect the package
# version to be newer than the previous zip; fake_newer.ps1 fakes the next version (last number + 1).
# Uses build\tmp\installer-test (deleted and re-created) and starts the game once (S2).
param([string]$PreviousZip = 'C:\dev\wiz8-ws\release\Wiz8Widescreen-1.0.0.zip')
$ErrorActionPreference = 'Continue'
# versions as regex text: this package (VERSION), the previous release (from the zip name) and
# the faked newer one
$version = (Get-Content 'C:\dev\wiz8-ws\VERSION' -TotalCount 1).Trim()
$parts = $version.Split('.'); $parts[-1] = [string]([int]$parts[-1] + 1); $newer = $parts -join '.'
$V = [regex]::Escape($version)
$N = [regex]::Escape($newer)
$P = [regex]::Escape(([regex]::Match((Split-Path $PreviousZip -Leaf), '\d+\.\d+\.\d+')).Value)
$sp = $PSScriptRoot
$t = 'C:\dev\wiz8-ws\build\tmp\installer-test'; $g = "$t\game"
$new = 'C:\dev\wiz8-ws\build\package\Wiz8Widescreen\Wiz8WideSetup.exe'
$files = 'C:\dev\wiz8-ws\build\package\Wiz8Widescreen\files'
$script:fails = 0; $script:passes = 0
function Check([string]$name, [bool]$ok, [string]$detail = '') {
    if ($ok) { $script:passes++; "PASS $name" } else { $script:fails++; "FAIL $name $detail" }
}
function Gui([string]$click = 'none', [string]$answer = 'yes', [string]$folder = $g, [string]$diag = 'keep') {
    (powershell -NoProfile -ExecutionPolicy Bypass -File "$sp\gui_setup.ps1" -Exe $new -Folder $folder -Click $click -Answer $answer -Diag $diag) -join "`n"
}
function Cmd([string]$exe, [string]$action, [string[]]$more = @()) { (& "$sp\run_setup.ps1" -Exe $exe -SetupArgs (@($action, "`"$g`"") + $more)) -join "`n" }
function IniValue([string]$file, [string]$section, [string]$key) {
    $in = $false
    foreach ($l in Get-Content -LiteralPath $file -ErrorAction SilentlyContinue) {
        if ($l -match '^\[(.+)\]') { $in = $Matches[1] -eq $section; continue }
        if ($in -and $l -match "^$key=(.*)$") { return $Matches[1] }
    }
    $null
}
function Installed { (& "$sp\check_install.ps1" -Game $g -Files $files) -join "`n" }
function Uninstalled { (& "$sp\check_install.ps1" -Game $g -Uninstalled) -join "`n" }
function FolderSnap { (Get-ChildItem $g -Recurse -File | Where-Object { $_.Name -notmatch '\.log$|^3DVideo\.CFG$|^Wiz8\.CFG$' } |
    ForEach-Object { $_.FullName + '|' + (Get-FileHash $_.FullName).Hash }) -join "`n" }
function SetIni([string]$file, [string]$section, [string]$key, [string]$value) {
    $out = @(); $in = $false
    foreach ($l in Get-Content -LiteralPath $file) {
        if ($l -match '^\[(.+)\]') { $in = $Matches[1] -eq $section }
        elseif ($in -and $l -match "^$key=") { $l = "$key=$value" }
        $out += $l
    }
    Set-Content -LiteralPath $file -Value $out
}

"== S0 fresh copy"
if (Test-Path $t) { [IO.Directory]::Delete($t, $true) }
New-Item -ItemType Directory -Force $t | Out-Null
robocopy C:\dev\wiz8-ws\games\reference $g /E /NFL /NDL /NJH /NJS /NP /MT:8 | Out-Null
Get-ChildItem $g -Recurse -File | ForEach-Object { $_.Attributes = $_.Attributes -band -bnot [IO.FileAttributes]::ReadOnly }
Expand-Archive -LiteralPath $PreviousZip -DestinationPath "$t\pkg100" -Force
$old = "$t\pkg100\Wiz8WideSetup.exe"

"== S1 update from the previous release keeps wiz8wide.ini, Enabled=0 and Wiz8Logs (folder typed with a trailing backslash)"
$r = Cmd $old '--install'
SetIni "$g\wiz8wide.ini" 'Display' 'MaxFps' '97'
SetIni "$g\wiz8ws.ini" 'General' 'Enabled' '0'
New-Item -ItemType Directory -Force "$g\Wiz8Logs\2026-01-01_10-00-00" | Out-Null
Set-Content "$g\Wiz8Logs\2026-01-01_10-00-00\wiz8ws.log" 'old session'
Set-Content "$g\wiz8ws.log" 'last session'   # the game closed, then the player updates
$r = Gui 'install' 'yes' "$g\"
Check 'S1 Wiz8Logs kept' (Test-Path "$g\Wiz8Logs\2026-01-01_10-00-00\wiz8ws.log")
$moved = @(Get-ChildItem "$g\Wiz8Logs" -Recurse -Filter wiz8ws.log | Where-Object { (Get-Content $_.FullName -Raw).Trim() -eq 'last session' })
Check 'S1 last session''s log moved into Wiz8Logs' ($moved.Count -eq 1 -and -not (Test-Path "$g\wiz8ws.log"))
[IO.Directory]::Delete("$g\Wiz8Logs", $true)
Check 'S1 button Update' ($r -match "BUTTON: Update $P → $V")
Check 'S1 done text' ($r -match "updated from $P to $V")
$c = Installed
Check 'S1 files' ($c -match 'installed check: 1 problem' -and $c -match 'DIFFERS FROM PACKAGE wiz8ws\.ini') $c
Check 'S1 MaxFps kept' ((IniValue "$g\wiz8wide.ini" 'Display' 'MaxFps') -eq '97')
Check 'S1 Enabled=0 kept' ((IniValue "$g\wiz8ws.ini" 'General' 'Enabled') -eq '0')
Check 'S1 Hybrid Enabled=1' ((IniValue "$g\wiz8ws.ini" 'Hybrid' 'Enabled') -eq '1')
Check 'S1 no .keep' (-not (Test-Path "$g\wiz8wide.ini.keep"))

"== S2 game running: reinstall and uninstall refused"
SetIni "$g\wiz8ws.ini" 'General' 'Enabled' '1'
Push-Location C:\dev\wiz8-ws
. C:\dev\wiz8-ws\scripts\play\hybrid_session.ps1 -GameDir $g
Start-Wiz8 | Out-Null; Start-Sleep 10
$before = FolderSnap
$r1 = Gui 'install'; $r2 = Gui 'uninstall'
Check 'S2 reinstall refused' ($r1 -match 'is in use')
Check 'S2 uninstall refused' ($r2 -match 'is in use')
Check 'S2 folder unchanged' ($before -eq (FolderSnap))
$log = Get-Content "$g\wiz8ws.log" -TotalCount 1
Check 'S2 log has version' ($log -match "Wizardry 8 Widescreen $V") $log
Quit-Wiz8 | Out-Null; Pop-Location; Start-Sleep 2

"== S3 rollback from a faked $newer"
& "$sp\fake_newer.ps1" -Game $g -Version $newer | Out-Null
$r = Gui 'install' 'no'
Check 'S3 button Roll back' ($r -match "BUTTON: Roll back $N → $V")
Check "S3 No keeps $newer" ((Get-Content "$g\Wiz8Wide.installed.txt" -TotalCount 1) -eq "*version=$newer" -and (Test-Path "$g\Data\WIDE\NEWER.STI"))
$r = Gui 'install' 'yes'
Check 'S3 done text' ($r -match "rolled back from $N to $V")
Check "S3 $newer extras gone" (-not (Test-Path "$g\Data\WIDE\NEWER.STI") -and -not (Test-Path "$g\Data\NEWER"))
$c = Installed
Check 'S3 files' ($c -match 'installed check: 0 problem') $c
Check 'S3 MaxFps kept' ((IniValue "$g\wiz8wide.ini" 'Display' 'MaxFps') -eq '97')

"== S4 newer manifest format"
& "$sp\fake_newer.ps1" -Game $g -Version $newer -Format2 | Out-Null
$before = FolderSnap
$r = Gui
Check 'S4 uninstall button off' ($r -match 'UNINSTALL enabled: False')
Check 'S4 status' ($r -match 'comes from a newer installer')
$r1 = Cmd $new '--install'; $r2 = Cmd $new '--uninstall'
Check 'S4 install refused' ($r1 -match 'cannot safely change it')
Check 'S4 uninstall refused' ($r2 -match 'cannot safely change it')
Check 'S4 folder unchanged' ($before -eq (FolderSnap))
$m = "$g\Wiz8Wide.installed.txt"
[IO.File]::WriteAllText($m, ((Get-Content $m | Where-Object { $_ -ne '*format=2' }) -join "`r`n") + "`r`n")
$r = Gui 'install' 'yes'   # roll the fake newer version back again
Check 'S4 rollback after' ($r -match "rolled back from $N to $V")

"== S5 a copy fails halfway through a reinstall; Enabled=0 and settings survive"
SetIni "$g\wiz8ws.ini" 'General' 'Enabled' '0'
$conf = Join-Path $g 'dgVoodoo.conf'
[IO.File]::Delete($conf); [void][IO.Directory]::CreateDirectory($conf)
$r = Cmd $new '--install'
Check 'S5 failure text' ($r -match 'The patch is not installed now')
Check 'S5 no manifest, no keep' (-not (Test-Path $m) -and -not (Test-Path "$g\wiz8wide.ini.keep"))
Check 'S5 settings left for next time' ((IniValue "$g\wiz8wide.ini" 'Display' 'MaxFps') -eq '97' -and (IniValue "$g\wiz8ws.ini" 'General' 'Enabled') -eq '0')
[IO.Directory]::Delete($conf)
$extra = Get-ChildItem $g -Recurse -File | ForEach-Object { $_.FullName.Substring($g.Length + 1) } |
    Where-Object { -not (Test-Path (Join-Path 'C:\dev\wiz8-ws\games\reference' $_)) }
Check 'S5 only the settings files are extra' ((@($extra) -join ',') -eq 'wiz8wide.ini,wiz8ws.ini') ($extra -join ',')
$r = Cmd $new '--install'
Check 'S5 install again' ($r -match "patch $V is installed")
Check 'S5 settings back' ((IniValue "$g\wiz8wide.ini" 'Display' 'MaxFps') -eq '97' -and (IniValue "$g\wiz8ws.ini" 'General' 'Enabled') -eq '0')
Check 'S5 settings not saved as originals' (-not (Test-Path "$g\Wiz8Wide.backup\wiz8wide.ini") -and -not (Test-Path "$g\Wiz8Wide.backup\wiz8ws.ini"))
# what the diagnostics leave ([Debug] Diagnostics=1): uninstall must remove it too
New-Item -ItemType Directory -Force "$g\Wiz8Logs\2026-01-01_10-00-00" | Out-Null
foreach ($log in 'wiz8ws.log', 'wiz8hy.log', 'wiz8wide.log') { Set-Content "$g\Wiz8Logs\2026-01-01_10-00-00\$log" 'old session' }
Set-Content "$g\Wiz8Logs\crash-2026-01-01_10-00-00.dmp" 'dump'
Set-ItemProperty "$g\Wiz8Logs\crash-2026-01-01_10-00-00.dmp" -Name IsReadOnly -Value $true
$r = Gui 'uninstall'
$c = Uninstalled
Check 'S5 uninstall byte for byte (Wiz8Logs removed)' ($c -match 'uninstalled check: 0 problem') $c

"== S6 install over a manual install, with only a .keep left of the settings (the 1.0.0 failure state)"
Copy-Item "$files\*" $g -Recurse -Force
Copy-Item "$g\wiz8wide.ini" "$g\wiz8wide.ini.keep"
SetIni "$g\wiz8wide.ini.keep" 'Display' 'MaxFps' '55'
[IO.File]::Delete("$g\wiz8wide.ini")
$r = Cmd $new '--install'
Check 'S6 installed' ($r -match "patch $V is installed")
Check 'S6 settings from .keep' ((IniValue "$g\wiz8wide.ini" 'Display' 'MaxFps') -eq '55' -and -not (Test-Path "$g\wiz8wide.ini.keep"))
$saved = Get-ChildItem "$g\Wiz8Wide.backup" -Recurse -File | ForEach-Object { $_.FullName.Substring("$g\Wiz8Wide.backup".Length + 1) }
$bad = @($saved | Where-Object { $_ -match '^(version\.dll|wiz8hy\.dll|wiz8hy_hooks\.txt|wiz8ws\.ini|wiz8wide\.ini)$|^Data\\WIDE\\|_(768|856)\.STI$' })
Check 'S6 no patch files saved as originals' ($bad.Count -eq 0) ($bad -join ',')
"  saved as originals: " + ($saved -join ', ')
$r = Gui 'uninstall'
$c = Uninstalled
"  after uninstall: " + ($c -replace "`n", ' | ')
# the installer cannot know what a manual install put there before it: dgVoodoo, FALCON.STI
# (not loose in the original) and the folders it created come back; nothing that runs the patch
$left = @($c -split "`n" | Where-Object { $_ -match '^(EXTRA|CHANGED|MISSING) ' -and
    $_ -notmatch '^EXTRA (DDraw\.dll|D3DImm\.dll|dgVoodoo\.conf|Data\\OPTIONS\\FALCON\.STI)$' -and $_ -notmatch '^EXTRA DIR ' })
Check 'S6 uninstall leaves only the manual install''s dgVoodoo, FALCON.STI and empty folders' ($left.Count -eq 0) ($left -join ',')

"== S7 empty manifest"
robocopy C:\dev\wiz8-ws\games\reference $g /MIR /NFL /NDL /NJH /NJS /NP /MT:8 | Out-Null   # back to a clean copy
Get-ChildItem $g -Recurse -File | ForEach-Object { $_.Attributes = $_.Attributes -band -bnot [IO.FileAttributes]::ReadOnly }
New-Item -ItemType File $m -Force | Out-Null
$r = Gui
Check 'S7 empty list = not installed' ($r -match 'STATUS: Status: the patch is not installed' -and $r -match 'BUTTON: Install')
$r = Cmd $new '--install'
Check 'S7 install over it' ($r -match "patch $V is installed")
$r = Cmd $old '--uninstall'
$c = Uninstalled
Check 'S7 previous installer uninstalls this version byte for byte' ($c -match 'uninstalled check: 0 problem') $c

"== S8 the diagnostics checkbox and --diagnostics / --no-diagnostics ([Debug] Diagnostics of wiz8ws.ini)"
Add-Type -Namespace W8 -Name Ini -MemberDefinition '[DllImport("kernel32.dll", CharSet = CharSet.Unicode)] public static extern bool WritePrivateProfileString(string s, string k, string v, string f);'
function Diag { IniValue "$g\wiz8ws.ini" 'Debug' 'Diagnostics' }
function SetDiag([string]$value) { [void][W8.Ini]::WritePrivateProfileString('Debug', 'Diagnostics', $value, "$g\wiz8ws.ini") }
function Before([string]$r) { ($r -split '-- after --')[0] }   # the window before the button was pressed
function After([string]$r) { ($r -split '-- after --')[-1] }
function Clean([string]$name) {
    $c = Uninstalled
    Check "$name, uninstall byte for byte" ($c -match 'uninstalled check: 0 problem') $c
}
# S7 left the clean copy
$r = Gui 'install'
Check 'S8 fresh: checkbox off' ((Before $r) -match 'DIAG: checked False, enabled True') $r
Check 'S8 fresh, box left off: Diagnostics=0' ((Diag) -eq '0')
$c = Installed
Check 'S8 fresh off: wiz8ws.ini as in the package' ($c -match 'installed check: 0 problem') $c
$r = Gui 'install' 'yes' $g 'on'
Check 'S8 reinstall: box shows 0' ((Before $r) -match 'DIAG: checked False') $r
Check 'S8 reinstall, box ticked: Diagnostics=1' ((Diag) -eq '1')
Check 'S8 box shows 1 after it' ((After $r) -match 'DIAG: checked True') $r
$r = Gui 'install'
Check 'S8 reinstall: box shows 1' ((Before $r) -match 'DIAG: checked True') $r
Check 'S8 reinstall, box left on: Diagnostics=1 kept' ((Diag) -eq '1')
$c = Installed
Check 'S8 only the Diagnostics line differs' ($c -match 'installed check: 1 problem' -and $c -match 'DIFFERS FROM PACKAGE wiz8ws\.ini') $c
$r = Cmd $new '--install'
Check 'S8 --install without a switch keeps 1' ($r -match "patch $V is installed" -and (Diag) -eq '1') $r
# a failed reinstall (as S5) leaves Diagnostics=1 for the next attempt
$conf = Join-Path $g 'dgVoodoo.conf'
[IO.File]::Delete($conf); [void][IO.Directory]::CreateDirectory($conf)
$r = Cmd $new '--install'
Check 'S8 failed reinstall' ($r -match 'The patch is not installed now') $r
Check 'S8 failed reinstall keeps Diagnostics=1' ((Diag) -eq '1')
[IO.Directory]::Delete($conf)
$r = Gui 'install'
Check 'S8 after the failure: box shows 1, install keeps it' ((Before $r) -match 'DIAG: checked True' -and (Diag) -eq '1') $r
$r = Cmd $new '--install' @('--no-diagnostics')
Check 'S8 --no-diagnostics over 1: Diagnostics=0' ($r -match "patch $V is installed" -and (Diag) -eq '0') $r
$r = Gui 'install' 'yes' $g 'off'
Check 'S8 reinstall, box left off: Diagnostics=0 kept' ((Before $r) -match 'DIAG: checked False' -and (Diag) -eq '0') $r
$before = FolderSnap
$r = Cmd $new '--install' @('--diagnostic')
Check 'S8 unknown switch: exit 2, nothing changed' ($r -match 'EXIT: 2' -and $r -notmatch 'BOX' -and $before -eq (FolderSnap)) $r
$r = Cmd $new '--uninstall'
Clean 'S8 off'
$r = Cmd $new '--install' @('--diagnostics')
Check 'S8 fresh --diagnostics: Diagnostics=1' ($r -match "patch $V is installed" -and (Diag) -eq '1') $r
$r = Gui 'uninstall'
Clean 'S8 on (GUI uninstall)'
$r = Cmd $new '--install'
Check 'S8 fresh --install without a switch: Diagnostics=0' ($r -match "patch $V is installed" -and (Diag) -eq '0') $r
$r = Cmd $new '--uninstall'
Clean 'S8 fresh without a switch'
# updates from the previous release (its wiz8ws.ini has [Debug] without a Diagnostics line;
# 1 = the player added it, as the README says)
$cases = @(
    @{ Name = 'update, box left off'; Set = $null; Gui = 'keep'; Want = '0'; Shown = 'False' },
    @{ Name = 'update keeps 1 (GUI)'; Set = '1'; Gui = 'keep'; Want = '1'; Shown = 'True' },
    @{ Name = 'update keeps 0 (GUI, Diagnostics=0 written)'; Set = '0'; Gui = 'keep'; Want = '0'; Shown = 'False' },
    @{ Name = 'update, box unticked: 1 -> 0'; Set = '1'; Gui = 'off'; Want = '0'; Shown = 'True' },
    @{ Name = 'update, box ticked: 0 -> 1'; Set = $null; Gui = 'on'; Want = '1'; Shown = 'False' },
    @{ Name = 'update keeps 1 (command line)'; Set = '1'; Cmd = @(); Want = '1' },
    @{ Name = 'update keeps 0 (command line)'; Set = $null; Cmd = @(); Want = '0' },
    @{ Name = 'update --no-diagnostics: 1 -> 0'; Set = '1'; Cmd = @('--no-diagnostics'); Want = '0' },
    @{ Name = 'update --diagnostics: 0 -> 1'; Set = $null; Cmd = @('--diagnostics'); Want = '1' }
)
foreach ($case in $cases) {
    $r = Cmd $old '--install'
    SetIni "$g\wiz8wide.ini" 'Display' 'MaxFps' '97'
    if ($case.Set) { SetDiag $case.Set }
    if ($case.ContainsKey('Cmd')) {
        $r = Cmd $new '--install' $case.Cmd
    } else {
        $r = Gui 'install' 'yes' $g $case.Gui
        Check "S8 $($case.Name): box showed $($case.Shown)" ((Before $r) -match "DIAG: checked $($case.Shown)") $r
    }
    Check "S8 $($case.Name): updated" ($r -match "updated from $P to $V") $r
    Check "S8 $($case.Name): Diagnostics=$($case.Want)" ((Diag) -eq $case.Want) "Diagnostics=$(Diag)"
    Check "S8 $($case.Name): MaxFps kept" ((IniValue "$g\wiz8wide.ini" 'Display' 'MaxFps') -eq '97')
    $r = Cmd $new '--uninstall'
    Clean "S8 $($case.Name)"
}

"== RESULT: $script:passes passed, $script:fails failed"
