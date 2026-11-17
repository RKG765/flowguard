#!/usr/bin/env bash
# Create the unprivileged service accounts FlowGuard runs as, and let them reach this checkout. Idempotent. Needs root.
#   flowguard-engine  runs the Ryu engine; the only account that can read the HMAC signing key
#   flowguard-core    runs the core API and the dashboard server; owns the database and the user accounts
#   flowguard         their shared group (the spool, the engine-to-core socket and the control folder are group-shared)
# Only the lab itself (Mininet / Open vSwitch) still needs root. Nothing here is added to sudoers or to any login group.
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
[ "$(id -u)" -eq 0 ] || { echo "run as root: sudo bash scripts/service-users.sh" >&2; exit 1; }

getent group flowguard >/dev/null || { groupadd --system flowguard; echo "created group flowguard"; }
for u in flowguard-engine flowguard-core; do
  id -u "$u" >/dev/null 2>&1 || { useradd --system --no-create-home --home-dir /nonexistent --shell /usr/sbin/nologin -g flowguard "$u"; echo "created account $u"; }
done

# every folder from / down to the checkout must be enterable by both accounts (a home folder is usually mode 750).
# Walk from the top and grant only where a folder actually blocks: a traverse-only entry on a folder the account could
# already read would REPLACE its normal read permission there (a named ACL entry overrides "other").
path=""
IFS=/ read -ra parts <<< "${REPO#/}"
for part in "${parts[@]}"; do
  path="$path/$part"
  for u in flowguard-engine flowguard-core; do
    if ! runuser -u "$u" -- test -x "$path" 2>/dev/null; then
      command -v setfacl >/dev/null || { echo "setfacl is missing (apt install acl); $u cannot enter $path" >&2; exit 1; }
      setfacl -m "u:$u:x" "$path"   # traverse only: no listing, no reading, no writing
      echo "granted $u traverse (x) on $path"
    fi
  done
done
for u in flowguard-engine flowguard-core; do
  runuser -u "$u" -- test -r "$REPO/engine/app.py" || { echo "$u cannot read the checkout at $REPO" >&2; exit 1; }
done
echo "service accounts ready"
