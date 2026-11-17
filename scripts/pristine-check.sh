#!/usr/bin/env bash
# Pristine-install check: build a CLEAN Ubuntu 22.04 userland with debootstrap, copy this checkout into it, run the real
# setup script, the doctor, and every test that does not need the lab, and keep the log in results/pristine_install.txt.
# Usage: sudo bash scripts/pristine-check.sh        (about 15-30 minutes, needs internet and ~3 GB)
# What it proves: scripts/setup_ubuntu.sh installs everything from nothing and the code, tests and dashboard build work on it.
# What it cannot prove: the kernel is the host's (so the Open vSwitch kernel module and the Mininet lab are NOT re-tested
# here) and there is no systemd in a chroot. Run `sudo bin/flowguard start` on a real fresh machine for that.
# It never deletes the chroot (a tree that had bind mounts is dangerous to remove); to remove it later:
#   sudo umount -R /var/lib/flowguard-pristine/{proc,sys,dev} 2>/dev/null; then delete the folder by hand.
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ROOT="${PRISTINE_ROOT:-/var/lib/flowguard-pristine}"
LOG="$REPO/results/pristine_install.txt"
[ "$(id -u)" -eq 0 ] || { echo "run as root: sudo bash scripts/pristine-check.sh" >&2; exit 1; }
command -v debootstrap >/dev/null || { apt-get update -y && apt-get install -y debootstrap; }
mkdir -p "$REPO/results"
exec > >(tee "$LOG") 2>&1
echo "== pristine install check, $(date '+%Y-%m-%d %H:%M:%S'), host kernel $(uname -r)"

cleanup() {
  # stop anything started inside the chroot (package post-install scripts start daemons) so the mounts can be released
  for p in /proc/[0-9]*; do [ "$(readlink "$p/root" 2>/dev/null)" = "$ROOT" ] && kill "${p##*/}" 2>/dev/null; done; sleep 2
  # the mounts were made private/slave below, so unmounting them here cannot reach the host's own /proc, /sys or /dev
  for m in dev sys; do mountpoint -q "$ROOT/$m" && umount -R "$ROOT/$m" || true; done
  mountpoint -q "$ROOT/proc" && umount "$ROOT/proc" || true
  [ -e /dev/null ] && [ -d /proc/self ] || echo "WARNING: the host /dev or /proc looks affected; restart the distro (wsl --terminate)"
}
trap cleanup EXIT

if [ ! -f "$ROOT/etc/os-release" ]; then
  echo "== building a clean Ubuntu 22.04 (jammy) userland in $ROOT"
  debootstrap --variant=minbase --components=main,universe jammy "$ROOT" http://archive.ubuntu.com/ubuntu
fi
# a normal Ubuntu install has universe, updates and security enabled; reproduce that (idempotent)
cat > "$ROOT/etc/apt/sources.list" <<SRC
deb http://archive.ubuntu.com/ubuntu jammy main universe
deb http://archive.ubuntu.com/ubuntu jammy-updates main universe
deb http://security.ubuntu.com/ubuntu jammy-security main universe
SRC
grep PRETTY_NAME "$ROOT/etc/os-release"
mount -t proc proc "$ROOT/proc"
mount --make-rprivate "$ROOT/proc"
mount --rbind /sys "$ROOT/sys"
mount --make-rslave "$ROOT/sys"   # host changes may show up inside, but nothing done inside may reach the host
mount --rbind /dev "$ROOT/dev"
mount --make-rslave "$ROOT/dev"
cp /etc/resolv.conf "$ROOT/etc/resolv.conf"
# a chroot has no init system: never let package scripts start daemons in it
printf '#!/bin/sh
exit 101
' > "$ROOT/usr/sbin/policy-rc.d"; chmod +x "$ROOT/usr/sbin/policy-rc.d"
if [ -n "${PRISTINE_SEED_DEBS:-}" ]; then
  # optional: when a third-party package source (here the deadsnakes PPA on Launchpad) is down, reuse packages already
  # downloaded on the host. The log says so, because the result is then not a pure from-nothing install.
  echo "== NOTE: seeding the clean chroot's apt cache from $PRISTINE_SEED_DEBS (package source outage workaround)"
  mkdir -p "$ROOT/var/cache/apt/archives"
  cp -n "$PRISTINE_SEED_DEBS"/*.deb "$ROOT/var/cache/apt/archives/" 2>/dev/null || true
fi

echo "== copying the checkout (no venvs, no node_modules, no build output, no git history)"
mkdir -p "$ROOT/root/flowguard"
tar -C "$REPO" --exclude='.venv-*' --exclude=node_modules --exclude=web/dist --exclude=.git --exclude=.scratch --exclude=.impeccable -cf - . | tar -C "$ROOT/root/flowguard" -xf -

chroot "$ROOT" /bin/bash -lc '
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
echo "== step 1: minimal prerequisites the README tells a fresh laptop to install"
apt-get update -y
apt-get install -y --no-install-recommends ca-certificates curl gnupg git sudo
cd /root/flowguard
echo "== step 2: scripts/setup_ubuntu.sh"
bash scripts/setup_ubuntu.sh
echo "== step 3: bin/flowguard doctor (expected: lab-only checks may fail inside a chroot)"
bin/flowguard doctor --quick || true
echo "== step 4: tests that do not need the lab"
.venv-core/bin/python -m pytest tests/unit tests/api -q -p no:cacheprovider 2>&1 | tail -n 3
.venv-engine/bin/python -m pytest tests/unit tests/engine -q -p no:cacheprovider 2>&1 | tail -n 3
echo "== step 5: dashboard"
cd web && npm ci --no-fund --no-audit 2>&1 | tail -n 2 && npx vitest run 2>&1 | grep -E "Tests " && npm run -s build 2>&1 | tail -n 1
echo "== PRISTINE CHECK DONE"
'
