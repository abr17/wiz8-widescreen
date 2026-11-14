# Full installer scenario run on a fresh copy of games\reference (read-only flags cleared, like a
# real GOG/Steam folder): update from the previous release, the game running, rollback from a
# faked newer version, a newer manifest format, a copy failing halfway, a manual install, an
# empty manifest, uninstall back to the original byte for byte (the render driver and its logs
# included; an update takes out the dgVoodoo of 1.0.0-1.0.2), the diagnostics checkbox and
# --diagnostics / --no-diagnostics (fresh, reinstall, update, failure), the installer started in
# the game folder with an empty or relative folder, the report file (--report and the "Report a
# problem..." button), a game folder that has no 3DVideo.CFG, a package without the render
# driver. Prints PASS/FAIL per check.
#   pwsh -File tools_src\setup\tests\test_all.ps1 [-PreviousZip release\Wiz8Widescreen-1.0.0.zip]
# First build the package (scripts\build\make-hybrid-package.ps1). The scripts expect the package
# version to be newer than the previous zip; fake_newer.ps1 fakes the next version (last number + 1).
# Every path comes from where this script is in the repository: games\reference, the package in
# build\package\Wiz8Widescreen, and release\ for the default previous zip.
# Meant for Windows Sandbox (docs\testing.md): besides build\tmp\installer-test (deleted and
# re-created) and one start of the game (S2), S10 presses "Report a problem...", which saves a
# report zip to the Desktop of whoever runs the script and puts its path on the clipboard in
# place of what was there. The zip is deleted at the end of S10; a run stopped before that
# leaves it on the Desktop, with the paths of this machine in it.
param([string]$PreviousZip)
$ErrorActionPreference = 'Continue'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path
if (-not $PreviousZip) { $PreviousZip = "$root\release\Wiz8Widescreen-1.0.0.zip" }
$ref = "$root\games\reference"
# versions as regex text: this package (VERSION), the previous release (from the zip name) and
# the faked newer one
$version = (Get-Content "$root\VERSION" -TotalCount 1).Trim()
$parts = $version.Split('.'); $parts[-1] = [string]([int]$parts[-1] + 1); $newer = $parts -join '.'
$V = [regex]::Escape($version)
$N = [regex]::Escape($newer)
$P = [regex]::Escape(([regex]::Match((Split-Path $PreviousZip -Leaf), '\d+\.\d+\.\d+')).Value)
$sp = $PSScriptRoot
$t = "$root\build\tmp\installer-test"; $g = "$t\game"
$new = "$root\build\package\Wiz8Widescreen\Wiz8WideSetup.exe"
$files = "$root\build\package\Wiz8Widescreen\files"
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
function Installed { (& "$sp\check_install.ps1" -Game $g -Ref $ref -Files $files) -join "`n" }
function Uninstalled { (& "$sp\check_install.ps1" -Game $g -Ref $ref -Uninstalled) -join "`n" }
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
robocopy $ref $g /E /NFL /NDL /NJH /NJS /NP /MT:8 | Out-Null
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
# 1.0.0-1.0.2 installed dgVoodoo; the update takes it out and brings the render driver
$dgv = @('DDraw.dll', 'D3DImm.dll', 'dgVoodoo.conf' | Where-Object { Test-Path -LiteralPath "$g\$_" })
Check 'S1 dgVoodoo of the previous release removed' ($dgv.Count -eq 0) ($dgv -join ',')
Check 'S1 render driver installed, the game''s drivers untouched' ((Test-Path -LiteralPath "$g\Dll\srDD_D3D11.dll") -and
    (Get-FileHash "$g\Dll\srDD_DirectX7.dll").Hash -eq (Get-FileHash "$ref\Dll\srDD_DirectX7.dll").Hash)

