# Isolated Linux bench: runs the game under Wine or Proton in a throw-away Docker container,
# like Windows Sandbox (a fresh prefix and game copy every run; the host gets one new folder).
#   powershell -File scripts\linux\linux_bench.ps1 [-Runner proton|wine] [-Overrides 'version=n,b'|none]
#       [-Install files|setup|none] [-Desktop 1280x800|none] [-Wait 30] [-Actions file] [-Canvas 768]
#       [-Timeout 300] [-WineDebug +seh] [-EnvVar NAME=VALUE,...] [-Game dir] [-Patch dir | -Zip file]
#       [-Then 'version=n,b,none'] [-Uninstall] [-GlobalOverride NAME=ORDER,...]
#       [-SetupPrefix same|other] [-Launcher none|shortcut|heroic|lutris] [-Ini Section.Key=Value,...]
#       [-Load save.SAV] [-Name label] [-OutRoot dir] [-Memory 6g] [-Cpus 4] [-Gpu] [-Show [-Hold]] [-Rebuild]
# Needs Docker Desktop (WSL2 backend, Linux containers) running. Builds the image from this
# folder when it is missing or was built from other versions of Dockerfile/bake.sh/bench.sh
# (the image label wiz8bench.scripts holds their SHA-256; -Rebuild forces a build; the first
# one downloads about 1 GB and takes 5-10 minutes).
# Mounts, nothing else: -Game read-only at /game (default games\reference), -Patch read-only at
# /patch (default build\package\Wiz8Widescreen; -Zip extracts a release zip into
# build\tmp\linux-bench\_zip\<name>-<hash>\, once per zip content, and uses that), and a new
# folder build\tmp\linux-bench\<time>-<runner>-<install>[-<name>]\ at /out. No network, no
# privileges. -Gpu adds WSL's GPU device /dev/dxg and the WSL libraries (/usr/lib/wsl,
# read-only) and nothing else: OpenGL on the Windows GPU, Proton only (bench.sh --gpu).
# -Show: the WSL sandbox instead of the container, to watch the run as in Windows Sandbox. The
# image is exported once per image version to build\tmp\linux-bench\_wsl\rootfs-<id>.tar, and
# every run imports it as a new WSL2 distro wiz8-bench-<label> (its disk in _wsl\<label>\),
# deleted after the run. The bench's screen is then a window on the Windows desktop (WSLg). In
# the distro (sandbox.sh, wsl.conf) only the same three folders are mounted, Windows programs
# cannot be started and the game has no network; -Memory and -Cpus do not apply (WSL's own
# limits do). One -Show run at a time: a new one removes wiz8-bench-* distros left by a killed
# run. -Hold keeps the game running after the actions until it is quit or the window is closed.
# The options go to bench.sh (its header explains them); -Actions is copied into
# the output folder first (as LF text). -Overrides none (or '') = WINEDLLOVERRIDES not set; use
# none from Windows PowerShell 5.1, which drops an empty '' argument to powershell -File.
# The options of the Wine settings and detection checks (bench.sh --then and so on):
#   -Then          one more start of the game in the same prefix per value, with that
#                  WINEDLLOVERRIDES (none = not set): -Then 'version=n,b,none' is a second start
#                  with the launch option and a third one without it. Give the list as one
#                  string, as powershell -File passes it anyway; it is split before each none and
#                  before each NAME= that follows a whole NAME=ORDER (a comma inside version=n,b
#                  stays, and so does Wine's form for several names, version,ddraw=n,b).
#   -Uninstall     Wiz8WideSetup.exe --uninstall after the last start, then the registry and the
#                  game copy again (the patch package is needed for it)
#   -GlobalOverride  NAME=ORDER in HKCU\Software\Wine\DllOverrides of the game's prefix (as
#                  winecfg sets it), before the installer and the first start
#   -SetupPrefix   other = the installer in a second fresh prefix, not the game's (as when it is
#                  started on its own); needs -Install setup or -Uninstall
#   -Launcher      shortcut (Steam, the game as a non-Steam game), heroic, lutris: that
#                  launcher's files in a fake home folder, the game copy and its prefix where
#                  that launcher keeps them (home.txt lists them), the game started as it starts it
#   -Ini           Section.Key=Value in the game copy's wiz8ws.ini or wiz8wide.ini after the
#                  install (Display.Mode=fullscreen,Display.ScreenWidth=1024,Display.ScreenHeight=768)
#   -Load          a save file for the 3D world: copied into the game copy as Saves\Quick 1.SAV,
#                  and the game is started with /LOAD (no intro, no main menu); give it time
#                  to load (-Wait 90)
#   -Desktop none  no Wine virtual desktop: the game on a bare X screen of 1280x800
#                  (none:1920x1080 for another size), as on a Linux desktop
# Prints summary.txt and the output folder; the exit code is bench.sh's (0 = finished,
# 1 = bad arguments, 2 = bench error). The standard checks (docs\testing.md):
#   -Overrides none                 patch loaded: no (Wine's own version.dll)
#   (defaults)                      patch loaded: yes, version.dll native, ddraw.dll Wine's own
#   -Install setup -Overrides none  the installer's registry overrides make it load; with the
#                                   1.0.3 installer and the GOG/Steam game it also sets up the
#                                   binkw32 route, whose copy starts the patch (the registry
#                                   values are written too)
#   -Overrides 'version=n,b;ddraw=n,b'  a DDraw.dll in the game folder, for experiments (the
#                                   packages up to 1.0.2 had dgVoodoo's; 1.0.3 has none)
# and of the Wine settings the patch and the installer keep (needs a package after 1.0.2):
#   -Then none                      start 2: wine settings: *version already set ..., patch loaded: yes
#   -Install setup -Overrides none -Then none -Uninstall
#                                   both starts load the patch; after the uninstall registry
#                                   AppDefaults\Wiz8.exe and registry Wiz8Wide: not present
#   -Overrides 'version=n,b;ddraw=n,b' -Then none
#                                   start 1: "*ddraw not written: WINEDLLOVERRIDES asks for
#                                   ddraw=n,b"; start 2 gets Wine's own ddraw.dll
#   -GlobalOverride ddraw=native -Then none
#                                   with a package up to 1.0.2: start 1: dgVoodoo (it crashes)
#                                   after "*ddraw written"; start 2: ddraw.dll builtin
#   -Launcher shortcut -Install setup -Overrides none
#                                   the installer's verdict: the game's own prefix; values
#                                   written, patch loaded: yes (also heroic, lutris)
#   -Launcher shortcut -Install setup -SetupPrefix other -Overrides none -Then 'version=n,b,none'
#                                   the GOG/Steam game: patch loaded: yes at every start, start 1
#                                   started from: binkw32.dll (no launch option needed);
#                                   version.dll: Wine's own, and *version written; without the
#                                   route (another mod's binkw32.dll, a mock game): start 1 no
#                                   (nothing written), start 2 yes (*version written), start 3 yes
#                                   without the option (also heroic, lutris)
#   -Ini Display.Mode=fullscreen,Display.ScreenWidth=1024,Display.ScreenHeight=768
#                                   fullscreen picture: 1024x768 drawn, scaled into 1066x800 at
#                                   (107,0) of the 1280x800 window; click640 lands inside it
param(
    [ValidateSet('proton', 'wine')][string]$Runner = 'proton',
    [AllowEmptyString()][string]$Overrides = 'version=n,b',
    [ValidateSet('files', 'setup', 'none')][string]$Install = 'files',
    [ValidatePattern('^(\d{3,4}x\d{3,4}|none(:\d{3,4}x\d{3,4})?)$')][string]$Desktop = '1280x800',
    [int]$Wait = 30,
    [string]$Actions = '',
    [int]$Canvas = 0,
    [int]$Timeout = 300,
    [string]$WineDebug = '',
    [string[]]$EnvVar = @(),
    [AllowEmptyString()][string[]]$Then = @(),
    [switch]$Uninstall,
    [string[]]$GlobalOverride = @(),
    [ValidateSet('same', 'other')][string]$SetupPrefix = 'same',
    [ValidateSet('none', 'shortcut', 'heroic', 'lutris')][string]$Launcher = 'none',
    [string[]]$Ini = @(),
    [string]$Load = '',
    [string]$Game = '',
    [string]$Patch = '',
    [string]$Zip = '',
    [string]$OutRoot = '',
    [ValidatePattern('^[A-Za-z0-9_.-]*$')][string]$Name = '',
    [string]$Image = 'wiz8-linux-bench:1',
    [string]$Memory = '6g',
    [string]$Cpus = '4',
    [switch]$Gpu,
    [switch]$Show,
    [switch]$Hold,
    [switch]$Rebuild
)
$ErrorActionPreference = 'Stop'
if ($Overrides -eq 'none') { $Overrides = '' }
if ($Gpu -and $Runner -ne 'proton') { throw '-Gpu needs -Runner proton (its WoW64 mode; Ubuntu''s Wine 9.0 cannot use the 64-bit GPU driver)' }
if ($Hold -and -not $Show) { throw '-Hold needs -Show' }
if ($SetupPrefix -eq 'other' -and $Install -ne 'setup' -and -not $Uninstall) {
    throw '-SetupPrefix other needs -Install setup or -Uninstall (it is where the installer runs)'
}
$root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
if (-not $Game) { $Game = Join-Path $root 'games\reference' }
if (-not $Patch) { $Patch = Join-Path $root 'build\package\Wiz8Widescreen' }
if (-not $OutRoot) { $OutRoot = Join-Path $root 'build\tmp\linux-bench' }
# absolute (docker needs an absolute mount source; .NET calls do not know PowerShell's folder)
$OutRoot = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($OutRoot)

