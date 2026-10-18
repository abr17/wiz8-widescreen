# Full installer scenario run on a fresh copy of games\reference (read-only flags cleared, like a
# real GOG/Steam folder): update from the previous release, the game running, rollback from a
# faked newer version, a newer manifest format, a copy failing halfway, a manual install, an
# empty manifest, uninstall back to the original byte for byte. Prints PASS/FAIL per check.
#   pwsh -File tools_src\setup\tests\test_all.ps1 [-PreviousZip release\Wiz8Widescreen-1.0.0.zip]
# First build the package (scripts\build\make-hybrid-package.ps1). The scripts expect the package
# version to be newer than the previous zip and older than 1.0.2 (fake102.ps1 fakes 1.0.2).
# Uses build\tmp\installer-test (deleted and re-created) and starts the game once (S2).
param([string]$PreviousZip = 'C:\dev\wiz8-ws\release\Wiz8Widescreen-1.0.0.zip')
$ErrorActionPreference = 'Continue'
# versions as regex text: this package (VERSION) and the previous release (from the zip name)
$V = [regex]::Escape((Get-Content 'C:\dev\wiz8-ws\VERSION' -TotalCount 1).Trim())
$P = [regex]::Escape(([regex]::Match((Split-Path $PreviousZip -Leaf), '\d+\.\d+\.\d+')).Value)
$sp = $PSScriptRoot
$t = 'C:\dev\wiz8-ws\build\tmp\installer-test'; $g = "$t\game"
$new = 'C:\dev\wiz8-ws\build\package\Wiz8Widescreen\Wiz8WideSetup.exe'
$files = 'C:\dev\wiz8-ws\build\package\Wiz8Widescreen\files'
$script:fails = 0; $script:passes = 0
function Check([string]$name, [bool]$ok, [string]$detail = '') {
    if ($ok) { $script:passes++; "PASS $name" } else { $script:fails++; "FAIL $name $detail" }
}
function Gui([string]$click = 'none', [string]$answer = 'yes', [string]$folder = $g) {
    (powershell -NoProfile -ExecutionPolicy Bypass -File "$sp\gui_setup.ps1" -Exe $new -Folder $folder -Click $click -Answer $answer) -join "`n"
}
function Cmd([string]$exe, [string]$action) { (& "$sp\run_setup.ps1" -Exe $exe -SetupArgs @($action, "`"$g`"")) -join "`n" }
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

"== S1 update 1.0.0 -> 1.0.1 keeps wiz8wide.ini and Enabled=0 (folder typed with a trailing backslash)"
$r = Cmd $old '--install'
SetIni "$g\wiz8wide.ini" 'Display' 'MaxFps' '97'
SetIni "$g\wiz8ws.ini" 'General' 'Enabled' '0'
$r = Gui 'install' 'yes' "$g\"
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

"== S3 rollback from a faked 1.0.2"
& "$sp\fake102.ps1" -Game $g | Out-Null
$r = Gui 'install' 'no'
Check 'S3 button Roll back' ($r -match "BUTTON: Roll back 1\.0\.2 → $V")
Check 'S3 No keeps 1.0.2' ((Get-Content "$g\Wiz8Wide.installed.txt" -TotalCount 1) -eq '*version=1.0.2' -and (Test-Path "$g\Data\WIDE\NEW102.STI"))
$r = Gui 'install' 'yes'
Check 'S3 done text' ($r -match "rolled back from 1\.0\.2 to $V")
Check 'S3 1.0.2 extras gone' (-not (Test-Path "$g\Data\WIDE\NEW102.STI") -and -not (Test-Path "$g\Data\NEW102"))
$c = Installed
Check 'S3 files' ($c -match 'installed check: 0 problem') $c
Check 'S3 MaxFps kept' ((IniValue "$g\wiz8wide.ini" 'Display' 'MaxFps') -eq '97')

"== S4 newer manifest format"
& "$sp\fake102.ps1" -Game $g -Format2 | Out-Null
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
$r = Gui 'install' 'yes'   # roll the fake 1.0.2 back again
Check 'S4 rollback after' ($r -match "rolled back from 1\.0\.2 to $V")

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
$r = Gui 'uninstall'
$c = Uninstalled
Check 'S5 uninstall byte for byte' ($c -match 'uninstalled check: 0 problem') $c

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
Check 'S7 1.0.0 installer uninstalls 1.0.1 byte for byte' ($c -match 'uninstalled check: 0 problem') $c

"== RESULT: $script:passes passed, $script:fails failed"