"== S2 game running: reinstall and uninstall refused"
SetIni "$g\wiz8ws.ini" 'General' 'Enabled' '1'
Push-Location $root
. "$root\scripts\play\hybrid_session.ps1" -GameDir $g
Start-Wiz8 | Out-Null; Start-Sleep 10
$before = FolderSnap
$r1 = Gui 'install'; $r2 = Gui 'uninstall'
Check 'S2 reinstall refused' ($r1 -match 'is in use')
Check 'S2 uninstall refused' ($r2 -match 'is in use')
Check 'S2 folder unchanged' ($before -eq (FolderSnap))
$log = Get-Content "$g\wiz8ws.log" -TotalCount 1
Check 'S2 log has version' ($log -match "Wizardry 8 Widescreen $V") $log
Check 'S2 the game runs on the patch''s render driver' ((Get-Content "$g\3DVideo.CFG" -TotalCount 1).Trim() -eq 'D3D11' -and
    (Test-Path -LiteralPath "$g\Dll\srDD_D3D11.log")) (Get-Content "$g\3DVideo.CFG" -TotalCount 1)
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
# a folder in the place of a package file that is copied after Data\ (the render driver)
$conf = Join-Path $g 'Dll\srDD_D3D11.dll'
[IO.File]::Delete($conf); [void][IO.Directory]::CreateDirectory($conf)
$r = Cmd $new '--install'
Check 'S5 failure text' ($r -match 'The patch is not installed now')
Check 'S5 no manifest, no keep' (-not (Test-Path $m) -and -not (Test-Path "$g\wiz8wide.ini.keep"))
Check 'S5 settings left for next time' ((IniValue "$g\wiz8wide.ini" 'Display' 'MaxFps') -eq '97' -and (IniValue "$g\wiz8ws.ini" 'General' 'Enabled') -eq '0')
[IO.Directory]::Delete($conf)
$extra = Get-ChildItem $g -Recurse -File | ForEach-Object { $_.FullName.Substring($g.Length + 1) } |
    Where-Object { -not (Test-Path (Join-Path $ref $_)) }
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
# the installer cannot know what a manual install put there before it: the render driver (also
# released on its own), FALCON.STI (not loose in the original) and the folders it created come
# back; nothing that runs the patch
$left = @($c -split "`n" | Where-Object { $_ -match '^(EXTRA|CHANGED|MISSING) ' -and
    $_ -notmatch '^EXTRA (Dll\\srDD_D3D11\.dll|Data\\OPTIONS\\FALCON\.STI)$' -and $_ -notmatch '^EXTRA DIR ' })
Check 'S6 uninstall leaves only the manual install''s render driver, FALCON.STI and empty folders' ($left.Count -eq 0) ($left -join ',')

"== S7 empty manifest"
robocopy $ref $g /MIR /NFL /NDL /NJH /NJS /NP /MT:8 | Out-Null   # back to a clean copy
Get-ChildItem $g -Recurse -File | ForEach-Object { $_.Attributes = $_.Attributes -band -bnot [IO.FileAttributes]::ReadOnly }
New-Item -ItemType File $m -Force | Out-Null
$r = Gui
Check 'S7 empty list = not installed' ($r -match 'STATUS: Status: the patch is not installed' -and $r -match 'BUTTON: Install')
$r = Cmd $new '--install'
Check 'S7 install over it' ($r -match "patch $V is installed")
# what the patched game writes itself is in the list too, so the previous installer, which
# knows nothing of the render driver, removes its logs as well (made by hand: no game start here)
$unlisted = @('3DVideo.CFG', 'Dll\srDD_D3D11.log', 'Dll\srDD_D3D11.log.old' | Where-Object { (Get-Content -LiteralPath $m) -notcontains $_ })
Check 'S7 the list names 3DVideo.CFG and the render driver''s logs' ($unlisted.Count -eq 0) ($unlisted -join ', ')
Set-Content "$g\Dll\srDD_D3D11.log" 'the last session'
Set-Content "$g\Dll\srDD_D3D11.log.old" 'the session before'
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
$conf = Join-Path $g 'Dll\srDD_D3D11.dll'
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

"== S9 started in the game folder (the archive unpacked into it, no GOG key): no empty or relative folder"
# 1.0.2 read an empty folder (the GOG key that is not there, or "" on the command line) against the
# current folder: the window preselected an empty entry, and Install made a folder named
# D3DImm.dll in the game folder. Now the window offers nothing, an empty folder is refused, and
# "." on the command line is made the full path of the current folder.
function TreeSnap { (Get-ChildItem -LiteralPath $g -Recurse | ForEach-Object {
    if ($_.PSIsContainer) { 'D ' + $_.FullName } else { 'F ' + $_.FullName + '|' + (Get-FileHash -LiteralPath $_.FullName).Hash } }) -join "`n" }
