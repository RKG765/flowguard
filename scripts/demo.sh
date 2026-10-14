#!/usr/bin/env bash
# FlowGuard demo: Mininet lab + engine + core + dashboard on ONE address: http://127.0.0.1:8787
# Usage: sudo bash scripts/demo.sh [restore|alert_only]    (Ctrl+C stops everything)
#   restore    = the engine repairs tampered rules automatically (default)
#   alert_only = the engine only reports; an admin repairs from the dashboard
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODE="${1:-restore}"
cd "$REPO"

if [ "$(id -u)" -ne 0 ]; then exec sudo -E bash "$0" "$@"; fi
case "$MODE" in restore|alert_only) ;; *) echo "mode must be restore or alert_only"; exit 2 ;; esac

for v in .venv-core .venv-engine; do
  [ -x "$v/bin/python" ] || { echo "Missing $v. Run once: sudo bash scripts/setup_ubuntu.sh"; exit 1; }
done

if [ ! -f web/dist/index.html ]; then
  echo "[demo] building the dashboard (web/dist) ..."
  OWNER="${SUDO_USER:-root}"
  if command -v npm >/dev/null 2>&1; then
    sudo -u "$OWNER" bash -c "cd '$REPO/web' && npm ci --no-fund --no-audit && npm run -s build"
  else
    echo "Node is not installed and web/dist is missing. Either run scripts/setup_ubuntu.sh (installs Node 20)"
    echo "or download the prebuilt dashboard from the GitHub release (see RUN_AND_SHOW.md)."; exit 1
  fi
fi

pkill -f "[r]yu-manager" 2>/dev/null || true
mn -c >/dev/null 2>&1 || true
echo
echo "  FlowGuard is starting (mode: $MODE). When you see FLOWGUARD-STACK-READY:"
echo "  open  http://127.0.0.1:8787   (first visit: create the admin account)"
echo "  stop  Ctrl+C"
echo
exec "$REPO/.venv-core/bin/python" "$REPO/tests/e2e_live/stack.py" --core-port 8787 --response-mode "$MODE" --data /tmp/flowguard-demo
