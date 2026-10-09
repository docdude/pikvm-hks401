#!/bin/bash
# Deploy this repo onto the PiKVM. Run as root from anywhere.
set -euo pipefail

cd "$(dirname "$(realpath "$0")")"

if [[ $EUID -ne 0 ]]; then
    echo "ERROR: run as root" >&2
    exit 1
fi

REMOUNTED=0
if findmnt -no OPTIONS / | tr ',' '\n' | grep -qx ro; then
    mount -o remount,rw /
    REMOUNTED=1
fi
trap 'if [[ $REMOUNTED -eq 1 ]]; then sync; mount -o remount,ro /; fi' EXIT

install -Dm0755 daemon/hks401d                     /usr/local/bin/hks401d
install -Dm0755 cli/hks401                         /usr/local/bin/hks401
install -Dm0644 pikvm/hks401.py                    /usr/local/lib/hks401/hks401.py
install -Dm0644 pikvm/web/hks401.css               /usr/local/lib/hks401/hks401.css
install -Dm0755 pikvm/install-hks401-kvmd-plugin   /usr/local/sbin/install-hks401-kvmd-plugin
install -Dm0644 pikvm/override-hks401.yaml         /etc/kvmd/override.d/hks401.yaml
install -Dm0644 systemd/hks401d.service            /etc/systemd/system/hks401d.service
install -Dm0644 systemd/kvmd-hks401-override.conf  /etc/systemd/system/kvmd.service.d/override.conf
install -Dm0644 udev/99-hks401-uart.rules          /etc/udev/rules.d/99-hks401-uart.rules

# override.yaml is merged after override.d and would replace our view table.
if grep -q hks401 /etc/kvmd/override.yaml; then
    echo "WARNING: /etc/kvmd/override.yaml still contains hks401 settings that" >&2
    echo "         take precedence over /etc/kvmd/override.d/hks401.yaml." >&2
    echo "         Remove them (backup: /etc/kvmd/override.yaml.pre-hks401-driver)." >&2
fi

# Keep the serial login service from competing with hks401d for ttyAMA0.
# systemd-getty-generator can request it because PiKVM boots with
# console=ttyAMA0; masking takes precedence without editing /boot/cmdline.
systemctl mask --now serial-getty@ttyAMA0.service
if [[ "$(systemctl is-enabled serial-getty@ttyAMA0.service)" != "masked" ]]; then
    echo "ERROR: serial getty is not masked" >&2
    exit 1
fi

systemctl daemon-reload
systemctl restart hks401d
# kvmd's ExecStartPre runs install-hks401-kvmd-plugin.
systemctl restart kvmd

echo "HKS401 deployed."
