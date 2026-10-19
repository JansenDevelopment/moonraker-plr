#!/bin/bash
# moonraker-plr installer: links the component and the Klipper macros in place.
# It does not edit moonraker.conf or printer.cfg; see README.md for those lines.
set -e
REPO="$(cd "$(dirname "$0")" && pwd)"
MOON="${MOONRAKER_DIR:-$HOME/moonraker}"
CONF="${PRINTER_CONFIG:-$HOME/printer_data/config}"

[ -d "$MOON/moonraker/components" ] || { echo "Moonraker not found in $MOON" >&2; exit 1; }
[ -d "$CONF" ] || { echo "Config dir not found: $CONF" >&2; exit 1; }

ln -sfn "$REPO/component/plr_watchdog.py" "$MOON/moonraker/components/plr_watchdog.py"
# keep Moonraker's own repo clean for its update manager
EXCL="$MOON/.git/info/exclude"
grep -qxF "moonraker/components/plr_watchdog.py" "$EXCL" 2>/dev/null \
  || echo "moonraker/components/plr_watchdog.py" >> "$EXCL"
ln -sfn "$REPO/klipper/plr.cfg" "$CONF/plr.cfg"

echo "Linked:"
ls -l "$MOON/moonraker/components/plr_watchdog.py" "$CONF/plr.cfg"
echo
echo "Next: add [plr_watchdog] + [update_manager plr] to moonraker.conf,"
echo "      [include plr.cfg] to printer.cfg, then restart Moonraker and Klipper."
