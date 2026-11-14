#!/bin/bash
# Isolated Linux bench: starts Wiz8.exe under Wine or Proton in a fresh prefix, takes
# screenshots and collects the patch's logs. Entry point of the bench image (Dockerfile next to
# this file); on Windows start it with linux_bench.ps1 (docs/testing.md, "Linux / Proton bench").
#   bench.sh [--runner proton|wine] [--overrides 'version=n,b'] [--install files|setup|none]
#            [--desktop 1280x800|none] [--wait 30] [--actions /out/actions.txt] [--canvas 768]
#            [--timeout 300] [--winedebug +seh] [--env NAME=VALUE]... [--gpu yes|no] [--show yes|no]
#            [--hold yes|no] [--then 'version=n,b'|none] [--uninstall yes|no]
#            [--global-override NAME=ORDER]... [--setup-prefix same|other]
#            [--launcher none|shortcut|heroic|lutris] [--ini Section.Key=Value]...
#            [--load /out/save.SAV]
# Every option also takes the form --option=value (--overrides= for an empty value).
# Mounts: /game  the game folder (read-only; the bench works on a copy),
#         /patch the package: Wiz8WideSetup.exe + files\ (read-only; not needed for --install none
#                without --uninstall),
#         /out   results: summary.txt, screenshots, logs.
#   --runner     proton = GE-Proton10-25 (default), wine = Ubuntu's Wine 9.0
#   --overrides  WINEDLLOVERRIDES for the game (default version=n,b: the patch with Wine's own
#                ddraw, the route the installer sets up; version=n,b;ddraw=n,b tries a DDraw.dll
#                in the game folder: none in the package since 1.0.3, dgVoodoo's before);
#                empty = not set, as for a player who did not set it (the patch then does not load)
#   --install    files = copy /patch/files into the game copy (default; names match in any
#                letter case, as on Windows);
#                setup = run Wiz8WideSetup.exe --install in the same prefix the game then uses
#                (or in another one, --setup-prefix; its registry overrides land there; message
#                boxes are answered: 'y' says Yes to a Yes/No box, Return closes an OK box);
#                none = the game copy as mounted
#   --desktop    size of the Wine virtual desktop, which is the game's screen (default 1280x800);
#                none = no virtual desktop: the game on a bare X screen of 1280x800 (none:1920x1080
#                for another size), as on a Linux desktop
#   --wait       seconds from the game start to the first screenshot, start.png (default 30)
#   --actions    file of steps run after start.png, one per line ('#' starts a comment;
#                CRLF, a BOM and UTF-16 are fine):
#                  sleep S | shot NAME | key KEYS (xdotool names: Escape, Return, ctrl+s) |
#                  click X Y, rclick X Y (desktop pixels) |
#                  click640 X Y, rclick640 X Y (the game's 640x480 coordinates on the wide
#                  canvas, as Click640 in docs/testing.md; in full screen under Wine inside the
#                  picture that wiz8wide.log names, "scaled into WxH at (X,Y)", not the whole screen,
#                  until a later "[Display] output:" line says the game left it)
#   --canvas     canvas width for click640 (default: W= from wiz8wide.log, else 640)
#   --timeout    seconds allowed for the installer and for the game run, --wait and actions
#                included (default 300)
#   --winedebug  extra WINEDEBUG channels (+pid,+loaddll are always on)
#   --env        extra environment variable for the runner, repeatable (PROTON_USE_WINED3D=1)
#   --gpu        yes = draw on the Windows GPU through WSL's /dev/dxg (with the WSL libraries
#                at /usr/lib/wsl): Mesa's d3d12 driver for OpenGL. Proton only, in its WoW64 mode
#                (PROTON_USE_WOW64=1): the WSL driver is 64-bit only, and WoW64 runs the 32-bit
#                game on the 64-bit libraries. No Vulkan on the GPU (Ubuntu's Mesa has no Vulkan
#                driver for it), so DXVK stays on lavapipe. Default no.
#   --show       yes = the bench's screen is a window (Xephyr) on the X display in $DISPLAY, the
#                Windows desktop in the WSL sandbox (sandbox.sh); no = an invisible Xvfb (default)
#   --hold       yes = after the actions, wait until the game is quit or the window is closed,
#                instead of stopping the game (needs --show yes; default no)
#   --then       a second start of the game after the first one, in the same prefix and game
#                copy, with this WINEDLLOVERRIDES (none or --then= = not set): does the patch now
#                start by itself (the setting it keeps in the prefix, the binkw32.dll route)? It
#                gets the same --wait, --actions, --timeout and --hold; the earlier start's logs
#                are taken out of the game copy before it. Its files go to /out/start2/, its
#                summary lines end in "(start 2)". Repeatable: each further --then is one more
#                start (start3/, "(start 3)"; --then 'version=n,b' --then none = once with the
#                launch option, then once without it)
#   --uninstall  yes = after the last start, run Wiz8WideSetup.exe --uninstall in the installer's
#                prefix (--setup-prefix), then dump the registry again and compare the game copy
#                with the one before the install (default no)
#   --global-override  NAME=ORDER in HKCU\Software\Wine\DllOverrides of the game's prefix, as
#                winecfg or winetricks set it (ddraw=native), set before the installer and the
#                first start; repeatable, or several separated by commas
#   --setup-prefix  same = the installer runs in the game's prefix (default; as Protontricks,
#                Heroic's "Run EXE on Prefix" or Lutris' "Run EXE inside Wine prefix" run it);
#                other = in a second fresh prefix, as when it is started on its own (as another
#                non-Steam game, with plain wine); needs --install setup or --uninstall yes
#   --launcher   none = the game copy in the run folder (default); shortcut, heroic, lutris = a
#                fake home folder (the runner's HOME, which Wine passes on as WINEHOMEDIR) with
#                that launcher's files for a GOG game, the game copy and its prefix where that
#                launcher keeps them, and the game started as it starts it (by its Linux path,
#                with its environment); home.txt lists the files:
#                  shortcut  Steam with the game as a non-Steam game: ~/.local/share/Steam with
#                            userdata/12345678/config/shortcuts.vdf (Exe "~/Games/gog/Wizardry
#                            8/Wiz8.exe"), the prefix steamapps/compatdata/<shortcut id>/pfx
#                            (only C: and Z:); Proton with Steam's variables (SteamGameId of the
#                            shortcut), but UMU_ID set and empty: that skips Proton's steam.exe,
#                            which waits for a Steam client, and maps no further drives
#                  heroic    ~/.config/heroic: gog_store/installed.json (~/Games/Heroic/Wizardry 8)
#                            and GamesConfig/1207659230.json (winePrefix ~/Games/Heroic/Prefixes/
#                            default/Wizardry 8); Proton as umu starts it (UMU_ID=umu-245450, the
#                            prefix folder is also the compat folder: pfx is a link to itself)
#                  lutris    ~/.local/share/lutris/games/wizardry-8-1729000000.yml (exe, prefix,
#                            working_dir): the prefix ~/Games/wizardry-8 with the game in its
#                            drive_c/GOG Games/Wizardry 8, as Lutris' GOG installer puts it;
#                            Proton as umu starts it
#                The installer always gets the folder as Z:\... (every prefix has Z:).
#   --ini        Section.Key=Value written into the game copy's ini files after the install,
#                before the first start; repeatable, or several separated by commas
#                (Display.Mode=fullscreen,Display.ScreenWidth=1024). The file: the one whose
#                [Section] has the key (also as a ';Key=' comment; wiz8wide.ini if both do),
#                else the one that has the section, else wiz8ws.ini for [General] and [Hybrid]
#                (the loader's settings, read by version.dll) and wiz8wide.ini for any other
#                (read by wiz8hy.dll). A missing key, section or file is added.
#   --load       a save file: it is copied into the game copy as Saves/Quick 1.SAV and the game
#                is started with /LOAD, which loads the newest quick save right at the start: no
#                intro and no main menu, straight into the 3D world (at every start of the run)
# Output in /out: summary.txt (one line per check), *.png, wiz8ws.log / wiz8hy.log /
# wiz8wide.log / Wiz8Wide.installed.txt when the game wrote them, srDD_D3D11.log (the log of
# the patch's render driver, from the game copy's Dll folder), loaddll.txt (the loader lines
# of the game process for version/binkw32/binkw32_wiz8wide/ddraw/d3dimm/sr/wiz8hy.dll),
# appdefaults.reg (the prefix's HKCU\Software\Wine\AppDefaults\Wiz8.exe key after the start),
# wiz8wide.reg (HKCU\Software\Wiz8Wide, the notes of the installer and the patch, then that
# AppDefaults key), runner.log (Wine stderr or the Proton log), setup-runner.log, actions.log
# (each step with its time since the game start), xserver.log (Xvfb's or Xephyr's output),
# game-added.txt (files the install added); with --then start2/ (the same for the second start;
# start3/ ... for more),
# with --uninstall uninstall-runner.log, uninstall-NN.png and uninstall/ (the registry after it,
# game-diff.txt: + added, - missing, ~ changed against the copy before the install), with
# --setup-prefix other setup-prefix/ (that prefix's registry after the install), with
# --launcher home.txt, with --ini the ini files it changed.
# Exit code: 0 = the run finished and summary.txt is complete, whatever the game did
# ("patch loaded: no" is a result); 1 = bad arguments or mounts; 2 = a bench step failed.
set -uo pipefail

