import json
import os
import selectors
import shlex
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import evdev
from evdev import ecodes

from tapir.engine import UINPUT_NAME
from tapir.i18n import tr, translate_label
from tapir.ipc import RUNTIME_DIR

MODMASKS = {"SUPER": 64, "CTRL": 4, "ALT": 8, "SHIFT": 1}
MOD_LABELS = {"SUPER": "Super", "CTRL": "Ctrl", "ALT": "Alt", "SHIFT": "Shift"}
MOUSE_LABELS = {ecodes.BTN_SIDE: "Mouse 4", ecodes.BTN_EXTRA: "Mouse 5"}
# Right Alt is left out: it is AltGr on most layouts, which Qt and Hyprland don't treat as Alt either.
EVDEV_MODIFIERS = {
    ecodes.KEY_LEFTMETA: "SUPER",
    ecodes.KEY_RIGHTMETA: "SUPER",
    ecodes.KEY_LEFTCTRL: "CTRL",
    ecodes.KEY_RIGHTCTRL: "CTRL",
    ecodes.KEY_LEFTALT: "ALT",
    ecodes.KEY_LEFTSHIFT: "SHIFT",
    ecodes.KEY_RIGHTSHIFT: "SHIFT",
}
XKB_KEYCODE_OFFSET = 8
BIND_DESCRIPTION = "tapir"
RESCAN_S = 2.0


class HotkeyError(Exception):
    pass


@dataclass(frozen=True)
class Hotkey:
    mods: frozenset[str]
    code: int  # evdev code, so it is layout independent and usable by both backends

    @property
    def is_mouse(self) -> bool:
        return self.code in MOUSE_LABELS

    @property
    def modmask(self) -> int:
        return sum(MODMASKS[m] for m in self.mods)

    @property
    def spec(self) -> str:
        """Hyprland key combo, also used as the config value."""
        key = f"mouse:{self.code}" if self.is_mouse else f"code:{self.code + XKB_KEYCODE_OFFSET}"
        return " + ".join([*(m for m in MODMASKS if m in self.mods), key])

    @classmethod
    def parse(cls, spec: str) -> "Hotkey":
        *mods, key = (part.strip() for part in spec.split("+"))
        kind, _, number = key.partition(":")
        if number.isdigit() and set(mods) <= MODMASKS.keys():
            code = int(number)
            if kind == "code" and code > XKB_KEYCODE_OFFSET:
                return cls(frozenset(mods), code - XKB_KEYCODE_OFFSET)
            if kind == "mouse" and code in MOUSE_LABELS:
                return cls(frozenset(mods), code)
        raise ValueError(f"invalid hotkey: {spec!r}")

    def label(self, key_text: str = "") -> str:
        """key_text comes from Qt so letters match the user's layout; evdev names assume QWERTY."""
        key = MOUSE_LABELS.get(self.code) or key_text or _evdev_key_name(self.code)
        return "+".join([*(MOD_LABELS[m] for m in MODMASKS if m in self.mods), key])


def _evdev_key_name(code: int) -> str:
    name = ecodes.KEY.get(code, f"KEY_{code}")
    return (name[0] if isinstance(name, list) else name).removeprefix("KEY_")


def on_hyprland() -> bool:
    return bool(os.environ.get("HYPRLAND_INSTANCE_SIGNATURE")) and shutil.which("hyprctl") is not None


def hyprland_event_socket() -> Path:
    return RUNTIME_DIR / "hypr" / os.environ["HYPRLAND_INSTANCE_SIGNATURE"] / ".socket2.sock"


def toggle_command() -> str:
    # PYTHONPATH lets the bind work from a source checkout as well as from an install.
    root = Path(__file__).resolve().parent.parent
    return f"PYTHONPATH={shlex.quote(str(root))} {shlex.quote(sys.executable)} -m tapir toggle"