# docker with stderr hidden; Windows PowerShell turns a native command's redirected stderr
# into errors under 'Stop', so this runs under 'Continue'
function Invoke-DockerQuiet {
    $old = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
    try { $text = & docker @args 2>$null; return @{ Code = $LASTEXITCODE; Text = $text } }
    finally { $ErrorActionPreference = $old }
}
function Invoke-WslQuiet {
    $old = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
    try { $text = & wsl.exe @args 2>$null; return @{ Code = $LASTEXITCODE; Text = $text } }
    finally { $ErrorActionPreference = $old }
}

# (docker templates without spaces or quotes: Windows PowerShell 5.1 passes a native argument
# with embedded double quotes broken)
$r = Invoke-DockerQuiet info --format '{{.OSType}}/{{.NCPU}}'
if ($r.Code -ne 0) { throw 'Docker is not running: start Docker Desktop (WSL2 backend) and try again' }
$osType, $ncpu = "$($r.Text)".Trim().Split('/')
if ($osType -ne 'linux') { throw 'Docker Desktop is in Windows containers mode: switch it to Linux containers' }
# docker refuses --cpus above what its VM has
if ([double]::Parse($Cpus, [Globalization.CultureInfo]::InvariantCulture) -gt [int]$ncpu) { $Cpus = $ncpu }