runner=proton
overrides='version=n,b'
install=files
desktop=1280x800
wait_s=30
actions=
canvas=
timeout_s=300
winedebug_extra=
extra_env=()
gpu=no
show=no
hold=no
then_list=()     # the WINEDLLOVERRIDES of each start after the first one
uninstall=no
global_overrides=()
setup_prefix=same
launcher=none
ini_entries=()
load=
host_display=${DISPLAY:-}

usage() { sed -n '2,/^set -uo/p' "$0" | sed '$d' | sed 's/^# \{0,1\}//'; }
die_usage() { echo "bench.sh: $*" >&2; echo "run bench.sh --help for the options" >&2; exit 1; }
# split_list <value> <entry start>: one entry per line, split at each comma followed by the
# start of an entry (NAME= or Section.Key=), so a comma inside a value (n,b) stays
split_list() { printf '%s\n' "$1" | sed -E "s/,($2)/\n\1/g"; }

while [ $# -gt 0 ]; do
    case "$1" in
        -h|--help) usage; exit 0 ;;
        --*=*) opt=${1%%=*}; val=${1#*=}; shift ;;
        --*) opt=$1; [ $# -ge 2 ] || die_usage "$1 needs a value"; val=$2; shift 2 ;;
        *) die_usage "unknown argument: $1" ;;
    esac
    case "$opt" in
        --runner) runner=$val ;;
        --overrides) overrides=$val ;;
        --install) install=$val ;;
        --desktop) desktop=$val ;;
        --wait) wait_s=$val ;;
        --actions) actions=$val ;;
        --canvas) canvas=$val ;;
        --timeout) timeout_s=$val ;;
        --winedebug) winedebug_extra=$val ;;
        --env) extra_env+=("$val") ;;
        --gpu) gpu=$val ;;
        --show) show=$val ;;
        --hold) hold=$val ;;
        --then) [ "$val" = none ] && val=; then_list+=("$val") ;;
        --uninstall) uninstall=$val ;;
        --global-override)
            while IFS= read -r e; do global_overrides+=("$e"); done < <(split_list "$val" '[A-Za-z0-9_.*-]+=') ;;
        --setup-prefix) setup_prefix=$val ;;
        --launcher) launcher=$val ;;
        --ini)
            while IFS= read -r e; do ini_entries+=("$e"); done < <(split_list "$val" '[A-Za-z0-9_]+\.[A-Za-z0-9_]+=') ;;
        --load) load=$val ;;
        *) die_usage "unknown option: $opt" ;;
    esac
done

case "$runner" in wine|proton) ;; *) die_usage "--runner must be wine or proton" ;; esac
case "$install" in none|files|setup) ;; *) die_usage "--install must be none, files or setup" ;; esac
# the X screen, and whether the game gets a Wine virtual desktop of that size on it
if [[ "$desktop" =~ ^none(:([0-9]{3,4}x[0-9]{3,4}))?$ ]]; then
    vdesk=no
    screen=${BASH_REMATCH[2]:-1280x800}
elif [[ "$desktop" =~ ^[0-9]{3,4}x[0-9]{3,4}$ ]]; then
    vdesk=yes
    screen=$desktop
else
    die_usage "--desktop must look like 1280x800, or be none (none:1920x1080)"
fi
[[ "$wait_s" =~ ^[0-9]+$ ]] || die_usage "--wait must be a number of seconds"
[[ "$timeout_s" =~ ^[0-9]+$ ]] || die_usage "--timeout must be a number of seconds"
[ -z "$canvas" ] || [[ "$canvas" =~ ^[0-9]+$ ]] || die_usage "--canvas must be a number"
case "$gpu" in yes|no) ;; *) die_usage "--gpu must be yes or no" ;; esac
case "$show" in yes|no) ;; *) die_usage "--show must be yes or no" ;; esac
case "$hold" in yes|no) ;; *) die_usage "--hold must be yes or no" ;; esac
[ "$hold" = no ] || [ "$show" = yes ] || die_usage "--hold needs --show yes"
[ "$show" = no ] || [ -n "$host_display" ] || die_usage "--show: DISPLAY is not set (the display to open the window on)"
if [ "$gpu" = yes ]; then
    [ "$runner" = proton ] || die_usage "--gpu needs --runner proton (Ubuntu's Wine 9.0 has no WoW64 mode for the 64-bit GPU driver)"
    [ -e /dev/dxg ] || die_usage "--gpu: /dev/dxg not found (in Docker: --device /dev/dxg)"
    [ -f /usr/lib/wsl/lib/libd3d12.so ] || die_usage "--gpu: /usr/lib/wsl/lib/libd3d12.so not found (in Docker: mount /usr/lib/wsl)"
fi
for e in "${extra_env[@]}"; do
    [[ "$e" =~ ^[A-Za-z_][A-Za-z0-9_]*= ]] || die_usage "--env must be NAME=VALUE: $e"
done
case "$uninstall" in yes|no) ;; *) die_usage "--uninstall must be yes or no" ;; esac
for e in "${global_overrides[@]}"; do
    [[ "$e" =~ ^[A-Za-z0-9_.*-]+=[A-Za-z,]*$ ]] || die_usage "--global-override must be NAME=ORDER (ddraw=native): $e"
done
case "$setup_prefix" in same|other) ;; *) die_usage "--setup-prefix must be same or other" ;; esac
[ "$setup_prefix" = same ] || [ "$install" = setup ] || [ "$uninstall" = yes ] \
    || die_usage "--setup-prefix other needs --install setup or --uninstall yes (it is where the installer runs)"
case "$launcher" in none|shortcut|heroic|lutris) ;; *) die_usage "--launcher must be none, shortcut, heroic or lutris" ;; esac
for e in "${ini_entries[@]}"; do
    [[ "$e" =~ ^[A-Za-z0-9_]+\.[A-Za-z0-9_]+= && "$e" != *$'\r'* ]] || die_usage "--ini must be Section.Key=Value: $e"
done
[ -z "$load" ] || [ -f "$load" ] || die_usage "--load: no such file: $load"
[ -f /game/Wiz8.exe ] || die_usage "/game/Wiz8.exe not found (mount the game folder at /game)"
[ "$install" = none ] || [ -d /patch/files ] || die_usage "/patch/files not found (mount the package at /patch)"
[ "$install" != setup ] && [ "$uninstall" = no ] || [ -f /patch/Wiz8WideSetup.exe ] \
    || die_usage "/patch/Wiz8WideSetup.exe not found"
[ -z "$actions" ] || [ -f "$actions" ] || die_usage "actions file not found: $actions"
if [ -n "$actions" ]; then
    # a file made on Windows has CRLF line ends, maybe a UTF-8 BOM, or is UTF-16 (Windows
    # PowerShell's '>'): the steps are read from a plain LF copy
    if [ "$(head -c2 "$actions" | od -An -tx1 | tr -d ' \n')" = fffe ]; then
        iconv -f UTF-16 -t UTF-8 "$actions"
    else
        cat "$actions"
    fi | sed -e 's/\r$//' -e '1s/^\xEF\xBB\xBF//' >/tmp/bench-actions.txt \
        || die_usage "cannot read the actions file: $actions"
    actions=/tmp/bench-actions.txt
    n=0
    while IFS= read -r line || [ -n "$line" ]; do
        n=$((n + 1))
        line=${line%%#*}
        read -r cmd a b _ <<<"$line"
        num='^-?[0-9]+$'
        case "${cmd:-}" in
            '') ;;
            sleep) [[ "${a:-}" =~ ^[0-9]+(\.[0-9]+)?$ ]] || die_usage "actions line $n: sleep needs seconds" ;;
            shot) [[ "${a:-}" =~ ^[A-Za-z0-9_.-]+$ ]] || die_usage "actions line $n: shot needs a name (letters, digits, _ . -)" ;;
            key) [ -n "${a:-}" ] || die_usage "actions line $n: key needs a key name" ;;
            click|rclick|click640|rclick640)
                [[ "${a:-}" =~ $num && "${b:-}" =~ $num ]] || die_usage "actions line $n: $cmd needs x y" ;;
            *) die_usage "actions line $n: unknown step '$cmd'" ;;
        esac
    done <"$actions"
fi
touch /out/.write-test 2>/dev/null && rm -f /out/.write-test || die_usage "/out is not writable"

# ---------------- state, summary ----------------
out=/out
baked=/home/bench/baked
run=$(mktemp -d /home/bench/run.XXXXXX)
# the game copy: in the run folder, or with --launcher where that launcher keeps a GOG game,
# under a fake home folder (the prefixes are placed in step 1)
home=
case "$launcher" in
    none) game="$run/game" ;;
    shortcut) home="$run/home"; game="$home/Games/gog/Wizardry 8" ;;
    heroic) home="$run/home"; game="$home/Games/Heroic/Wizardry 8" ;;
    lutris) home="$run/home"; game="$home/Games/wizardry-8/drive_c/GOG Games/Wizardry 8" ;;
esac
game_win="Z:${game//\//\\}"
declare -A S
keys=()
shots=()
shot_dir=$out    # where shot puts its pictures, and their names in summary.txt
shot_rel=
od=$out          # the current start's output folder and summary suffix (start_game)
sfx=
result=ok
game_pid=
xvfb_pid=
t0=$EPOCHREALTIME

