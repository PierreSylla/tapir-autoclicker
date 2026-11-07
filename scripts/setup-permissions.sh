#!/usr/bin/env bash
set -euo pipefail

rule_src="$(dirname "$(readlink -f "$0")")/../packaging/70-tapir-uinput.rules"
rule_dst=/etc/udev/rules.d/70-tapir-uinput.rules

if [[ -w /dev/uinput ]]; then
    echo "/dev/uinput is already writable for $USER, so Tapir works without this rule."
    read -rp "Install $rule_dst anyway? [y/N] " answer || answer=
else
    echo "Tapir needs write access to /dev/uinput to create its virtual mouse."
    echo "This installs $rule_dst, which gives that access to the user logged in"
    echo "at the seat (systemd 'uaccess'), and reloads udev. It uses sudo."
    read -rp "Proceed? [y/N] " answer || answer=
fi
if [[ $answer != [yY]* ]]; then
    echo "Nothing changed."
    exit 0
fi

sudo install -Dm644 "$rule_src" "$rule_dst"
[[ -e /dev/uinput ]] || sudo modprobe uinput
sudo udevadm control --reload-rules
sudo udevadm trigger --sysname-match=uinput
sudo udevadm settle

if [[ -w /dev/uinput ]]; then
    echo "Done: /dev/uinput is writable."
else
    echo "Rule installed, but /dev/uinput is not writable yet. Log out and back in, or reboot."
fi