function CmdHere([string[]]$setupArgs) { (& "$sp\run_setup.ps1" -Exe $new -SetupArgs $setupArgs -WorkingDirectory $g) -join "`n" }
# S8 left the clean copy
$r = (powershell -NoProfile -ExecutionPolicy Bypass -File "$sp\gui_setup.ps1" -Exe $new -WorkingDirectory $g) -join "`n"
Check 'S9 window started there: empty folder box, not-found status' ($r -match 'FOLDER: \[\]' -and $r -match 'STATUS: Wizardry 8 was not found automatically') $r
$before = TreeSnap
$r = CmdHere @('--install', '""')
Check 'S9 --install "" refused (exit 1, not a game folder)' ($r -match 'EXIT: 1' -and $r -match 'does not contain Wizardry 8') $r
Check 'S9 --install "": folder unchanged (no folder named after a package file)' ($before -eq (TreeSnap))
$r = CmdHere @('--install', '.')
Check 'S9 --install . installed (exit 0, manifest)' ($r -match 'EXIT: 0' -and $r -match "patch $V is installed" -and (Test-Path -LiteralPath "$g\Wiz8Wide.installed.txt")) $r
$c = Installed
Check 'S9 --install . files' ($c -match 'installed check: 0 problem') $c
$before = TreeSnap
$r = CmdHere @('--uninstall', '""')
Check 'S9 --uninstall "" refused, folder unchanged' ($r -match 'EXIT: 1' -and $r -match 'does not contain Wizardry 8' -and $before -eq (TreeSnap)) $r
$r = CmdHere @('--uninstall', '.')
$c = Uninstalled
Check 'S9 --uninstall . byte for byte' ($r -match 'EXIT: 0' -and $c -match 'uninstalled check: 0 problem') "$r $c"

