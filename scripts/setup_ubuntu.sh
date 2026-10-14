#!/usr/bin/env bash
# FlowGuard environment setup for Ubuntu 22.04 (native or WSL2). One script, both targets.
#
# What it does (idempotent, safe to re-run):
#   1. detects the environment (wsl | ubuntu)
#   2. installs apt packages: Open vSwitch, Mininet, build tools, Python 3.9 (deadsnakes), Node 20
#   3. starts the Open vSwitch daemons
#   4. creates .venv-engine (Python 3.9, pinned for Ryu 4.34) and .venv-core (system Python)
#   5. runs `flowguard doctor`
#
# Usage: scripts/setup_ubuntu.sh [--skip-apt] [--skip-node] [--skip-venv] [--help]
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SKIP_APT=0; SKIP_NODE=0; SKIP_VENV=0

# Pins that were verified to work together for Ryu 4.34 (see docs/spike_findings.md).
PIP_VERSION="23.3.2"
SETUPTOOLS_VERSION="58.0.0"

log()  { printf '\033[1;34m[setup]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[setup][warn]\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31m[setup][error]\033[0m %s\n' "$*" >&2; exit 1; }

usage() { sed -n '2,12p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0; }

for arg in "$@"; do
  case "$arg" in
    --skip-apt)  SKIP_APT=1 ;;
    --skip-node) SKIP_NODE=1 ;;
    --skip-venv) SKIP_VENV=1 ;;
    -h|--help)   usage ;;
    *) die "unknown option: $arg (try --help)" ;;
  esac
done

SUDO=""
if [ "$(id -u)" -ne 0 ]; then
  command -v sudo >/dev/null 2>&1 || die "not root and sudo is missing; re-run as root or install sudo"
  SUDO="sudo"
fi

detect_env() {
  if grep -qiE 'microsoft|wsl' /proc/version 2>/dev/null; then echo wsl; else echo ubuntu; fi
}

preflight() {
  FG_ENV="$(detect_env)"
  log "environment: ${FG_ENV}"
  [ -r /etc/os-release ] || die "/etc/os-release missing; this script targets Ubuntu 22.04"
  # shellcheck disable=SC1091
  . /etc/os-release
  [ "${ID:-}" = "ubuntu" ] || die "unsupported distro '${ID:-?}'; Ubuntu 22.04 is required"
  [ "${VERSION_ID:-}" = "22.04" ] || warn "Ubuntu ${VERSION_ID:-?} detected; only 22.04 is tested"
  command -v curl >/dev/null 2>&1 || { $SUDO apt-get update -y && $SUDO apt-get install -y curl; }
  curl -fsS -m 10 -o /dev/null https://pypi.org || warn "cannot reach pypi.org; package installs may fail"
}

install_apt() {
  log "installing apt packages"
  export DEBIAN_FRONTEND=noninteractive
  $SUDO apt-get update -y
  $SUDO apt-get install -y --no-install-recommends \
    ca-certificates curl gnupg git jq sqlite3 build-essential pkg-config \
    software-properties-common iproute2 iputils-ping net-tools tcpdump \
    openvswitch-switch openvswitch-common mininet iperf \
    python3 python3-venv python3-pip python3-dev libffi-dev libssl-dev

  if ! command -v python3.9 >/dev/null 2>&1; then
    add_deadsnakes
  fi
  $SUDO apt-get install -y python3.9 python3.9-venv python3.9-dev python3.9-distutils
}

# Add the deadsnakes PPA by hand. `add-apt-repository` needs api.launchpad.net, which is blocked on
# some networks (it timed out on the WSL2 dev machine); the PPA mirror and keyserver are enough.
add_deadsnakes() {
  local fpr="F23C5A6CF475977595C89F51BA6932366A755776" key=/etc/apt/keyrings/deadsnakes.gpg tmp
  log "adding deadsnakes PPA for Python 3.9 (needed by Ryu 4.34)"
  $SUDO mkdir -p /etc/apt/keyrings
  tmp="$(mktemp)"
  curl -fsSL "https://keyserver.ubuntu.com/pks/lookup?op=get&search=0x${fpr}" | gpg --dearmor --yes -o "$tmp"
  gpg --show-keys --with-colons "$tmp" | grep -q "^fpr:::::::::${fpr}:" \
    || die "deadsnakes key fingerprint mismatch (expected ${fpr}); refusing to trust it"
  $SUDO install -m 0644 "$tmp" "$key"; rm -f "$tmp"
  echo "deb [signed-by=${key}] https://ppa.launchpadcontent.net/deadsnakes/ppa/ubuntu jammy main" \
    | $SUDO tee /etc/apt/sources.list.d/deadsnakes.list >/dev/null
  $SUDO apt-get update -y
}

install_node() {
  if command -v node >/dev/null 2>&1 && node --version | grep -q '^v20\.'; then
    log "node $(node --version) already installed"; return
  fi
  log "installing Node.js 20 from the NodeSource apt repository (signed keyring)"
  $SUDO mkdir -p /etc/apt/keyrings
  curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key \
    | $SUDO gpg --dearmor --yes -o /etc/apt/keyrings/nodesource.gpg
  echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_20.x nodistro main" \
    | $SUDO tee /etc/apt/sources.list.d/nodesource.list >/dev/null
  $SUDO apt-get update -y
  $SUDO apt-get install -y nodejs
}

start_ovs() {
  log "starting Open vSwitch daemons"
  if [ -d /run/systemd/system ] && command -v systemctl >/dev/null 2>&1; then
    $SUDO systemctl enable --now openvswitch-switch || warn "systemctl could not start openvswitch-switch"
  else
    $SUDO service openvswitch-switch start || warn "service start failed (no systemd)"
  fi
  sleep 2
  if $SUDO ovs-vsctl --timeout=5 show >/dev/null 2>&1; then
    log "ovsdb reachable"
  else
    warn "ovs-vsctl cannot reach ovsdb; run 'flowguard doctor' for details"
  fi
}

make_venvs() {
  cd "$REPO_DIR"
  log "creating .venv-engine (Python 3.9, Ryu 4.34 pins)"
  [ -d .venv-engine ] || python3.9 -m venv .venv-engine
  .venv-engine/bin/python -m pip install --quiet "pip==${PIP_VERSION}" "setuptools==${SETUPTOOLS_VERSION}" wheel
  .venv-engine/bin/python -m pip install --quiet -r requirements/engine.txt -r requirements/engine-dev.txt

  # --system-site-packages: the apt `mininet` package installs its Python module system-wide, and the
  # lab/helper must import it. Everything FlowGuard runs in Python still goes through a venv.
  log "creating .venv-core (system Python $(python3 --version | cut -d' ' -f2), sees apt Mininet)"
  [ -d .venv-core ] || python3 -m venv --system-site-packages .venv-core
  .venv-core/bin/python -m pip install --quiet --upgrade pip
  .venv-core/bin/python -m pip install --quiet -r requirements/core.txt
}

main() {
  preflight
  [ "$SKIP_APT" -eq 1 ] || install_apt
  [ "$SKIP_NODE" -eq 1 ] || install_node
  start_ovs
  [ "$SKIP_VENV" -eq 1 ] || make_venvs
  log "running doctor"
  "$REPO_DIR/bin/flowguard" doctor || warn "doctor reported failures; read the fix column above"
  log "setup finished"
}

main "$@"
