#!/usr/bin/env bash
# FlowGuard prototype: the whole product from ONE command.
#   Mininet lab + Ryu engine + core + dashboard  ->  http://127.0.0.1:8787  (website; Demo Lab page included)
#   Streamlit operator console                   ->  http://127.0.0.1:8501
# Usage: sudo bash scripts/prototype.sh [restore|alert_only]     (Ctrl+C stops everything; or `bin/flowguard stop`)
#   restore    = the engine repairs tampered rules automatically (default)
#   alert_only = the engine only reports; an admin repairs from the dashboard
# Sign in with the demo account the stack creates on first start (see RUN_AND_SHOW.md). Local lab only: 127.0.0.1.
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODE="${1:-restore}"
RUN=/run/flowguard/data      # data dir: stack.py wipes and recreates it on every start, so logs and pids live elsewhere
LOGS=/run/flowguard/logs     # root-owned (checked below): this script runs as root and must not trust a /tmp directory
OWNER="${SUDO_USER:-root}"
cd "$REPO"

if [ "$(id -u)" -ne 0 ]; then exec sudo -E bash "$0" "$@"; fi
case "$MODE" in restore|alert_only) ;; *) echo "mode must be restore or alert_only"; exit 2 ;; esac
for v in .venv-core .venv-engine; do
  [ -x "$v/bin/python" ] || { echo "Missing $v. Run once: sudo bash scripts/setup_ubuntu.sh"; exit 1; }
done
install -d -m 0755 -o root -g root /run/flowguard "$LOGS"
for d in /run/flowguard "$LOGS"; do
  [ "$(stat -c %u "$d")" = "0" ] || { echo "$d is not owned by root; refusing to run"; exit 1; }
done

# console venv: created with uv when available (pip otherwise), once
if [ ! -x .venv-ui/bin/streamlit ]; then
  echo "[prototype] preparing the console environment (.venv-ui) ..."
  UV="$(sudo -u "$OWNER" bash -lc 'command -v uv' 2>/dev/null || true)"
  [ -n "$UV" ] || UV="$(getent passwd "$OWNER" | cut -d: -f6)/.local/bin/uv"
  if [ -x "$UV" ]; then
    sudo -u "$OWNER" bash -c "cd '$REPO' && '$UV' venv .venv-ui --python 3.10 -q && '$UV' pip install -q --python .venv-ui/bin/python -r requirements/ui.txt"
  else
    sudo -u "$OWNER" bash -c "cd '$REPO' && python3 -m venv .venv-ui && .venv-ui/bin/python -m pip install -q -r requirements/ui.txt"
  fi
fi

# dashboard build
if [ ! -f web/dist/index.html ]; then
  echo "[prototype] building the dashboard (web/dist) ..."
  command -v npm >/dev/null 2>&1 || { echo "Node is missing and web/dist is not built. Run scripts/setup_ubuntu.sh (installs Node 20)."; exit 1; }
  sudo -u "$OWNER" bash -c "cd '$REPO/web' && npm ci --no-fund --no-audit && npm run -s build"
fi

pkill -f "[r]yu-manager" 2>/dev/null || true
pkill -f "[s]treamlit run" 2>/dev/null || true
pkill -f "[c]ore.main:create_app" 2>/dev/null || true   # a stale core would keep port 8787 and hide this stack's data
mn -c >/dev/null 2>&1 || true
sleep 1

cleanup() {
  trap - INT TERM EXIT
  echo; echo "[prototype] stopping ..."
  [ -f "$LOGS/prototype.pids" ] && while read -r p; do kill "$p" 2>/dev/null || true; done < "$LOGS/prototype.pids"
  pkill -f "[r]yu-manager" 2>/dev/null || true
  pkill -f "[c]ore.main:create_app" 2>/dev/null || true
  mn -c >/dev/null 2>&1 || true
  rm -f "$LOGS/prototype.pids"
}
trap cleanup INT TERM EXIT

"$REPO/.venv-core/bin/python" "$REPO/tests/e2e_live/stack.py" --core-port 8787 --response-mode "$MODE" --data "$RUN" > "$LOGS/stack.log" 2>&1 &
echo $! > "$LOGS/prototype.pids"
for _ in $(seq 1 90); do grep -q FLOWGUARD-STACK-READY "$LOGS/stack.log" 2>/dev/null && break; sleep 1; done
grep -q FLOWGUARD-STACK-READY "$LOGS/stack.log" || { echo "stack did not become ready; see $LOGS/stack.log"; exit 1; }

sudo -u "$OWNER" -H bash -c "cd '$REPO' && exec .venv-ui/bin/streamlit run ui/streamlit_app.py --server.address 127.0.0.1 --server.port 8501 --server.headless true --browser.gatherUsageStats false" > "$LOGS/console.log" 2>&1 &
echo $! >> "$LOGS/prototype.pids"
sleep 3

cat <<MSG

  FlowGuard prototype is running (mode: $MODE)

    Website            http://127.0.0.1:8787     (Demo Lab page: simulated attacks and detection)
    Operator console   http://127.0.0.1:8501     (Streamlit; signs in by itself)
    Logs               $LOGS/stack.log  $LOGS/console.log
    Stop               Ctrl+C here, or:  bin/flowguard stop

MSG
wait
