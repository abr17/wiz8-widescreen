#!/bin/bash
# Makes the clean Wine and Proton prefixes of the bench image; run once by the Dockerfile as
# the bench user. bench.sh copies them to a fresh folder for every run.
#   bake.sh
# /home/bench/baked/wine       WINEPREFIX for Ubuntu's Wine (64-bit, as a plain `wine` makes it)
# /home/bench/baked/proton     STEAM_COMPAT_DATA_PATH for GE-Proton (pfx/ + Proton's own files)
# /home/bench/baked/image.txt  versions, printed at the top of every summary.txt
# /home/bench/steam            empty STEAM_COMPAT_CLIENT_INSTALL_PATH (there is no Steam client)
# Wine copies its own DLLs into a new prefix (1.3 GB for Ubuntu's Wine); copies identical to
# the runner's files are turned into symlinks to them, as Proton itself does, so a prefix
# takes little space and copies in seconds. The prefixes are made under /tmp/bake (a tmpfs in
# the Dockerfile, so the full-size copies never reach the disk) and moved to $baked after.
set -euo pipefail
baked=/home/bench/baked
work=/tmp/bake/bench   # Wine wants a parent folder that belongs to the user
mkdir -p "$baked" "$work/proton" /home/bench/steam

# link_identical <prefix> <runner dir>...: replaces prefix files with symlinks to identical runner files
link_identical() {
    python3 -I - "$@" <<'EOF'
import filecmp, os, sys
prefix, dirs = sys.argv[1], sys.argv[2:]
index = {}
for d in dirs:
    for root, _, files in os.walk(d):
        for f in files:
            p = os.path.join(root, f)
            if os.path.isfile(p) and not os.path.islink(p):
                index.setdefault((f.lower(), os.path.getsize(p)), []).append(p)
linked = saved = 0
for root, _, files in os.walk(os.path.join(prefix, 'drive_c')):
    for f in files:
        p = os.path.join(root, f)
        if os.path.islink(p) or not os.path.isfile(p):
            continue
        size = os.path.getsize(p)
        for cand in index.get((f.lower(), size), []):
            if filecmp.cmp(p, cand, shallow=False):
                os.remove(p)
                os.symlink(cand, p)
                linked += 1
                saved += size
                break
print('%s: %d files linked to the runner, %d MB saved' % (prefix, linked, saved >> 20))
EOF
}

rm -f /tmp/.X90-lock
Xvfb :90 -screen 0 1024x768x24 -nolisten tcp >/tmp/bake-xvfb.log 2>&1 &
xvfb=$!
export DISPLAY=:90
for _ in $(seq 50); do xdotool getdisplaygeometry >/dev/null 2>&1 && break; sleep 0.2; done

# Wine: Mono and Gecko are not installed (the game needs neither; without network their
# install prompts would block the build); no menu entries.
start=$(date +%s)
WINEPREFIX="$work/wine" WINEDEBUG=-all WINEDLLOVERRIDES='mscoree,mshtml=;winemenubuilder.exe=d' \
    wineboot --init
WINEPREFIX="$work/wine" wineserver -w
test -f "$work/wine/user.reg"
link_identical "$work/wine" /usr/lib/x86_64-linux-gnu/wine /usr/lib/i386-linux-gnu/wine /usr/share/wine
echo "wine prefix: $(( $(date +%s) - start )) s, $(du -sh "$work/wine" | cut -f1)"

# Proton: the first start copies its default prefix and runs wineboot (takes minutes).
start=$(date +%s)
STEAM_COMPAT_DATA_PATH="$work/proton" STEAM_COMPAT_CLIENT_INSTALL_PATH=/home/bench/steam \
    UMU_ID=umu-default WINEDEBUG=-all \
    python3 /opt/proton/proton waitforexitandrun 'C:\windows\system32\cmd.exe' /c exit 0
WINEPREFIX="$work/proton/pfx" /opt/proton/files/bin/wineserver -w
test -f "$work/proton/pfx/user.reg"
link_identical "$work/proton/pfx" /opt/proton/files/lib /opt/proton/files/share
echo "proton prefix: $(( $(date +%s) - start )) s, $(du -sh "$work/proton" | cut -f1)"

kill "$xvfb"; wait "$xvfb" 2>/dev/null || true
cp -a "$work/wine" "$work/proton" "$baked/"
rm -rf "${work:?}"/* /home/bench/.cache /tmp/bake-xvfb.log
echo "baked: $(du -sh "$baked/wine" | cut -f1) wine, $(du -sh "$baked/proton" | cut -f1) proton"

{
    echo "image: wiz8-linux-bench, built $(date -u +%Y-%m-%d)"
    echo "wine: $(wine --version)"
    echo "proton: $(cut -d' ' -f2 /opt/proton/version)"
    echo "mesa: $(dpkg-query -W -f='${Version}' mesa-vulkan-drivers:amd64)"
} >"$baked/image.txt"