# --- the image: built when missing or when the scripts it is made from changed ---
$sha = [Security.Cryptography.SHA256]::Create()
$text = (('Dockerfile', 'bake.sh', 'bench.sh', 'sandbox.sh', 'wsl.conf') | ForEach-Object {
    [IO.File]::ReadAllText((Join-Path $PSScriptRoot $_)).Replace("`r`n", "`n") }) -join "`n"
$hash = -join ($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($text)) | ForEach-Object { $_.ToString('x2') })
$r = Invoke-DockerQuiet image inspect --format '{{json .Config.Labels}}' $Image
$have = ''
if ($r.Code -eq 0) {
    $labels = "$($r.Text)" | ConvertFrom-Json
    if ($labels -and $labels.'wiz8bench.scripts') { $have = $labels.'wiz8bench.scripts' }
}
if ($Rebuild -or $have -ne $hash) {
    Write-Host ($(if ($r.Code -eq 0) { "Rebuilding $Image (scripts changed or -Rebuild)" } else { "Building $Image" }))
    $old = $ErrorActionPreference; $ErrorActionPreference = 'Continue'   # build progress goes to stderr
    & docker build --label "wiz8bench.scripts=$hash" -t $Image $PSScriptRoot
    $code = $LASTEXITCODE; $ErrorActionPreference = $old
    if ($code -ne 0) { throw "docker build failed ($code)" }
}