sum() { [ -n "${S[$1]+x}" ] || keys+=("$1"); S[$1]=$2; }
us() { local t=${1//[.,]/}; echo $((10#$t)); }            # $EPOCHREALTIME -> microseconds
since() { echo $(( $(us "$EPOCHREALTIME") - $(us "$1") )); }  # microseconds since a mark
elapsed() { local d; d=$(since "$1"); printf '%d.%d' $((d / 1000000)) $((d / 100000 % 10)); }
note() { echo "[bench $(elapsed "$t0") s] $*"; }
fail() { result="bench error: $*"; note "ERROR: $*"; exit 2; }

finish() {
    local code=$?
    [ -n "$game_pid" ] && kill -0 "$game_pid" 2>/dev/null && stop_wine
    [ -n "$xvfb_pid" ] && kill "$xvfb_pid" 2>/dev/null
    [ -s "$run/xvfb.log" ] && cp "$run/xvfb.log" "$out/xserver.log"
    [ "$code" -ne 0 ] && [ "$result" = ok ] && result="bench error: exit code $code"
    # the checks first (each start's, the uninstall's), then how the run was set up
    local per_start=("patch loaded" "started from" "wine settings" "loaddll version.dll"
                     "loaddll binkw32.dll" "loaddll binkw32_wiz8wide.dll" "loaddll ddraw.dll"
                     "loaddll d3dimm.dll" "loaddll wiz8hy.dll" "loaddll" "render driver"
                     "fullscreen picture"
                     "registry AppDefaults\\Wiz8.exe" "registry Wiz8Wide" "overrides requested"
                     "overrides effective")
    local per_end=("game exit" "actions" "hold" "timeout") k n
    local first=("${per_start[@]}" "install" "game copy after install"
                 "registry AppDefaults\\Wiz8.exe (setup prefix)" "registry Wiz8Wide (setup prefix)"
                 "${per_end[@]}")
    for n in $(seq 2 $(( ${#then_list[@]} + 1 ))); do
        for k in "${per_start[@]}" "${per_end[@]}"; do first+=("$k (start $n)"); done
    done
    first+=("uninstall" "game copy after uninstall" "registry AppDefaults\\Wiz8.exe (after uninstall)"
            "registry Wiz8Wide (after uninstall)" "registry AppDefaults\\Wiz8.exe (setup prefix, after uninstall)"
            "registry Wiz8Wide (setup prefix, after uninstall)")
    local -A listed
    for k in "${first[@]}"; do listed[$k]=1; done
    {
        cat "$baked/image.txt" 2>/dev/null
        for k in "${first[@]}"; do [ -n "${S[$k]+x}" ] && echo "$k: ${S[$k]}"; done
        echo "screenshots: ${#shots[@]}${shots:+ (${shots[*]})}"
        for k in "${keys[@]}"; do [ -n "${listed[$k]+x}" ] || echo "$k: ${S[$k]}"; done
        echo "bench time: $(elapsed "$t0") s"
        echo "result: $result"
    } >"$out/summary.txt"
    rm -rf "$run"
    exit "$code"
}
trap finish EXIT
trap 'result="bench error: stopped by a signal"; exit 2' INT TERM

# ---------------- runner ----------------
# Wine: Ubuntu's wine with its own prefix. Proton: the proton script with a compat folder
# (its prefix is compat/pfx); the reg/wineserver calls use Proton's own wine binaries.
# The game's prefix and, with --setup-prefix other, the installer's are placed in step 1;
# $prefix (and with Proton $compat) is the one the runner calls use now (use_prefix).
proton_dir=/opt/proton
if [ "$runner" = wine ]; then
    wineserver_bin=/usr/bin/wineserver
    wine_bin=/usr/bin/wine
else
    wineserver_bin="$proton_dir/files/bin/wineserver"
    wine_bin="$proton_dir/files/bin/wine64"
fi
prefix=
compat=
game_prefix=
game_compat=
setup_wprefix=
setup_compat=
winedebug="+pid,+loaddll${winedebug_extra:+,${winedebug_extra#,}}"
# the launcher's environment for every runner call (step 1 sets it for --launcher), the start's
# own (WINEDLLOVERRIDES), and the game id Proton names its log after
launch_env=()
start_env=()
wait_server=no
steam_game_id=12345
[ "$runner" = proton ] && launch_env=(STEAM_COMPAT_CLIENT_INSTALL_PATH=/home/bench/steam UMU_ID=umu-default SteamGameId=12345)

use_prefix() {  # use_prefix game|setup
    if [ "$1" = setup ] && [ "$setup_prefix" = other ]; then
        prefix=$setup_wprefix compat=$setup_compat
    else
        prefix=$game_prefix compat=$game_compat
    fi
}

stop_wine() {
    [ -n "$prefix" ] || return
    WINEPREFIX="$prefix" "$wineserver_bin" -k 2>/dev/null
    if [ -n "$game_pid" ]; then
        for _ in $(seq 100); do kill -0 "$game_pid" 2>/dev/null || break; sleep 0.2; done
        kill -9 "$game_pid" 2>/dev/null
    fi
    WINEPREFIX="$prefix" timeout 30 "$wineserver_bin" -w 2>/dev/null
}

# run_exe <log> <windows exe path> [args...]: starts an exe with the runner in the current
# prefix, in the background (pid in $bg_pid), current folder = the exe's folder for the game
run_exe() {
    local log=$1 logdir; shift
    if [ "$runner" = wine ]; then
        env WINEPREFIX="$prefix" WINEDEBUG="$winedebug" "${launch_env[@]}" "${extra_env[@]}" "${start_env[@]}" \
            "$wine_bin" "$@" >"$log" 2>&1 &
        bg_pid=$!
        return
    fi
    logdir="$run/proton-log.$(basename "$log")"
    mkdir -p "$logdir"
    local proton_env=(STEAM_COMPAT_DATA_PATH="$compat" "${launch_env[@]}" PROTON_LOG=1 PROTON_LOG_DIR="$logdir"
                      WINEDEBUG="$winedebug" "${extra_env[@]}" "${start_env[@]}")
    if [ "$wait_server" = no ]; then
        env "${proton_env[@]}" python3 "$proton_dir/proton" waitforexitandrun "$@" >"$log.launcher" 2>&1 &
    else
        # a program given by its Linux path is started through start.exe, which returns at once:
        # this waits until the prefix's last program has ended, as umu and Steam wait for the game
        # shellcheck disable=SC2016 # a script for bash -c, its values come as arguments
        env "${proton_env[@]}" bash -c 'proton=$1 server=$2 pfx=$3; shift 3
                python3 "$proton" waitforexitandrun "$@"; rc=$?; WINEPREFIX="$pfx" "$server" -w; exit $rc' \
            bench "$proton_dir/proton" "$wineserver_bin" "$prefix" "$@" >"$log.launcher" 2>&1 &
    fi
    bg_pid=$!
}

# collect_runner_log <log>: for Proton, puts its log (and the launcher's output) into <log>
collect_runner_log() {
    local log=$1
    if [ "$runner" = proton ]; then
        local logdir="$run/proton-log.$(basename "$log")"
        cat "$logdir/steam-$steam_game_id.log" "$log.launcher" >"$log" 2>/dev/null
    fi
}

# copy_prefix <wine prefix> <Proton compat folder> [umu]: a fresh copy of the baked prefix there;
# umu = laid out as umu (Heroic, Lutris) keeps it: the compat folder is the prefix itself, its
# pfx a link to the folder
copy_prefix() {
    if [ "$runner" = wine ]; then
        mkdir -p "$1" && cp -a "$baked/wine/." "$1/" || return 1
    elif [ "${3:-}" = umu ]; then
        mkdir -p "$2" && cp -a "$baked/proton/pfx/." "$2/" \
            && find "$baked/proton" -mindepth 1 -maxdepth 1 ! -name pfx -exec cp -a {} "$2/" \; \
            && ln -s . "$2/pfx" || return 1
    else
        mkdir -p "$2" && cp -a "$baked/proton/." "$2/" || return 1
    fi
    # Steam's prefixes have no x: drive (the baked Proton prefix has one, mapped by umu)
    [ "$launcher" != shortcut ] || rm -f "$1/dosdevices/x:"
}

# ---------------- screen, input ----------------
export DISPLAY=:1
dw=${screen%x*}
dh=${screen#*x}

shot() {
    local name=${1//[^A-Za-z0-9_.-]/_}
    if xwd -root -silent >"$run/shot.xwd" 2>/dev/null && convert "xwd:$run/shot.xwd" "$shot_dir/$name.png" 2>/dev/null; then
        shots+=("$shot_rel$name.png")
        return 0
    fi
    note "screenshot $name failed"
    return 1
}

click_at() {  # click_at <button> <x> <y>
    xdotool mousemove "$2" "$3"; sleep 0.25
    xdotool mousedown "$1"; sleep 0.08; xdotool mouseup "$1"
}

canvas_width() {
    if [ -n "$canvas" ]; then echo "$canvas"; return; fi
    local w
    w=$(grep -aoE '(^|[^A-Za-z])W=[0-9]+' "$game/wiz8wide.log" 2>/dev/null | tail -1 | grep -oE '[0-9]+$')
    echo "${w:-640}"
}

# the game's picture on the screen, "x y w h": in full screen under Wine the rectangle
# wiz8wide.log names ("[Display] fullscreen ... scaled into WxH at (X,Y) of the ... window"; the
# window covers the screen from its top left corner), otherwise the whole screen. The hybrid logs
# a line at every open of the output ("[Display] output: borderless, no scaling" or "... window,
# no scaling" for the others), so only the last of those lines counts: after a switch back to
# borderless or window in Options the picture is the whole screen again.
picture_rect() {
    local r
    r=$(grep -aoE 'scaled into [0-9]+x[0-9]+ at \(-?[0-9]+,-?[0-9]+\) of the [0-9]+x[0-9]+ window|\[Display\] output: ' \
            "$game/wiz8wide.log" 2>/dev/null | tail -1 \
        | sed -nE 's/^scaled into ([0-9]+)x([0-9]+) at \((-?[0-9]+),(-?[0-9]+)\).*/\3 \4 \1 \2/p')
    echo "${r:-0 0 $dw $dh}"
}

# one axis of a canvas pixel on the screen, as CanvasAxisToScreen in Canvas.cpp: the screen
# pixel at its middle if the game maps that pixel back to it, else the first one inside it (a
# screen pixel wider than half a canvas pixel can start in the canvas pixel before)
axis_to_screen() {  # axis_to_screen <canvas pixel> <canvas extent> <screen extent>
    local s=$(( (2 * $1 + 1) * $3 / (2 * $2) ))
    (( $1 < 0 || s * $2 / $3 == $1 )) || s=$(( ($1 * $3 + $2 - 1) / $2 ))
    echo "$s"
}

# a canvas pixel on the screen, as To-Screen 'canvas' in scripts/play/game.ps1
# (CanvasCanvasToScreen in Canvas.cpp), inside the picture
to_screen() {  # to_screen <x640> <y640> -> "sx sy W picture"
    local W ox sx sy px py pw ph pic=
    W=$(canvas_width)
    ox=$(( (W - 640) / 2 ))
    read -r px py pw ph <<<"$(picture_rect)"
    [ "$px $py $pw $ph" = "0 0 $dw $dh" ] || pic="${pw}x${ph}+${px}+${py}"
    sx=$(( px + $(axis_to_screen $(( $1 + ox )) "$W" "$pw") ))
    sy=$(( py + $(axis_to_screen "$2" 480 "$ph") ))
    (( sx < 0 )) && sx=0; (( sx >= dw )) && sx=$((dw - 1))
    (( sy < 0 )) && sy=0; (( sy >= dh )) && sy=$((dh - 1))
    echo "$sx $sy $W $pic"
}

time_left() { (( $(since "$game_t0") < timeout_s * 1000000 )); }

# alog <text>: a line of actions.log, with the time the step started (since the game start)
alog() { printf '[%6s s] %s\n' "$step_t" "$*" >>"$od/actions.log"; }

run_actions() {
    local n=0 total line cmd a b c sx sy W pic left step step_t
    total=$(sed 's/#.*//' "$actions" | grep -c '[^[:space:]]')
    : >"$od/actions.log"
    while IFS= read -r line || [ -n "$line" ]; do
        line=${line%%#*}
        cmd= a= b= c=
        read -r cmd a b c <<<"$line"
        [ -z "$cmd" ] && continue
        step="$cmd${a:+ $a}${b:+ $b}${c:+ $c}"
        step_t=$(elapsed "$game_t0")
        if ! kill -0 "$game_pid" 2>/dev/null; then   # the rest would only see an empty screen
            game_gone="seen at $step_t s, before step $((n + 1)): $step"
            alog "the game has exited: steps $((n + 1))-$total not run"
            sum "actions$sfx" "$n of $total done, the game exited before step $((n + 1)) ($step)"
            return
        fi
        if ! time_left; then
            sum "actions$sfx" "$n of $total done, stopped by --timeout $timeout_s"
            timed_out=yes
            return
        fi
        n=$((n + 1))
        case "$cmd" in
            sleep) # not past --timeout
                   left=$(( (timeout_s * 1000000 - $(since "$game_t0")) / 1000000 ))
                   if (( ${a%.*} >= left )); then
                       sleep "$left"
                       alog "sleep $a: cut to $left s by --timeout"
                       sum "actions$sfx" "$n of $total done, stopped by --timeout $timeout_s"
                       timed_out=yes
                       return
                   fi
                   sleep "$a" ;;
            shot) shot "$a" ;;
            key) xdotool key --delay 80 $a $b $c ;;
            click|rclick)
                click_at "$([ "$cmd" = click ] && echo 1 || echo 3)" "$a" "$b"
                alog "$cmd $a $b"; continue ;;
            click640|rclick640)
                read -r sx sy W pic <<<"$(to_screen "$a" "$b")"
                click_at "$([ "$cmd" = click640 ] && echo 1 || echo 3)" "$sx" "$sy"
                alog "$cmd $a $b -> desktop $sx $sy (canvas W=$W, desktop ${dw}x${dh}${pic:+, full screen picture $pic})"
                continue ;;
        esac
        alog "$step"
    done <"$actions"
    sum "actions$sfx" "$n of $total done"
}

# ---------------- registry ----------------
# reg_keys <user.reg> <key>: that key and its subkeys from a prefix's user.reg; the key as
# user.reg writes it (Software\\Wiz8Wide), in any letter case
reg_keys() {
    REGKEY=$2 awk 'BEGIN { key = tolower(ENVIRON["REGKEY"]); p = 0 }
         /^\[/ { k = tolower($0); p = (index(k, "[" key "]") == 1 || index(k, "[" key "\\\\") == 1) }
         p' "$1"
}

# dump_registry <wine prefix> <out dir> <summary suffix>: appdefaults.reg (HKCU\Software\Wine\
# AppDefaults\Wiz8.exe: key names are not case-sensitive, wiz8.exe counts too) and wiz8wide.reg
# (HKCU\Software\Wiz8Wide, then the AppDefaults key again) from the prefix's user.reg, and their
# summary lines. Read after wineserver -w: the registry is saved when the prefix's last program ends.
dump_registry() {
    local reg="$1/user.reg" dir=$2 suffix=$3 vals
    mkdir -p "$dir"
    reg_keys "$reg" 'Software\\Wine\\AppDefaults\\Wiz8.exe' >"$dir/appdefaults.reg"
    if [ -s "$dir/appdefaults.reg" ]; then
        vals=$(grep -aE '^"[^"]+"="' "$dir/appdefaults.reg" | sed 's/^"\([^"]*\)"="\([^"]*\)"/\1=\2/' | paste -sd' ' -)
        sum "registry AppDefaults\\Wiz8.exe$suffix" "${vals:-key present, no values}"
    else
        echo "; HKCU\\Software\\Wine\\AppDefaults\\Wiz8.exe is not in this prefix" >"$dir/appdefaults.reg"
        sum "registry AppDefaults\\Wiz8.exe$suffix" "not present"
    fi
    { reg_keys "$reg" 'Software\\Wiz8Wide'; reg_keys "$reg" 'Software\\Wine\\AppDefaults\\Wiz8.exe'; } >"$dir/wiz8wide.reg"
    # per key below Software\Wiz8Wide: its values, name=data (data "" as the name alone)
    vals=$(python3 -I - "$dir/wiz8wide.reg" <<'EOF'
import re, sys
def plain(s): return re.sub(r'\\(.)', r'\1', s)
keys = []
for line in open(sys.argv[1], encoding='utf-8', errors='replace'):
    m = re.match(r'\[((?:[^\]\\]|\\.)*)\]', line)
    if m:
        name = plain(m.group(1))
        inside = name.lower().startswith('software\\wiz8wide')
        keys.append([name[len('Software\\Wiz8Wide\\'):] or 'Wiz8Wide', []] if inside else None)
        continue
    m = re.match(r'"((?:[^"\\]|\\.)*)"="((?:[^"\\]|\\.)*)"', line)
    if m and keys and keys[-1]:
        name, data = plain(m.group(1)), plain(m.group(2))
        keys[-1][1].append(('"%s"' % name if ' ' in name else name) + ('=' + data if data else ''))
found = [k for k in keys if k]
print('; '.join('%s: %s' % (k, ' '.join(v)) for k, v in found if v)
      or ('key present, no values' if found else 'not present'))
EOF
    )
    sum "registry Wiz8Wide$suffix" "${vals:-not readable}"
}

# ---------------- the installer ----------------
# screen_sig: a signature of the pixels on the screen now (an xwd dump itself differs from one
# call to the next); empty while it shows only the empty desktop (one colour)
screen_sig() {
    local colours sig
    xwd -root -silent >"$run/setup.xwd" 2>/dev/null || return
    read -r colours sig <<<"$(convert "xwd:$run/setup.xwd" -format '%k %#' info: 2>/dev/null)"
    [ "${colours:-1}" = 1 ] || echo "$sig"
}

# run_setup <install|uninstall> <name>: Wiz8WideSetup.exe --<action> <game folder> in the
# installer's prefix (--setup-prefix); its screens are <name>-NN.png, its log <name>-runner.log.
# Sets setup_rc, setup_boxes and setup_time.
run_setup() {
    local action=$1 name=$2 t pic last='' try setup_pid
    note "running Wiz8WideSetup.exe --$action $game_win"
    t=$EPOCHREALTIME
    use_prefix setup
    start_env=()
    cd "$run" || fail "cannot enter $run"
    run_exe "$run/$name-runner.log" 'Z:\patch\Wiz8WideSetup.exe' "--$action" "$game_win"
    setup_pid=$bg_pid
    game_pid=$setup_pid
    setup_boxes=0
    # The installer shows only message boxes. A box gets 'y' (Yes on a Yes/No box, whose
    # default button is No) until the screen changes, up to 4 times; a box that 'y' does
    # not close is an OK box and then gets Return. Escape is never sent: Wine answers a
    # Yes/No box with Cancel on Escape, and Return there would pick the default No.
    while kill -0 "$setup_pid" 2>/dev/null; do
        sleep 1
        (( $(since "$t") < timeout_s * 1000000 )) \
            || { stop_wine; fail "the installer did not finish in $timeout_s s"; }
        [ -n "$(screen_sig)" ] || continue
        sleep 1                     # a new box takes the keyboard focus
        pic=$(screen_sig)
        [ -n "$pic" ] || continue
        if [ "$pic" != "$last" ]; then
            last=$pic
            setup_boxes=$((setup_boxes + 1))
            (( setup_boxes <= 20 )) && shot "$name-$(printf %02d "$setup_boxes")"
        fi
        for try in 1 2 3 4 5; do
            xdotool key "$([ "$try" -lt 5 ] && echo y || echo Return)"
            sleep 1
            kill -0 "$setup_pid" 2>/dev/null || break 2
            [ "$(screen_sig)" != "$pic" ] && break
        done
    done
    wait "$setup_pid"; setup_rc=$?
    game_pid=
    WINEPREFIX="$prefix" timeout 60 "$wineserver_bin" -w
    collect_runner_log "$run/$name-runner.log"
    cp "$run/$name-runner.log" "$out/$name-runner.log" 2>/dev/null
    setup_time=$(elapsed "$t")
}

# hash_files: every file of the game copy with its SHA-256 (for the comparison after --uninstall)
hash_files() { (cd "$game" && find . -type f -print0 | sort -z | xargs -0 -r sha256sum); }

# ---------------- 1. fresh copies ----------------
note "copying the game"
t=$EPOCHREALTIME
mkdir -p "$game"
cp -r --preserve=timestamps /game/. "$game/" || fail "copying /game failed"
chmod -R u+w "$game"
# logs of earlier sessions (a game folder used on Windows has them): only this run's logs count
find "$game" -maxdepth 1 -type f \( -iname wiz8ws.log -o -iname wiz8hy.log -o -iname wiz8wide.log \) -delete
find "$game" -maxdepth 2 -type f -ipath '*/dll/srdd_d3d11.log*' -delete
sum "game copy" "$(find "$game" -type f | wc -l) files, $(du -sh "$game" | cut -f1), $(elapsed "$t") s"
# --load: the save as the game's first quick save; /LOAD at the start then loads it
game_args=()
if [ -n "$load" ]; then
    saves=$(find "$game" -maxdepth 1 -type d -iname saves | head -1)
    [ -n "$saves" ] || { saves="$game/Saves"; mkdir -p "$saves"; }
    cp "$load" "$saves/Quick 1.SAV" || fail "copying the save failed"
    game_args=(/LOAD)
    sum "save" "$(basename "$load") as ${saves##*/}/Quick 1.SAV; the game is started with /LOAD"
fi

# the launcher's files in the fake home, pointing at the game copy, and where its prefix goes
# (Proton's compat folder; with plain Wine the prefix itself, or the compat folder's pfx for Steam)
place=
case "$launcher" in
    heroic) place="$home/Games/Heroic/Prefixes/default/Wizardry 8" ;;
    lutris) place="$home/Games/wizardry-8" ;;
esac
if [ "$launcher" != none ]; then
    ids=$(python3 -I - "$launcher" "$home" "$game" "$place" "$runner" "$out/home.txt" <<'EOF'
import json, os, struct, sys, zlib
launcher, home, game, place, runner, listing = sys.argv[1:7]
lines = []
def write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'wb' if isinstance(data, bytes) else 'w') as f:
        f.write(data)
    lines.append('~' + path[len(home):] + (':' if isinstance(data, str) else ' (binary)'))
    if isinstance(data, str):
        lines.extend('    ' + line for line in data.splitlines())
if launcher == 'shortcut':
    # Steam: its folder (and its own links to it), the library list, the non-Steam game
    steam = home + '/.local/share/Steam'
    os.makedirs(home + '/.steam', exist_ok=True)
    for name in ('steam', 'root'):
        os.symlink('../.local/share/Steam', home + '/.steam/' + name)
    write(steam + '/steamapps/libraryfolders.vdf', '"libraryfolders"\n{\n\t"0"\n\t{\n\t\t"path"\t\t"%s"\n'
          '\t\t"label"\t\t""\n\t\t"apps"\n\t\t{\n\t\t}\n\t}\n}\n' % steam)
    # shortcuts.vdf in Steam's binary format: 00 = a block, 01 = text, 02 = 32-bit number, 08 = end
    exe, name = '"%s/Wiz8.exe"' % game, 'Wizardry 8'
    def text(k, v): return b'\x01' + k.encode() + b'\0' + v.encode() + b'\0'
    def number(k, v): return b'\x02' + k.encode() + b'\0' + struct.pack('<i', v)
    # the shortcut's id as Steam makes it: CRC-32 of Exe (with its quotes) and the name, top
    # bit set; stored as a signed number; its prefix is compatdata/<id as unsigned>
    sid = zlib.crc32((exe + name).encode()) | 0x80000000
    fields = [number('appid', sid - (1 << 32)), text('AppName', name), text('Exe', exe),
              text('StartDir', '"%s/"' % game), text('icon', ''), text('ShortcutPath', ''),
              text('LaunchOptions', ''), number('IsHidden', 0), number('AllowDesktopConfig', 1),
              number('AllowOverlay', 1), number('OpenVR', 0), number('Devkit', 0),
              text('DevkitGameID', ''), number('DevkitOverrideAppID', 0), number('LastPlayTime', 0),
              text('FlatpakAppID', '')]
    data = b'\x00shortcuts\0' + b'\x000\0' + b''.join(fields) + b'\x00tags\0\x08' + b'\x08' + b'\x08\x08'
    write(steam + '/userdata/12345678/config/shortcuts.vdf', data)
    lines.append('    shortcut 0: appid %d (compatdata %d), AppName "%s", Exe %s, StartDir "%s/"'
                 % (sid - (1 << 32), sid, name, exe, game))
    # the id, and SteamGameId as Steam sets it for a non-Steam game (its 64-bit game id)
    print(sid, (sid << 32) | 0x02000000)
elif launcher == 'heroic':
    config = home + '/.config/heroic'
    write(config + '/gog_store/installed.json', json.dumps({'installed': [{
        'platform': 'windows', 'executable': '', 'install_path': game, 'install_size': '846 MiB',
        'is_dlc': False, 'version': '1.2.4', 'appName': '1207659230', 'installedWithDLCs': False,
        'language': 'en-US', 'versionEtag': '', 'buildId': ''}]}, indent=2) + '\n')
    wine = ({'bin': '/opt/proton/proton', 'name': 'Proton - GE-Proton10-25', 'type': 'proton'}
            if runner == 'proton' else {'bin': '/usr/bin/wine', 'name': 'Wine Default', 'type': 'wine'})
    write(config + '/GamesConfig/1207659230.json', json.dumps({'1207659230': {
        'winePrefix': place, 'wineVersion': wine, 'autoInstallDxvk': False, 'autoInstallVkd3d': False,
        'language': ''}, 'version': 'v0', 'explicit': True}, indent=2) + '\n')
elif launcher == 'lutris':
    def quoted(s): return "'" + s.replace("'", "''") + "'"   # YAML's single-quoted form
    write(home + '/.local/share/lutris/games/wizardry-8-1729000000.yml',
          'game:\n  exe: %s\n  prefix: %s\n  working_dir: %s\nsystem: {}\nwine:\n  version: %s\n'
          % (quoted(game + '/Wiz8.exe'), quoted(place), quoted(game),
             'ge-proton' if runner == 'proton' else 'system'))
with open(listing, 'w') as f:
    f.write('fake home ~ = %s (HOME of the runner; Wine passes it on as WINEHOMEDIR)\n' % home)
    f.write('game copy: ~%s\n' % game[len(home):])
    f.write('\n'.join(lines) + '\n')
EOF
    ) || fail "writing the $launcher files failed"
fi
case "$launcher" in
    shortcut)
        read -r shortcut_id steam_game_id <<<"$ids"
        place="$home/.local/share/Steam/steamapps/compatdata/$shortcut_id"
        sum "launcher" "shortcut (Steam, the game as the non-Steam game \"Wizardry 8\", id $shortcut_id; game ~/Games/gog/Wizardry 8, prefix ~/.local/share/Steam/steamapps/compatdata/$shortcut_id/pfx; ~ = $home, home.txt)"
        launch_env=(HOME="$home")
        [ "$runner" = proton ] && launch_env+=(STEAM_COMPAT_CLIENT_INSTALL_PATH="$home/.local/share/Steam"
            SteamAppId=0 SteamGameId="$steam_game_id" STEAM_COMPAT_APP_ID=0 STEAM_COMPAT_INSTALL_PATH="$game"
            STEAM_COMPAT_LIBRARY_PATHS="$home/.local/share/Steam/steamapps" UMU_ID=)
        ;;
    heroic|lutris)
        if [ "$launcher" = heroic ]; then
            sum "launcher" "heroic (GOG game 1207659230; game ~/Games/Heroic/Wizardry 8, prefix ~/Games/Heroic/Prefixes/default/Wizardry 8; ~ = $home, home.txt)"
        else
            sum "launcher" "lutris (games/wizardry-8-1729000000.yml; prefix ~/Games/wizardry-8, game in its drive_c/GOG Games/Wizardry 8; ~ = $home, home.txt)"
        fi
        launch_env=(HOME="$home")
        steam_game_id=245450
        [ "$runner" = proton ] && launch_env+=(STEAM_COMPAT_CLIENT_INSTALL_PATH= UMU_ID=umu-245450 GAMEID=umu-245450
            STORE=gog SteamAppId=245450 SteamGameId=245450 STEAM_COMPAT_APP_ID=245450 STEAM_COMPAT_INSTALL_PATH="$game")
        ;;