"== S10 the report file: --report and the `"Report a problem...`" button"
# What a played and crashed game leaves, made by hand: the logs of the last session, the render
# driver's log and its log of the session before (over 8 MB, as with LogLevel=3: the report
# takes its start and its end), and in Wiz8Logs\ two earlier sessions and three crash dumps (the
# newest packs well, the two older ones do not pack at all: 15 MB goes in, with 12 MB more the
# archive would pass its 24 MB, so the oldest is left out). Files that are not the patch's stay out.
function Fake([string]$rel, [byte[]]$bytes, [int]$ageMinutes) {
    $path = Join-Path $g $rel
    New-Item -ItemType Directory -Force (Split-Path $path) | Out-Null
    [IO.File]::WriteAllBytes($path, $bytes)
    (Get-Item -LiteralPath $path).LastWriteTime = (Get-Date).AddMinutes(-$ageMinutes)
}
function Text([string]$line, [int]$times) { [Text.Encoding]::ASCII.GetBytes(($line + "`r`n") * $times) }
function Noise([int]$size, [int]$seed) { $b = New-Object byte[] $size; (New-Object Random $seed).NextBytes($b); , $b }
# S9 left the clean copy
$r = Cmd $new '--install' @('--diagnostics')
Check 'S10 installed with the diagnostics on' ($r -match "patch $V is installed" -and (Diag) -eq '1') $r
Fake 'wiz8ws.log' (Text '22:00:01.000 [ 1234] Wizardry 8 Widescreen (wiz8ws, loaded as version.dll proxy)' 300) 2
Fake 'wiz8hy.log' (Text 'hybrid log line' 50) 2
Fake 'wiz8wide.log' (Text '[Display] Mode=borderless: popup window at monitor size' 40) 2
Fake 'Dll\srDD_D3D11.log' (Text '0004067772 f0 t23c device: driver type hardware, feature level 0xb100' 80) 1
$oldLine = ' f0 t23c the render driver, the session before'
$sb = New-Object Text.StringBuilder
for ($i = 0; $i -lt 170000; $i++) { [void]$sb.Append($i.ToString('D8')).Append($oldLine).Append("`r`n") }
$oldLog = [Text.Encoding]::ASCII.GetBytes($sb.ToString())
Fake 'Dll\srDD_D3D11.log.old' $oldLog 200
Fake 'Wiz8Logs\2026-11-10_21-00-00\wiz8ws.log' (Text 'an older session' 100) 3000
Fake 'Wiz8Logs\2026-11-10_21-00-00\wiz8hy.log' ([byte[]]@()) 3000
Fake 'Wiz8Logs\2026-11-11_22-30-00\wiz8ws.log' (Text 'a newer session' 100) 90
Fake 'Wiz8Logs\2026-11-11_22-30-00\wiz8wide.log' (Text 'a newer session, wide' 10) 90
$dump = New-Object byte[] (6MB); $island = Noise 300000 1; [Array]::Copy($island, 0, $dump, 1000000, $island.Length)
Fake 'Wiz8Logs\crash-2026-11-11_22-31-00.dmp' $dump 80
Fake 'Wiz8Logs\crash-2026-11-09_10-00-00.dmp' (Noise (15MB) 2) 4000
Fake 'Wiz8Logs\crash-2026-11-08_10-00-00.dmp' (Noise (12MB) 3) 6000
Fake 'Wiz8Logs\notes.txt' (Text 'not the patch''s file' 1) 1
Fake 'Wiz8Logs\other\x.log' (Text 'not the patch''s file' 1) 1
$zip = "$t\report.zip"
$before = TreeSnap
$r = (& "$sp\run_setup.ps1" -Exe $new -SetupArgs @('--report', "`"$g`"", "`"$zip`"")) -join "`n"
Check 'S10 --report: exit 0 and no message box' ($r -match 'EXIT: 0' -and $r -notmatch 'BOX:') $r
Check 'S10 --report: the game folder is unchanged' ($before -eq (TreeSnap))
Add-Type -AssemblyName System.IO.Compression.FileSystem
$names = @(); $different = @(); $report = ''; $cut = ''
if (Test-Path -LiteralPath $zip) {
    $sha = [Security.Cryptography.SHA256]::Create()
    $z = [IO.Compression.ZipFile]::OpenRead($zip)
    foreach ($e in $z.Entries) {
        $names += $e.FullName
        $stream = $e.Open(); $memory = New-Object IO.MemoryStream; $stream.CopyTo($memory); $stream.Dispose()
        $bytes = $memory.ToArray()
        if ($e.FullName -eq 'report.txt') { $report = [Text.Encoding]::UTF8.GetString($bytes); continue }
        if ($e.FullName -eq 'Dll/srDD_D3D11.log.old') { $cut = [Text.Encoding]::ASCII.GetString($bytes); continue }
        $file = Join-Path $g ($e.FullName -replace '/', '\')
        if (-not (Test-Path -LiteralPath $file) -or
            [BitConverter]::ToString($sha.ComputeHash($bytes)) -ne [BitConverter]::ToString($sha.ComputeHash([IO.File]::ReadAllBytes($file)))) { $different += $e.FullName }
    }
    $z.Dispose()
}
$want = @('wiz8ws.log', 'wiz8hy.log', 'wiz8wide.log', 'Dll/srDD_D3D11.log', 'Dll/srDD_D3D11.log.old', 'wiz8ws.ini', 'wiz8wide.ini', 'Wiz8Wide.installed.txt',
    'Wiz8Logs/2026-11-10_21-00-00/wiz8ws.log', 'Wiz8Logs/2026-11-10_21-00-00/wiz8hy.log', 'Wiz8Logs/2026-11-11_22-30-00/wiz8ws.log',
    'Wiz8Logs/2026-11-11_22-30-00/wiz8wide.log', 'Wiz8Logs/crash-2026-11-11_22-31-00.dmp', 'Wiz8Logs/crash-2026-11-09_10-00-00.dmp', 'report.txt')
$lacking = @($want | Where-Object { $names -notcontains $_ })
Check 'S10 archive: read by Windows, has the logs, settings, sessions and dumps' ($names.Count -gt 0 -and $lacking.Count -eq 0) "missing: $($lacking -join ', ')"
Check 'S10 archive: every file in it but the long log is byte for byte the game folder''s' ($names.Count -gt 0 -and $different.Count -eq 0) "differ: $($different -join ', ')"
# the long log: whole lines of its start (1 MB) and of its end (7 MB), one line between them that
# says how many bytes are left out
$whole = [regex]::Matches($cut, '(?m)^\d{8}' + [regex]::Escape($oldLine) + '\r$').Count
$note = [regex]::Matches($cut, '(?m)^\[Wiz8WideSetup: (\d+) bytes of this log are left out here; the report holds its start and its end\]\r$')
$leftOut = if ($note.Count -eq 1) { [long]$note[0].Groups[1].Value } else { -1 }
$noteAt = if ($note.Count -eq 1) { $note[0].Index } else { 0 }
Check 'S10 archive: the long log is cut in the middle, at line ends, and says so' ($note.Count -eq 1 -and
    $whole + 1 -eq [regex]::Matches($cut, "`n").Count -and $cut.StartsWith('00000000' + $oldLine) -and $cut.EndsWith('00169999' + $oldLine + "`r`n") -and
    $noteAt -gt 1MB - 100 -and $noteAt -le 1MB -and $cut.Length - $noteAt -gt 7MB - 100 -and $cut.Length - $noteAt -le 7MB + 200 -and
    $cut.Length - ($note[0].Length + 1) + $leftOut -eq $oldLog.Length) "lines $whole, notes $($note.Count), left out $leftOut, kept $($cut.Length) of $($oldLog.Length)"
$foreign = @($names | Where-Object { $_ -match 'notes\.txt|other/|Saves/|\.exe$|\.dll$|crash-2026-11-08' })
Check 'S10 archive: nothing else (no foreign files, saves or programs; the dump that does not fit)' ($foreign.Count -eq 0) ($foreign -join ', ')
Check 'S10 archive: under 25 MB (GitHub''s limit)' ((Test-Path -LiteralPath $zip) -and (Get-Item -LiteralPath $zip).Length -lt 25MB)
Check 'S10 report.txt: the patch and the game' ($report -match "Patch installed: $V\r?\n" -and $report -match 'Wiz8\.exe: version 1\.2\.4 \(tested\)' -and $report -match 'Diagnostics mode: on') $report
Check 'S10 report.txt: the system' ($report -match 'System: Windows \d+\.\d+\.\d+ x(64|86)' -and $report -match 'Processor: \S' -and $report -match 'Memory: \d+ MB' -and $report -match 'Graphics: \S' -and $report -match 'Primary screen: \d+x\d+ at \d+ %') $report
Check 'S10 report.txt: lists the files, names the dump left out and why' ($report -match '  Wiz8Logs\\crash-2026-11-11_22-31-00\.dmp  6291456 bytes' -and $report -match 'Left out:\r?\n  Wiz8Logs\\crash-2026-11-08_10-00-00\.dmp  12582912 bytes  the archive would pass 24 MB\r?\n') $report
Check 'S10 report.txt: says that the long log is cut' ($report -match "(?m)^  Dll\\srDD_D3D11\.log\.old  $($cut.Length) bytes  [-\d]+ [:\d]+  cut: $leftOut bytes of its middle are left out\r?$") $report
# the programs are described, not packed: the patch's with their SHA-256, then binkw32.dll (the
# game's own here; under Wine the patch starts through it) and the dgVoodoo files (none here)
$undescribed = @('Dll\srDD_D3D11.dll', 'version.dll', 'wiz8hy.dll' | Where-Object {
    $report -notmatch ('(?m)^  ' + [regex]::Escape($_) + "  $((Get-Item -LiteralPath "$g\$_").Length) bytes  [-\d]+ [:\d]+  SHA-256 $((Get-FileHash -LiteralPath "$g\$_").Hash)\r?$") })
Check 'S10 report.txt: the patch''s programs with size, time and SHA-256' ($undescribed.Count -eq 0) "$($undescribed -join ', ') $report"
Check 'S10 report.txt: binkw32.dll there, the dgVoodoo files absent' ($report -match '(?m)^  binkw32\.dll  \d+ bytes  [-\d]+ [:\d]+\r?$' -and
    $report -match '(?m)^  DDraw\.dll  absent\r?$' -and $report -match '(?m)^  D3DImm\.dll  absent\r?$' -and $report -match '(?m)^  dgVoodoo\.conf  absent\r?$') $report
$r = (& "$sp\run_setup.ps1" -Exe $new -SetupArgs @('--report', "`"$t`"", "`"$t\none.zip`"")) -join "`n"
Check 'S10 --report for a folder without the game: exit 1, no file' ($r -match 'EXIT: 1' -and -not (Test-Path -LiteralPath "$t\none.zip")) $r
$r = (& "$sp\run_setup.ps1" -Exe $new -SetupArgs @('--report', "`"$g`"", "`"$t\none.zip`"", 'more')) -join "`n"
Check 'S10 --report with one argument too many: exit 2, no file' ($r -match 'EXIT: 2' -and -not (Test-Path -LiteralPath "$t\none.zip")) $r
# the button: the file goes to the Desktop, its path to the clipboard; the question is declined
$desktop = [Environment]::GetFolderPath('DesktopDirectory')
$had = @(Get-ChildItem -LiteralPath $desktop -Filter 'Wiz8Wide-report-*.zip' -ErrorAction SilentlyContinue | ForEach-Object { $_.FullName })
$r = Gui 'report' 'no'
$made = @(Get-ChildItem -LiteralPath $desktop -Filter 'Wiz8Wide-report-*.zip' -ErrorAction SilentlyContinue | ForEach-Object { $_.FullName } | Where-Object { $had -notcontains $_ })
Check 'S10 button: one new report file on the Desktop' ($made.Count -eq 1) "$($made -join ', ') $r"
$saved = if ($made.Count -ge 1) { $made[0] } else { '' }
Check 'S10 button: the box names that file and asks about the bug report page' ($saved -and $r.Contains($saved) -and $r -match 'The report file was saved:' -and $r -match 'Open the bug report page on GitHub now\?' -and $r -match 'answered no') $r
Check 'S10 button: the box says that not everything fit (the dump left out, the log cut)' ($r -match 'Not everything fit into the file: its report\.txt says what was left out or shortened\.') $r
$clip = ''; try { Add-Type -AssemblyName System.Windows.Forms; $clip = [Windows.Forms.Clipboard]::GetText() } catch { $clip = "clipboard: $_" }
Check 'S10 button: the path of the file is on the clipboard' ($saved -and $clip -eq $saved) $clip
$inside = @()
if ($saved) { $z = [IO.Compression.ZipFile]::OpenRead($saved); $inside = @($z.Entries | ForEach-Object { $_.FullName }); $z.Dispose() }
Check 'S10 button: the file is the same kind of archive' ($inside -contains 'report.txt' -and $inside -contains 'wiz8ws.log' -and $inside -contains 'Wiz8Logs/crash-2026-11-11_22-31-00.dmp') ($inside -join ', ')
Check 'S10 button: the game folder is unchanged, the window stayed as it was' ($before -eq (TreeSnap) -and (After $r) -match 'BUTTON: Reinstall') $r
foreach ($f in $made) { Remove-Item -LiteralPath $f -Force }
Remove-Item -LiteralPath $zip -Force -ErrorAction SilentlyContinue
# a reinstall with the diagnostics on keeps the last session for a later report: its logs, the
# render driver's two from Dll\ with them, move into one new session folder of Wiz8Logs\
$sessions = @(Get-ChildItem -LiteralPath "$g\Wiz8Logs" -Directory | ForEach-Object { $_.Name })
$r = Cmd $new '--install'
$kept = @(Get-ChildItem -LiteralPath "$g\Wiz8Logs" -Directory | Where-Object { $sessions -notcontains $_.Name } | ForEach-Object { $_.FullName })
$moved = @('wiz8ws.log', 'wiz8hy.log', 'wiz8wide.log', 'srDD_D3D11.log', 'srDD_D3D11.log.old' | Where-Object { $kept.Count -eq 1 -and (Test-Path -LiteralPath (Join-Path $kept[0] $_)) })
$stayed = @('wiz8ws.log', 'wiz8hy.log', 'wiz8wide.log', 'Dll\srDD_D3D11.log', 'Dll\srDD_D3D11.log.old' | Where-Object { Test-Path -LiteralPath "$g\$_" })
$movedLong = if ($moved.Count -eq 5) { (Get-Item -LiteralPath (Join-Path $kept[0] 'srDD_D3D11.log.old')).Length } else { -1 }
Check 'S10 reinstall: the last session''s five logs moved into one new Wiz8Logs folder' ($r -match "patch $V is installed" -and $moved.Count -eq 5 -and $stayed.Count -eq 0 -and
    $movedLong -eq $oldLog.Length) "moved: $($moved -join ', '); stayed: $($stayed -join ', '); $r"
# what is not the patch's would stay after an uninstall: take it out, then the folder must be the original
Remove-Item -LiteralPath "$g\Wiz8Logs\notes.txt", "$g\Wiz8Logs\other" -Recurse -Force
$r = Cmd $new '--uninstall'
Clean 'S10'

"== S11 a game folder that has no 3DVideo.CFG: the one the patched game writes goes with the patch"
# The patched game writes 3DVideo.CFG at every start, with the patch's render driver in line 1.
# Left behind by an uninstall, it would keep the original game from starting: it has no such
# driver. The file is made by hand here, as the game writes it.
function GameWritesVideoConfig { [IO.File]::WriteAllText("$g\3DVideo.CFG", "D3D11`n1920`n1080`n32`nMiles Fast 2D Positional Audio`n") }
# S10 left the clean copy; its 3DVideo.CFG, if the reference has one, waits outside the game folder
$original = Test-Path -LiteralPath "$g\3DVideo.CFG"
if ($original) { Move-Item -LiteralPath "$g\3DVideo.CFG" -Destination "$t\3DVideo.CFG" }
$r = Cmd $new '--install'
Check 'S11 installed: 3DVideo.CFG is in the list, nothing saved for it' ($r -match "patch $V is installed" -and (Get-Content -LiteralPath $m) -contains '3DVideo.CFG' -and
    -not (Test-Path -LiteralPath "$g\Wiz8Wide.backup\3DVideo.CFG")) $r
GameWritesVideoConfig
$r = Cmd $new '--install'
Check 'S11 reinstall: the game''s file is removed, not saved as an original' ($r -match "patch $V is installed" -and -not (Test-Path -LiteralPath "$g\3DVideo.CFG") -and
    -not (Test-Path -LiteralPath "$g\Wiz8Wide.backup\3DVideo.CFG")) $r
GameWritesVideoConfig
$r = Cmd $new '--uninstall'
Check 'S11 uninstall removes the game''s 3DVideo.CFG' (-not (Test-Path -LiteralPath "$g\3DVideo.CFG")) $r
$r = Cmd $new '--install'
GameWritesVideoConfig
$r = Cmd $old '--uninstall'
Check 'S11 so does the previous installer' (-not (Test-Path -LiteralPath "$g\3DVideo.CFG")) $r
if ($original) { Move-Item -LiteralPath "$t\3DVideo.CFG" -Destination "$g\3DVideo.CFG" }
Clean 'S11'

"== S12 a package without the render driver (an antivirus took the DLL, a partial unpack): refused before anything is changed"
$broken = "$t\pkg-no-driver"
Copy-Item -LiteralPath (Split-Path $new) -Destination $broken -Recurse
Remove-Item -LiteralPath "$broken\files\Dll\srDD_D3D11.dll" -Force
function Refused([string]$r) { $r -match 'EXIT: 1' -and $r -match 'A file of the patch is missing from the "files" folder' -and $r -match 'files\\Dll\\srDD_D3D11\.dll' -and $r -match 'Nothing was changed' }
# S11 left the clean copy
$before = TreeSnap
$r = Cmd "$broken\Wiz8WideSetup.exe" '--install'
Check 'S12 fresh install refused: the message names the missing file, folder unchanged' ((Refused $r) -and $before -eq (TreeSnap)) $r
# over the previous release: without the check the update would remove it and then report success
$r = Cmd $old '--install'
$before = TreeSnap
$r = Cmd "$broken\Wiz8WideSetup.exe" '--install'
Check 'S12 update refused: the previous release stays as it was' ((Refused $r) -and $before -eq (TreeSnap)) $r
$r = Cmd $old '--uninstall'
Clean 'S12'

"== RESULT: $script:passes passed, $script:fails failed"
