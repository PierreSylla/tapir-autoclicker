import pytest
from evdev import InputEvent, ecodes

from tapir.hotkey import BIND_DESCRIPTION, EvdevListener, Hotkey, find_conflict

SUPER_F8 = Hotkey(frozenset({"SUPER"}), ecodes.KEY_F8)


def key(code, value):
    return InputEvent(0, 0, ecodes.EV_KEY, code, value)


def test_spec_uses_hyprland_syntax():
    assert Hotkey(frozenset({"SHIFT", "SUPER"}), ecodes.KEY_F8).spec == "SUPER + SHIFT + code:74"
    assert Hotkey(frozenset(), ecodes.BTN_EXTRA).spec == "mouse:276"


@pytest.mark.parametrize(
    "hotkey",
    [SUPER_F8, Hotkey(frozenset({"CTRL", "ALT", "SHIFT"}), ecodes.KEY_A), Hotkey(frozenset({"CTRL"}), ecodes.BTN_SIDE)],
)
def test_spec_round_trip(hotkey):
    assert Hotkey.parse(hotkey.spec) == hotkey


@pytest.mark.parametrize(
    "spec", ["", "F8", "SUPER + F8", "HYPER + code:74", "code:8", "code:x", "mouse:272", "SUPER + "]
)
def test_parse_rejects_invalid(spec):
    with pytest.raises(ValueError):
        Hotkey.parse(spec)


def test_label():
    assert Hotkey(frozenset({"SHIFT", "SUPER"}), ecodes.KEY_F8).label() == "Super+Shift+F8"
    assert Hotkey(frozenset({"CTRL"}), ecodes.KEY_Q).label("A") == "Ctrl+A"
    assert Hotkey(frozenset(), ecodes.BTN_SIDE).label() == "Mouse 4"
    assert Hotkey(frozenset({"ALT"}), ecodes.BTN_EXTRA).label() == "Alt+Mouse 5"


def test_modmask_matches_hyprland():
    assert Hotkey(frozenset({"SUPER", "CTRL", "ALT", "SHIFT"}), ecodes.KEY_F8).modmask == 77


def test_listener_requires_exact_modifiers():
    hits = []
    listener = EvdevListener(lambda: hits.append(1))
    listener.hotkey = Hotkey(frozenset({"CTRL"}), ecodes.KEY_F8)
    listener.feed(key(ecodes.KEY_F8, 1))
    listener.feed(key(ecodes.KEY_RIGHTCTRL, 1))
    listener.feed(key(ecodes.KEY_F8, 1))
    listener.feed(key(ecodes.KEY_F8, 2))
    listener.feed(key(ecodes.KEY_F8, 0))
    listener.feed(key(ecodes.KEY_LEFTSHIFT, 1))
    listener.feed(key(ecodes.KEY_F8, 1))
    listener.feed(key(ecodes.KEY_LEFTSHIFT, 0))
    listener.feed(key(ecodes.KEY_RIGHTCTRL, 0))
    listener.feed(key(ecodes.KEY_F8, 1))
    assert hits == [1]


def test_listener_side_button_and_no_hotkey():
    hits = []
    listener = EvdevListener(lambda: hits.append(1))
    listener.feed(key(ecodes.BTN_SIDE, 1))
    listener.hotkey = Hotkey(frozenset(), ecodes.BTN_SIDE)
    listener.feed(key(ecodes.BTN_EXTRA, 1))
    listener.feed(key(ecodes.BTN_SIDE, 1))
    assert hits == [1]


def bind(modmask=64, key="", keycode=0, description=""):
    return {"modmask": modmask, "key": key, "keycode": keycode, "description": description}


def test_find_conflict():
    super_q = Hotkey(frozenset({"SUPER"}), ecodes.KEY_Q)
    assert find_conflict(super_q, "Q", [bind(key="Q")])
    assert find_conflict(super_q, "A", [bind(keycode=ecodes.KEY_Q + 8)])
    assert not find_conflict(super_q, "A", [bind(key="Q")])
    assert not find_conflict(super_q, "Q", [bind(modmask=65, key="Q")])
    assert not find_conflict(super_q, "Q", [bind(key="Q", description=BIND_DESCRIPTION)])
    mouse = Hotkey(frozenset({"SUPER"}), ecodes.BTN_SIDE)
    assert find_conflict(mouse, "", [bind(key="mouse:275")])
    assert not find_conflict(mouse, "", [bind(key="mouse:276")])