def find_conflict(hotkey: Hotkey, key_text: str, binds: list[dict]) -> dict | None:
    for bind in binds:
        if bind.get("modmask") != hotkey.modmask or bind.get("description") == BIND_DESCRIPTION:
            continue
        if hotkey.is_mouse:
            if bind.get("key") == f"mouse:{hotkey.code}":
                return bind
        elif bind.get("keycode") == hotkey.code + XKB_KEYCODE_OFFSET or (
            key_text and str(bind.get("key", "")).lower() == key_text.lower()
        ):
            return bind
    return None


def hyprland_bind(hotkey: Hotkey, key_text: str) -> None:
    try:
        binds = json.loads(_hyprctl("binds", "-j"))
    except ValueError as e:
        raise HotkeyError(f"unexpected hyprctl output: {e}") from e
    if find_conflict(hotkey, key_text, binds):
        label = translate_label(hotkey.label(key_text))
        raise HotkeyError(tr("{label} is already bound in Hyprland.", label=label))
    # hl.unbind drops every bind on the combo; safe here because the conflict check proved they are all ours,
    # and it removes a duplicate left behind by a crashed instance.
    hyprland_unbind(hotkey)
    _hyprctl(
        "eval",
        f"hl.bind({_lua(hotkey.spec)}, hl.dsp.exec_cmd({_lua(toggle_command())}), "
        f"{{ description = {_lua(BIND_DESCRIPTION)} }})",
    )


def hyprland_unbind(hotkey: Hotkey) -> None:
    _hyprctl("eval", f"hl.unbind({_lua(hotkey.spec)})")


def _lua(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _hyprctl(*args: str) -> str:
    try:
        result = subprocess.run(["hyprctl", *args], capture_output=True, text=True, timeout=3)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise HotkeyError(str(e)) from e
    if result.returncode or result.stdout.startswith("error"):
        raise HotkeyError((result.stdout or result.stderr).strip())
    return result.stdout


class EvdevListener:
    """Global hotkey fallback for non-Hyprland sessions. Reads input devices without grabbing them."""

    def __init__(self, on_trigger):
        self.hotkey: Hotkey | None = None
        self._on_trigger = on_trigger
        self._held: set[int] = set()

    @staticmethod
    def available() -> bool:
        return bool(evdev.list_devices())

    def start(self) -> None:
        threading.Thread(target=self._run, name="tapir-hotkey", daemon=True).start()

    def feed(self, event) -> None:
        if event.type != ecodes.EV_KEY:
            return
        if event.code in EVDEV_MODIFIERS:
            (self._held.add if event.value else self._held.discard)(event.code)
            return
        hotkey = self.hotkey
        if (
            hotkey
            and event.value == 1
            and event.code == hotkey.code
            and {EVDEV_MODIFIERS[c] for c in self._held} == hotkey.mods
        ):
            self._on_trigger()

    def _run(self) -> None:
        selector = selectors.DefaultSelector()
        devices: dict[str, evdev.InputDevice | None] = {}
        while True:
            self._rescan(selector, devices)
            deadline = time.monotonic() + RESCAN_S
            while (left := deadline - time.monotonic()) > 0:
                for key, _ in selector.select(left):
                    device = key.fileobj
                    try:
                        for event in device.read():
                            self.feed(event)
                    except BlockingIOError:
                        pass
                    except OSError:
                        selector.unregister(device)
                        devices.pop(device.path, None)
                        device.close()

    @staticmethod
    def _rescan(selector: selectors.BaseSelector, devices: dict) -> None:
        paths = set(evdev.list_devices())
        for path in devices.keys() - paths:
            if device := devices.pop(path):
                selector.unregister(device)
                device.close()
        for path in paths - devices.keys():
            try:
                device = evdev.InputDevice(path)
            except OSError:
                continue
            if device.name == UINPUT_NAME or ecodes.EV_KEY not in device.capabilities():
                device.close()
                devices[path] = None
            else:
                selector.register(device, selectors.EVENT_READ)
                devices[path] = device