# --- inputs ---
if ($Zip) {
    # one folder per zip content: a rebuilt zip of the same name gets a new folder, never a stale one
    $Zip = (Resolve-Path -LiteralPath $Zip).Path
    $zipHash = (Get-FileHash -LiteralPath $Zip -Algorithm SHA256).Hash.Substring(0, 12).ToLower()
    $dest = Join-Path $OutRoot ('_zip\' + [IO.Path]::GetFileNameWithoutExtension($Zip) + "-$zipHash")
    if (-not (Test-Path -LiteralPath $dest)) {
        $part = "$dest.part"
        if (Test-Path -LiteralPath $part) { Remove-Item -LiteralPath $part -Recurse -Force }
        Expand-Archive -LiteralPath $Zip -DestinationPath $part
        Rename-Item -LiteralPath $part -NewName (Split-Path -Leaf $dest)
    }
    $setup = Get-ChildItem -LiteralPath $dest -Recurse -Filter 'Wiz8WideSetup.exe' | Select-Object -First 1
    if (-not $setup) { throw "no Wiz8WideSetup.exe in $Zip" }
    $Patch = $setup.DirectoryName
}
$Game = (Resolve-Path -LiteralPath $Game).Path
if (-not (Test-Path -LiteralPath (Join-Path $Game 'Wiz8.exe'))) { throw "no Wiz8.exe in $Game" }
$usePatch = $Install -ne 'none' -or $Uninstall -or (Test-Path -LiteralPath $Patch)
if ($usePatch) {
    $Patch = (Resolve-Path -LiteralPath $Patch).Path
    if (-not (Test-Path -LiteralPath (Join-Path $Patch 'files'))) { throw "no files\ folder in $Patch" }
}
foreach ($p in @($Game, $Patch)) { if ($p -match '[,"]') { throw "a path with a comma or quote cannot be mounted: $p" } }

$label = (Get-Date -Format 'yyyyMMdd-HHmmss') + "-$Runner-$Install" + $(if ($Name) { "-$Name" } else { '' })
$base = $label
for ($i = 2; Test-Path -LiteralPath (Join-Path $OutRoot $label); $i++) { $label = "$base-$i" }
$out = Join-Path $OutRoot $label
New-Item -ItemType Directory -Force $out | Out-Null
if ($out -match '[,"]') { throw "a path with a comma or quote cannot be mounted: $out" }

# --- bench.sh options (always --name=value: an empty value survives Windows PowerShell) ---
$opts = @("--runner=$Runner", "--overrides=$Overrides", "--install=$Install", "--desktop=$Desktop",
          "--wait=$Wait", "--timeout=$Timeout")
if ($Canvas -gt 0) { $opts += "--canvas=$Canvas" }
if ($WineDebug) { $opts += "--winedebug=$WineDebug" }
# powershell -File passes -EnvVar A=1,B=2 as one string: split it before each NAME=
foreach ($e in $EnvVar) { foreach ($v in ($e -split ',(?=[A-Za-z_][A-Za-z0-9_]*=)')) { $opts += "--env=$v" } }
if ($Actions) {
    # as LF text without a BOM, whatever the editor wrote (CRLF, UTF-16)
    $steps = @(Get-Content -LiteralPath $Actions) -join "`n"
    [IO.File]::WriteAllText((Join-Path $out 'actions.txt'), "$steps`n", (New-Object Text.UTF8Encoding $false))
    $opts += '--actions=/out/actions.txt'
}
if ($Load) {
    # a save for the 3D world: the bench puts it into the game copy as Saves\Quick 1.SAV and
    # starts the game with /LOAD (bench.sh --load)
    if (-not (Test-Path -LiteralPath $Load -PathType Leaf)) { throw "the save file is missing: $Load" }
    Copy-Item -LiteralPath $Load -Destination (Join-Path $out 'load.sav')
    $opts += '--load=/out/load.sav'
}
if ($Gpu) { $opts += '--gpu=yes' }
if ($Hold) { $opts += '--hold=yes' }
# one start per value; powershell -File passes -Then version=n,b,none as one string: split it
# at the commas before none, and before a NAME= once the value so far is none or a whole
# NAME=ORDER entry, so that Wine's version,ddraw=n,b (several names, one order) stays one value
foreach ($t in $Then) {
    $values = @(); $value = $null
    foreach ($part in ($t -split ',')) {
        if ($null -eq $value) { $value = $part }
        elseif ($part -eq 'none' -or ($part -match '^[A-Za-z0-9_.*-]+=' -and ($value -eq 'none' -or $value -match '='))) {
            $values += $value; $value = $part
        } else { $value += ",$part" }
    }
    $values += $value
    foreach ($v in $values) {
        $opts += $(if ($v -eq 'none') { '--then=' } else { "--then=$v" })
    }
}
if ($Uninstall) { $opts += '--uninstall=yes' }
# bench.sh splits a value with several entries itself (before each NAME= or Section.Key=)
foreach ($g in $GlobalOverride) { $opts += "--global-override=$g" }
if ($SetupPrefix -ne 'same') { $opts += "--setup-prefix=$SetupPrefix" }
if ($Launcher -ne 'none') { $opts += "--launcher=$Launcher" }
foreach ($e in $Ini) { $opts += "--ini=$e" }

if ($Show) {
    # --- the WSL sandbox: a new WSL2 distro from the image for this run, deleted after it ---
    $env:WSL_UTF8 = '1'   # wsl.exe writes UTF-16 otherwise
    $wslRoot = Join-Path $OutRoot '_wsl'
    New-Item -ItemType Directory -Force $wslRoot | Out-Null
    $r = Invoke-WslQuiet --list --quiet
    if ($r.Code -ne 0) { throw 'WSL is not available (wsl --list failed)' }
    # left by a run that was killed: only this bench's own distros and disk folders
    foreach ($d in @($r.Text | ForEach-Object { "$_".Trim([char]0, ' ') } | Where-Object { $_ -like 'wiz8-bench-*' })) {
        Write-Host "Removing the WSL sandbox $d left by an earlier run"
        Invoke-WslQuiet --unregister $d | Out-Null
    }
    Get-ChildItem -LiteralPath $wslRoot -Directory | ForEach-Object { Remove-Item -LiteralPath $_.FullName -Recurse -Force }
    # the image as a root file system for wsl --import, once per image version
    $r = Invoke-DockerQuiet image inspect --format '{{.Id}}' $Image
    $imageId = "$($r.Text)".Trim() -replace '^sha256:', ''
    if ($r.Code -ne 0 -or $imageId.Length -lt 12) { throw "docker image inspect $Image failed" }
    $tar = Join-Path $wslRoot "rootfs-$($imageId.Substring(0, 12)).tar"
    if (-not (Test-Path -LiteralPath $tar)) {
        Get-ChildItem -LiteralPath $wslRoot -Filter 'rootfs-*' | Remove-Item -Force   # older image versions
        Write-Host "Exporting $Image for WSL (once per image version, a few minutes)"
        $tmp = "wiz8-bench-export-$label"
        $r = Invoke-DockerQuiet create --name $tmp $Image
        if ($r.Code -ne 0) { throw "docker create $Image failed" }
        $r = Invoke-DockerQuiet export -o "$tar.part" $tmp
        Invoke-DockerQuiet rm $tmp | Out-Null
        if ($r.Code -ne 0) { throw 'docker export failed' }
        Rename-Item -LiteralPath "$tar.part" -NewName (Split-Path -Leaf $tar)
    }
    $distro = "wiz8-bench-$label"
    $disk = Join-Path $wslRoot $label
    Write-Host "Importing the WSL sandbox $distro"
    $r = Invoke-WslQuiet --import $distro $disk $tar --version 2
    if ($r.Code -ne 0) { throw "wsl --import failed ($($r.Code)): $($r.Text)" }
    $wsl = @('-d', $distro, '-u', 'root', '-e', '/opt/bench/sandbox.sh', $Game,
             $(if ($usePatch) { $Patch } else { '-' }), $out) + $opts
    Write-Host "wsl $($wsl -join ' ')"
    $ErrorActionPreference = 'Continue'   # bench.sh messages on stderr are not errors here
    try {
        & wsl.exe @wsl
        $code = $LASTEXITCODE
    } finally {
        Invoke-WslQuiet --terminate $distro | Out-Null
        Invoke-WslQuiet --unregister $distro | Out-Null
        if (Test-Path -LiteralPath $disk) { Remove-Item -LiteralPath $disk -Recurse -Force }
    }
} else {
    $run = @('run', '--rm', '--init', '--name', "wiz8-bench-$label", '--network', 'none',
             '--memory', $Memory, '--cpus', $Cpus, '--pids-limit', '4096', '--shm-size', '512m',
             '--security-opt', 'no-new-privileges', '--cap-drop', 'ALL',
             '--mount', "type=bind,source=$Game,target=/game,readonly")
    if ($usePatch) { $run += @('--mount', "type=bind,source=$Patch,target=/patch,readonly") }
    # the GPU: WSL's device and its user-mode driver libraries (paths in Docker Desktop's VM)
    if ($Gpu) { $run += @('--device', '/dev/dxg', '--mount', 'type=bind,source=/usr/lib/wsl,target=/usr/lib/wsl,readonly') }
    $run += @('--mount', "type=bind,source=$out,target=/out", $Image) + $opts

    Write-Host "docker $($run -join ' ')"
    $ErrorActionPreference = 'Continue'   # bench.sh and docker messages on stderr are not errors here
    & docker @run
    $code = $LASTEXITCODE
}
$summary = Join-Path $out 'summary.txt'
if (Test-Path -LiteralPath $summary) { Write-Host ''; Get-Content -LiteralPath $summary | Write-Host }
Write-Host ''
Write-Host "Output: $out"
exit $code
