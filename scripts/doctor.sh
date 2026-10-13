#!/usr/bin/env bash
# Thin wrapper so `scripts/doctor.sh` works before any venv exists. All logic is in doctor.py.
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if ! command -v python3 >/dev/null 2>&1; then
  echo "FAIL  python3 not found. Fix: sudo apt install python3" >&2
  exit 1
fi
exec python3 "$HERE/doctor.py" "$@"