esac
# the game: by its Windows path, or as the launchers start it, by its Linux path
game_exe="$game_win\\Wiz8.exe"
game_wait=no
if [ "$launcher" != none ]; then
    game_exe="$game/Wiz8.exe"
    [ "$runner" = proton ] && game_wait=yes   # see run_exe
fi

note "copying the baked $runner prefix"
t=$EPOCHREALTIME
layout=
case "$launcher" in
    none) place="$run/compat"; [ "$runner" = wine ] && place="$run/prefix" ;;
    heroic|lutris) layout=umu ;;
esac
if [ "$runner" = wine ]; then
    game_prefix=$place
    [ "$launcher" = shortcut ] && game_prefix="$place/pfx"
    copy_prefix "$game_prefix" || fail "copying the wine prefix failed"
else
    game_compat=$place
    game_prefix="$place/pfx"
    copy_prefix "$game_prefix" "$game_compat" "$layout" || fail "copying the proton prefix failed"
fi
if [ "$setup_prefix" = other ]; then
    # the installer's own fresh prefix, outside the launcher's places
    if [ "$runner" = wine ]; then
        setup_wprefix="$run/setup-prefix"
    else
        setup_compat="$run/setup-compat"
        setup_wprefix="$setup_compat/pfx"
    fi
    copy_prefix "$setup_wprefix" "$setup_compat" || fail "copying the installer's prefix failed"
