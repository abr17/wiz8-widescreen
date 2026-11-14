#!/bin/bash
# The WSL sandbox (linux_bench.ps1 -Show): runs bench.sh in a throw-away WSL2 distro made from
# the bench image, with the bench's screen as a window on the Windows desktop (WSLg). Started as
# root by linux_bench.ps1, which imports the distro before and deletes it after the run:
#   wsl -d <distro> -u root -e /opt/bench/sandbox.sh <game> <patch|-> <out> [bench.sh options]
# <game>, <patch>, <out>: Windows folders (C:\...), mounted at /game and /patch (read-only) and
# /out, in a mount namespace of this script's own, so the mounts end with it. Nothing else of
# Windows is mounted and Windows programs cannot be started (wsl.conf). bench.sh then runs as
# the bench user (uid 1000), without new privileges, in a network namespace of its own (only an
# unconfigured loopback: no network).
set -euo pipefail
die() { echo "sandbox.sh: $*" >&2; exit 1; }
[ "$(id -u)" = 0 ] || die "run as root (wsl -u root)"
[ $# -ge 3 ] || die "usage: sandbox.sh <game> <patch|-> <out> [bench.sh options]"
if [ -z "${WIZ8_SANDBOX_NS:-}" ]; then
    exec env WIZ8_SANDBOX_NS=1 unshare --mount --propagation private -- "$0" "$@"
fi
game=$1 patch=$2 out=$3
shift 3

x0=/mnt/wslg/.X11-unix/X0
[ -S "$x0" ] || die "no WSLg display ($x0 is missing): WSLg needs Windows 11 or WSL from the Microsoft Store"

# the three folders (drvfs: Windows files; its mount helper is WSL's /init)
[ -e /sbin/mount.drvfs ] || ln -s /init /sbin/mount.drvfs
drvfs() { mount -t drvfs "$1" "$2" -o "$3" || die "mounting $1 at $2 failed"; }
drvfs "$game" /game ro
[ "$patch" = - ] || drvfs "$patch" /patch ro
drvfs "$out" /out uid=1000,gid=1000

# X: bench.sh opens its window on WSLg's display :0 and runs its own X server :1 in it. WSLg's
# /tmp/.X11-unix is read-only, so this namespace gets its own, with WSLg's X0 linked in.
if mountpoint -q /tmp/.X11-unix; then umount -l /tmp/.X11-unix; fi
if [ -L /tmp/.X11-unix ]; then rm -f /tmp/.X11-unix; fi
mkdir -p /tmp/.X11-unix
mount -t tmpfs -o mode=1777 tmpfs /tmp/.X11-unix
ln -s "$x0" /tmp/.X11-unix/X0

exec unshare --net -- setpriv --reuid=1000 --regid=1000 --init-groups --no-new-privs --reset-env \
    env DISPLAY=:0 LANG=C.UTF-8 LC_ALL=C.UTF-8 /opt/bench/bench.sh --show=yes "$@"