fi
use_prefix game
sum "runner" "$runner, fresh prefix copied in $(elapsed "$t") s"
[ "$setup_prefix" = other ] && sum "setup prefix" "other (the installer runs in a second fresh prefix)"

# ---------------- 2. X server, virtual desktop ----------------
# :1 is the bench's screen: an invisible Xvfb, or with --show an Xephyr window on $host_display
# (the screenshots, clicks and keys go to :1 either way; a click into the window works too)
rm -f /tmp/.X1-lock /tmp/.X11-unix/X1
if [ "$show" = yes ]; then
    DISPLAY=$host_display Xephyr :1 -screen "${screen}x24" -title "Wizardry 8 bench" \
        -no-host-grab -nolisten tcp -noreset >"$run/xvfb.log" 2>&1 &
    xserver=Xephyr
else
    Xvfb :1 -screen 0 "${screen}x24" -nolisten tcp -noreset >"$run/xvfb.log" 2>&1 &
    xserver=Xvfb
fi
xvfb_pid=$!
for _ in $(seq 50); do xdotool getdisplaygeometry >/dev/null 2>&1 && break; sleep 0.2; done
xdotool getdisplaygeometry >/dev/null 2>&1 || fail "$xserver did not start ($(tail -1 "$run/xvfb.log"))"
xdotool mousemove $((dw / 2)) $((dh / 2))
# WSLg may place a new window partly off the screen (at -21,-21): move it to the top left
[ "$show" = no ] || DISPLAY=$host_display timeout 5 xdotool search --name '^Wizardry 8 bench$' \
    windowmove 32 32 >/dev/null 2>&1 || true

# the GPU: Mesa's d3d12 driver on WSL's /dev/dxg, for the 64-bit side Proton's WoW64 mode uses
gl_env=()
if [ "$gpu" = yes ]; then
    gl_env=("LD_LIBRARY_PATH=/usr/lib/wsl/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" GALLIUM_DRIVER=d3d12)
    extra_env+=("${gl_env[@]}" PROTON_USE_WOW64=1)
    sum "gpu" "yes (/dev/dxg, Mesa d3d12, PROTON_USE_WOW64=1)"
else
    sum "gpu" "no (Mesa software drivers)"
fi
renderer=$(env "${gl_env[@]}" timeout 30 glxinfo -B 2>/dev/null | sed -n 's/^OpenGL renderer string: //p')
sum "gl renderer" "${renderer:-unknown (glxinfo failed)} (64-bit glxinfo with the game's GL settings)"

# the game runs in a Wine virtual desktop: a bare Xvfb reports 0 Hz, which breaks DXVK and
# the game's display mode change. No taskbar in it (Ubuntu's Wine 9.0 shows one otherwise).
# --desktop none leaves it out; --global-override goes into the game's prefix with it.
# set_up_prefix <wine prefix> <with --global-override yes|no>
set_up_prefix() {
    {
        echo REGEDIT4
        if [ "$vdesk" = yes ]; then
            cat <<EOF

[HKEY_CURRENT_USER\\Software\\Wine\\Explorer]
"Desktop"="Default"

[HKEY_CURRENT_USER\\Software\\Wine\\Explorer\\Desktops]
"Default"="$desktop"

[HKEY_CURRENT_USER\\Software\\Wine\\Explorer\\Desktops\\Default]
"EnableShell"=dword:00000000
EOF
        fi
        if [ "$2" = yes ] && [ ${#global_overrides[@]} -gt 0 ]; then
            printf '\n[HKEY_CURRENT_USER\\Software\\Wine\\DllOverrides]\n'
            for e in "${global_overrides[@]}"; do printf '"%s"="%s"\n' "${e%%=*}" "${e#*=}"; done
        fi
    } >"$run/prefix.reg"
    [ "$(wc -l <"$run/prefix.reg")" -gt 1 ] || return 0
    local home_env=()
    [ -z "$home" ] || home_env=(HOME="$home")
    (cd "$run" && env WINEPREFIX="$1" WINEDEBUG=-all "${home_env[@]}" timeout 120 "$wine_bin" reg import prefix.reg \
        >"$run/reg.log" 2>&1) || return 1
    WINEPREFIX="$1" timeout 60 "$wineserver_bin" -w
}
set_up_prefix "$game_prefix" yes || fail "setting up the game's prefix failed ($(tail -1 "$run/reg.log"))"
if [ "$setup_prefix" = other ]; then
    set_up_prefix "$setup_wprefix" no || fail "setting up the installer's prefix failed ($(tail -1 "$run/reg.log"))"
fi
if [ "$vdesk" = yes ]; then
    sum "desktop" "$desktop (Wine virtual desktop$([ "$show" = yes ] && echo ", in a window on the Windows desktop"))"
else
    sum "desktop" "none (no Wine virtual desktop: a bare X screen of $screen$([ "$show" = yes ] && echo ", in a window on the Windows desktop"))"
fi
[ ${#global_overrides[@]} -eq 0 ] \
    || sum "global overrides" "${global_overrides[*]} (HKCU\\Software\\Wine\\DllOverrides of the game's prefix)"

# ---------------- 3. the patch ----------------
(cd "$game" && find . -type f | sort) >"$run/files-before.txt"
[ "$uninstall" = no ] || hash_files >"$run/hash-before.txt"
case "$install" in
    none)
        sum "install" "none (the game folder as mounted)" ;;
    files)
        # merged as on Windows: a folder or file that exists in another letter case (DATA\ for
        # Data\, ddraw.dll for DDraw.dll) is reused or replaced, not added as a second one
        merged=$(python3 -I - /patch/files "$game" <<'EOF'
import os, shutil, sys
src, dst = sys.argv[1], sys.argv[2]
def child(folder, name):
    names = {n.lower(): n for n in os.listdir(folder)}
    return os.path.join(folder, names.get(name.lower(), name))
copied = replaced = 0
for root, dirs, files in os.walk(src):
    dirs.sort()
    d = dst
    rel = os.path.relpath(root, src)
    for part in ([] if rel == '.' else rel.split(os.sep)):
        d = child(d, part)
        if not os.path.isdir(d):
            os.mkdir(d)
    for f in sorted(files):
        target = child(d, f)
        replaced += os.path.exists(target)
        shutil.copyfile(os.path.join(root, f), target)
        shutil.copystat(os.path.join(root, f), target)
        os.chmod(target, os.stat(target).st_mode | 0o200)
        copied += 1
print('%d files copied from /patch/files, %d of them replaced game files' % (copied, replaced))
EOF
        ) || fail "copying /patch/files failed"
        sum "install" "files ($merged)" ;;
    setup)
        run_setup install setup
        sum "install" "setup$([ "$setup_prefix" = other ] && echo " in the second prefix") (Wiz8WideSetup.exe --install, exit code $setup_rc, $setup_time s; $setup_boxes installer screen(s) answered, setup-NN.png)"
        [ "$setup_prefix" = same ] || dump_registry "$setup_wprefix" "$out/setup-prefix" " (setup prefix)"
        ;;
esac
use_prefix game
(cd "$game" && find . -type f | sort) >"$run/files-after.txt"
comm -13 "$run/files-before.txt" "$run/files-after.txt" | sed 's|^\./||' >"$out/game-added.txt"
sum "game copy after install" "$(wc -l <"$out/game-added.txt") files added (game-added.txt)"

# --ini: the settings in the game copy's wiz8ws.ini / wiz8wide.ini (the rules: see the top)
if [ ${#ini_entries[@]} -gt 0 ]; then
    done_ini=$(python3 -I - "$game" "$out" "${ini_entries[@]}" <<'EOF'
import os, re, shutil, sys
game, out, entries = sys.argv[1], sys.argv[2], sys.argv[3:]
names = {n.lower(): n for n in os.listdir(game)}
files = {}                                   # lower-case name -> [file name, lines or None]
for name in ('wiz8wide.ini', 'wiz8ws.ini'):
    real = names.get(name, name)
    path = os.path.join(game, real)
    lines = open(path, 'rb').read().decode('latin-1').splitlines(True) if os.path.isfile(path) else None
    files[name] = [real, lines]
def header(line):                           # the section name of a "[Section]" line
    m = re.match(r'\s*\[([^\]]*)\]', line)
    return m.group(1).strip() if m else None
def key_of(line, comments):                  # the key of a "Key=Value" line (lower case), or of ";Key=..."
    m = re.match(r'\s*(;\s*)?([^=;\[\s][^=]*?)\s*=', line)
    return m.group(2).lower() if m and (comments or not m.group(1)) else None
def section(lines, name):                    # (header line, end line) of a section, or None
    start = None
    for i, line in enumerate(lines or []):
        h = header(line)
        if h is not None:
            if start is not None:
                return start, i
            if h.lower() == name.lower():
                start = i
    return (start, len(lines)) if start is not None else None
def has_key(lines, sec, key):
    r = section(lines, sec)
    return bool(r) and any(key_of(line, True) == key.lower() for line in lines[r[0] + 1:r[1]])
reports, changed = [], []
for entry in entries:
    target, value = entry.split('=', 1)
    sec, key = target.split('.', 1)
    # which file (see the top of bench.sh)
    have = [n for n in ('wiz8wide.ini', 'wiz8ws.ini') if section(files[n][1], sec)]
    name = next((n for n in ('wiz8wide.ini', 'wiz8ws.ini') if has_key(files[n][1], sec, key)), None) \
        or (have[0] if len(have) == 1 else None) \
        or ('wiz8ws.ini' if sec.lower() in ('general', 'hybrid') else 'wiz8wide.ini')
    real, lines = files[name]
    what = ''
    if lines is None:
        lines, what = [], ', new file'
    eol = '\r\n' if any(l.endswith('\r\n') for l in lines) or not lines else '\n'
    r = section(lines, sec)
    if r is None:                            # a new section at the end
        if lines and not lines[-1].endswith('\n'):
            lines[-1] += eol
        if lines and lines[-1].strip():
            lines.append(eol)
        lines += ['[%s]%s' % (sec, eol), '%s=%s%s' % (key, value, eol)]
        report = '(added, new section%s)' % what
    else:
        sec = header(lines[r[0]])
        body = range(r[0] + 1, r[1])
        active = [i for i in body if key_of(lines[i], False) == key.lower()]
        if active:                           # the value replaced (the first one, which Windows reads)
            i = active[0]
            old = lines[i].split('=', 1)[1].rstrip('\r\n')
            line_eol = lines[i][len(lines[i].rstrip('\r\n')):] or eol
            lines[i] = lines[i].split('=', 1)[0] + '=' + value + line_eol
            report = '(was %s)' % old.strip()
        else:                                # added after its ';Key=' comment, or at the section's end
            comment = [i for i in body if key_of(lines[i], True) == key.lower()]
            filled = [i for i in body if lines[i].strip()]
            at = comment[0] + 1 if comment else (filled[-1] + 1 if filled else r[0] + 1)
            if not lines[at - 1].endswith('\n'):
                lines[at - 1] += eol
            lines.insert(at, '%s=%s%s' % (key, value, eol))
            report = '(added%s)' % what
    files[name][1] = lines
    reports.append('%s [%s] %s=%s %s' % (real, sec, key, value, report))
    if real not in changed:
        changed.append(real)
for name, (real, lines) in files.items():
    if real in changed:
        open(os.path.join(game, real), 'wb').write(''.join(lines).encode('latin-1'))
        shutil.copyfile(os.path.join(game, real), os.path.join(out, real))
print('; '.join(reports))
EOF
    ) || fail "writing the ini files failed"
    sum "ini" "$done_ini (the changed files are copied to /out)"
fi

# ---------------- 4. the game, 5. results ----------------
# the environment the game process really got (Proton adds its own WINEDLLOVERRIDES after
# it writes its log header): the first process with Wiz8.exe on its command line that is not
# the Python launcher (or run_exe's bash around it)
envwatch='
import os, sys, time
out, end = sys.argv[1], time.time() + float(sys.argv[2])
while time.time() < end:
    for pid in os.listdir("/proc"):
        try:
            cmd = open("/proc/%s/cmdline" % pid, "rb").read().split(b"\0")
            name = os.path.basename(cmd[0]).lower()
            if b"python" not in name and name not in (b"bash", b"env") and any(b"wiz8.exe" in a.lower() for a in cmd):
                env = open("/proc/%s/environ" % pid, "rb").read()
                open(out, "wb").write(env.replace(b"\0", b"\n"))
                sys.exit(0)
        except (OSError, ValueError):
            pass
    time.sleep(0.05)
'

dll_kind() {  # in load order: "native", "builtin", "native, then builtin" or "not loaded"
    local kinds
    kinds=$(grep -aiE "\\\\$1\" at " "$od/loaddll.txt" | grep -aoE '(native|builtin)$' \
            | awk '!seen[$0]++' | paste -sd, - | sed 's/,/, then /g')
    echo "${kinds:-not loaded}"
}

# start_game <n> <WINEDLLOVERRIDES or empty>: one start of the game in its prefix and what it
# did; the files of start 1 go to /out, of a later one to /out/start<n>/, and its summary lines
# end in " (start <n>)"
start_game() {
    local n=$1 ovr=$2 rc eff gpid state f text mode
    od=$out sfx='' shot_dir=$out shot_rel=''
    if [ "$n" -gt 1 ]; then
        od="$out/start$n" sfx=" (start $n)" shot_dir="$out/start$n" shot_rel="start$n/"
        mkdir -p "$od"
    fi
    use_prefix game
    start_env=()
    if [ -n "$ovr" ]; then
        start_env=("WINEDLLOVERRIDES=$ovr")
        sum "overrides requested$sfx" "WINEDLLOVERRIDES=$ovr"
    else
        sum "overrides requested$sfx" "none (WINEDLLOVERRIDES not set)"
    fi
    note "starting the game ($runner${sfx})"
    cd "$game" || fail "cannot enter the game copy"
    timed_out=no
    game_gone=
    game_t0=$EPOCHREALTIME
    wait_server=$game_wait
    run_exe "$run/runner$n.log" "$game_exe" "${game_args[@]}"
    wait_server=no
    game_pid=$bg_pid
    python3 -I -c "$envwatch" "$run/game$n.environ" "$timeout_s" &
    envwatch_pid=$!

    for _ in $(seq $((wait_s * 5))); do
        kill -0 "$game_pid" 2>/dev/null || break
        time_left || { timed_out=yes; break; }   # --wait longer than --timeout
        sleep 0.2
    done
    shot start
    [ -n "$actions" ] && run_actions
    [ -z "$actions" ] && sum "actions$sfx" "none"
    if [ "$hold" = yes ] && kill -0 "$game_pid" 2>/dev/null; then
        note "holding: quit the game or close the bench window to end the run"
        t=$EPOCHREALTIME
        while kill -0 "$game_pid" 2>/dev/null && kill -0 "$xvfb_pid" 2>/dev/null; do sleep 1; done
        sum "hold$sfx" "$(elapsed "$t") s, until $(kill -0 "$xvfb_pid" 2>/dev/null && echo "the game exited" || echo "the window was closed")"
    fi

    if kill -0 "$game_pid" 2>/dev/null; then
        note "stopping the game"
        stop_wine
        wait "$game_pid" 2>/dev/null
        sum "game exit$sfx" "still running after $(elapsed "$game_t0") s, stopped by the bench"
    else
        wait "$game_pid"; rc=$?
        sum "game exit$sfx" "exited by itself with code $rc${game_gone:+ ($game_gone)}"
        WINEPREFIX="$prefix" timeout 60 "$wineserver_bin" -w
    fi
    game_pid=
    kill "$envwatch_pid" 2>/dev/null
    [ "$timed_out" = yes ] && sum "timeout$sfx" "yes (--timeout $timeout_s)"

    collect_runner_log "$run/runner$n.log"
    cp "$run/runner$n.log" "$od/runner.log"
    for f in wiz8ws.log wiz8hy.log wiz8wide.log Wiz8Wide.installed.txt; do
        [ -f "$game/$f" ] && cp "$game/$f" "$od/"
    done
    # the patch's render driver (Dll/srDD_D3D11.dll, since 1.0.3) writes its log next to itself:
    # the device it got, where its shaders came from (embedded, or compiled at run time on
    # Wine's own Direct3D 11), and its error lines
    dlog=$(find "$game" -maxdepth 2 -type f -ipath '*/dll/srdd_d3d11.log' | head -1)
    if [ -n "$dlog" ]; then
        cp "$dlog" "$od/srDD_D3D11.log"
        # whatever else the driver was asked to write next to itself (srDD_D3D11.ini's debug
        # outputs: RT dumps, the seam log, D7S captures) and its ini, files under 200 MB
        find "$(dirname "$dlog")" -maxdepth 1 -type f -iname 'srdd_d3d11*' ! -iname '*.dll' ! -iname 'srdd_d3d11.log' \
            -size -200M -exec cp -t "$od/" {} + 2>/dev/null || true
        dev=$(grep -a 'device: driver type' "$dlog" | tail -1 | tr -d '\r' | sed -E 's/^.*device: driver type //; s/, x87.*$//')
        ready=$(grep -a 'shaders ready in' "$dlog" | tail -1 | tr -d '\r' | sed -E 's/^.*L2: back end //; s/ \(.*\)//')
        if grep -aq 'compiled at run time first' "$dlog"; then src="HLSL compiled at run time (Wine's own Direct3D 11)"; else src="embedded shaders"; fi
        errs=$(grep -acE ' error: |device lost|hardware device failed|swap chain creation failed|shaders failed|not compiled at run time' "$dlog")
        sum "render driver$sfx" "srDD_D3D11: ${dev:-no device line}; $src; ${ready:-no \"shaders ready\" line}; error lines: $errs"
    elif [ -n "$(find "$game" -maxdepth 2 -type f -ipath '*/dll/srdd_d3d11.dll' | head -1)" ]; then
        sum "render driver$sfx" "no Dll/srDD_D3D11.log: the game did not load the patch's Direct3D 11 driver"
    fi

    # effective WINEDLLOVERRIDES: what the game process got (Proton appends its own entries)
    if [ -s "$run/game$n.environ" ]; then
        eff=$(grep -a '^WINEDLLOVERRIDES=' "$run/game$n.environ" | head -1 | cut -d= -f2-)
        sum "overrides effective$sfx" "${eff:-(not set)} (environment of the game process)"
    else
        sum "overrides effective$sfx" "(not captured: the game process was not seen)"
    fi

    # loader lines of the game process (the one that loaded Wiz8.exe); a +timestamp channel puts
    # "  5.123:" before Wine's pid:tid:
    sed -E 's/^ *[0-9]+\.[0-9]{3}://' "$run/runner$n.log" >"$run/runner.untimed.log"
    gpid=$(grep -a 'trace:loaddll:.*Loaded L".*\\Wiz8\.exe"' "$run/runner.untimed.log" | head -1 | cut -d: -f1)
    if [ -n "$gpid" ]; then
        grep -a "^$gpid:[0-9a-f]*:trace:loaddll:" "$run/runner.untimed.log" \
            | grep -aiE '\\(wiz8\.exe|version\.dll|binkw32\.dll|binkw32_wiz8wide\.dll|ddraw\.dll|d3dimm\.dll|sr\.dll|wiz8hy\.dll)"' \
            >"$od/loaddll.txt"
    else
        : >"$od/loaddll.txt"
    fi
    if [ -z "$gpid" ]; then
        sum "loaddll$sfx" "no loader line for Wiz8.exe in runner.log (the game did not start)"
    else
        sum "loaddll version.dll$sfx" "$(dll_kind version.dll)"
        sum "loaddll binkw32.dll$sfx" "$(dll_kind binkw32.dll)"
        # the original binkw32.dll under its new name (the binkw32.dll route), when the copy has it
        if [ -n "$(find "$game" -maxdepth 1 -iname binkw32_wiz8wide.dll)" ] || grep -aqi 'binkw32_wiz8wide' "$od/loaddll.txt"; then
            sum "loaddll binkw32_wiz8wide.dll$sfx" "$(dll_kind binkw32_wiz8wide.dll)"
        fi
        sum "loaddll ddraw.dll$sfx" "$(dll_kind ddraw.dll)"
        sum "loaddll d3dimm.dll$sfx" "$(dll_kind d3dimm.dll)"
        sum "loaddll wiz8hy.dll$sfx" "$(dll_kind wiz8hy.dll)"
    fi

    # the patch: it writes wiz8ws.log when it starts (from version.dll, or under Wine from
    # binkw32.dll); which copy started it, and what it did with its own Wine setting
    if [ -f "$od/wiz8ws.log" ]; then
        state=$(grep -aoE 'hooks installed: [a-z]+|patch inactive \([^)]*\)|wiz8hy.dll: -?[0-9]+ functions replaced|ddraw\.dll is [^;]*$' \
                "$od/wiz8ws.log" | tr -d '\r' | paste -sd';' - | sed 's/;/; /g')
        sum "patch loaded$sfx" "yes (wiz8ws.log written${state:+: $state})"
        text=$(grep -ao 'started from binkw32\.dll.*' "$od/wiz8ws.log" | tr -d '\r' | head -1)
        if [ -n "$text" ]; then
            sum "started from$sfx" "${text#started from }"
        else
            text=$(grep -aoE 'loaded as [A-Za-z0-9_.]+ proxy' "$od/wiz8ws.log" | head -1 | sed -E 's/^loaded as (.*) proxy$/\1/')
            f=$(grep -ao 'binkw32\.dll: a copy of the patch, forwarding only.*' "$od/wiz8ws.log" | tr -d '\r' | head -1)
            sum "started from$sfx" "${text:-unknown (no header line in wiz8ws.log)}${f:+; $f}"
        fi
        # "wine settings (HKCU\...\DllOverrides): <what>; <result>", then any further line
        # about the game folder's entry in HKCU\Software\Wiz8Wide\Wine\Folders
        text=$(grep -ao 'wine settings (HKCU[^)]*): .*' "$od/wiz8ws.log" | tr -d '\r' | tail -1 | sed 's/^wine settings ([^)]*): //')
        f=$(grep -ao 'wine settings: .*' "$od/wiz8ws.log" | tr -d '\r' | sed 's/^wine settings: //' | paste -sd'|' - | sed 's/|/ | /g')
        if [ -n "$text$f" ]; then
            sum "wine settings$sfx" "${text:-(no main line)}${f:+ | $f}"
        else
            sum "wine settings$sfx" "no \"wine settings\" line in wiz8ws.log (a patch that keeps no Wine setting)"
        fi
    else
        sum "patch loaded$sfx" "no (no wiz8ws.log)"
    fi

    # full screen under Wine: the picture the hybrid draws into (wiz8wide.log), which click640
    # also used; shown when the log has a full screen line or the ini asks for full screen
    text=$(grep -ao '\[Display\] fullscreen .*' "$od/wiz8wide.log" 2>/dev/null | tr -d '\r' | tail -1)
    mode=$({ tr -d '\r' <"$game/wiz8wide.ini"; } 2>/dev/null | awk -F= '
        /^[[:space:]]*\[/ { display = (tolower($0) ~ /^[[:space:]]*\[display\]/) }
        display && tolower($1) ~ /^[[:space:]]*mode[[:space:]]*$/ { sub(/^[^=]*=[[:space:]]*/, ""); sub(/[[:space:]]+$/, ""); print; exit }')
    if [[ "$text" =~ fullscreen\ ([0-9]+x[0-9]+)[^:]*:.*scaled\ into\ ([0-9]+x[0-9]+)\ at\ \((-?[0-9]+,-?[0-9]+)\)\ of\ the\ ([0-9]+x[0-9]+)\ window ]]; then
        sum "fullscreen picture$sfx" "${BASH_REMATCH[1]} drawn, scaled into ${BASH_REMATCH[2]} at (${BASH_REMATCH[3]}) of the ${BASH_REMATCH[4]} window (click640 maps into it)"
    elif [ -n "$text" ]; then
        sum "fullscreen picture$sfx" "none: ${text#\[Display\] }"
    elif [ "${mode,,}" = fullscreen ]; then
        sum "fullscreen picture$sfx" "no [Display] fullscreen line in wiz8wide.log (wiz8wide.ini has Mode=fullscreen)"
    fi

    dump_registry "$prefix" "$od" "$sfx"
}

start_game 1 "$overrides"
n=1
for ovr in "${then_list[@]}"; do
    # only this start's logs count for it: the earlier start's are in /out already
    find "$game" -maxdepth 1 -type f \( -iname wiz8ws.log -o -iname wiz8hy.log -o -iname wiz8wide.log \) -delete
    find "$game" -maxdepth 2 -type f -ipath '*/dll/srdd_d3d11.log*' -delete
    n=$((n + 1))
    start_game "$n" "$ovr"
done
od=$out sfx='' shot_dir=$out shot_rel=''

# ---------------- 6. uninstall ----------------
if [ "$uninstall" = yes ]; then
    run_setup uninstall uninstall
    sum "uninstall" "Wiz8WideSetup.exe --uninstall$([ "$setup_prefix" = other ] && echo " in the second prefix"), exit code $setup_rc, $setup_time s; $setup_boxes installer screen(s) answered, uninstall-NN.png"
    mkdir -p "$out/uninstall"
    hash_files >"$run/hash-after.txt"
    python3 -I - "$run/hash-before.txt" "$run/hash-after.txt" >"$out/uninstall/game-diff.txt" <<'EOF'
import sys
def load(path):
    files = {}
    for line in open(path, encoding='utf-8', errors='replace'):
        digest, _, name = line.rstrip('\n').partition('  ')
        files[name[2:] if name.startswith('./') else name] = digest
    return files
before, after = load(sys.argv[1]), load(sys.argv[2])
for name in sorted(set(before) | set(after)):
    if name not in after:
        print('- ' + name)
    elif name not in before:
        print('+ ' + name)
    elif before[name] != after[name]:
        print('~ ' + name)
EOF
    n=$(wc -l <"$out/uninstall/game-diff.txt")
    if [ "$n" -eq 0 ]; then
        sum "game copy after uninstall" "the same as before the install (every file and its contents)"
    else
        sum "game copy after uninstall" "$n difference(s) from before the install: $(head -6 "$out/uninstall/game-diff.txt" | paste -sd'|' - | sed 's/|/, /g')$([ "$n" -gt 6 ] && echo ", ...") (uninstall/game-diff.txt)"
    fi
    use_prefix game
    dump_registry "$game_prefix" "$out/uninstall" " (after uninstall)"
    [ "$setup_prefix" = same ] || dump_registry "$setup_wprefix" "$out/uninstall/setup-prefix" " (setup prefix, after uninstall)"
fi
note "done: $out/summary.txt"
