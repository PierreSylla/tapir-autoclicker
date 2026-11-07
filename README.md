# Tapir

A small autoclicker for Linux Wayland desktops, with a compact Qt window.

Clicks go through a virtual `uinput` mouse, so they work under any compositor. No X11 tools (xdotool, pynput, PyAutoGUI) are involved.

## Features

- Interval in hours, minutes, seconds and milliseconds (10 ms minimum), with an optional random variation of ± N ms
- Left, right or middle button; single or double click
- Repeat N times or until stopped, with a click counter
- Optional countdown (0–10 s) when starting from the window or the tray, to give you time to place the cursor
- Clicks at the current cursor position and never moves the cursor
- Global start/stop hotkey: a bind managed in Hyprland, or an evdev fallback elsewhere
- Command line and Unix socket: `tapir toggle | start | stop`
- Tray icon coloured by state (grey stopped, amber countdown, green running)
- Settings saved on every change

## Installation

### Arch Linux / CachyOS package

```
cd packaging
makepkg -si
```

The PKGBUILD builds the **last commit** of this repository: uncommitted changes, including new files that are not committed yet, are not included. It installs the `tapir` command, the desktop entry and the udev rule, and pacman reloads udev for you.

### From source

```
sudo pacman -S pyside6 python-evdev python-tomli-w
python -m tapir
```

Python 3.12 or newer. On other distributions, install PySide6, evdev and tomli-w from your package manager or with pip. From a source checkout, replace `tapir` with `python -m tapir` in the commands below.

## Permissions

Tapir creates its virtual mouse through `/dev/uinput` and needs write access to it. Many systems already give it to the logged-in user (Steam's `60-steam-input.rules` does, for example). To check:

```
test -w /dev/uinput && echo ok
```

If it is not writable, install the udev rule shipped with Tapir. The package does it for you; from source, run:

```
scripts/setup-permissions.sh
```

The script asks for confirmation, then runs:

```
sudo install -Dm644 packaging/70-tapir-uinput.rules /etc/udev/rules.d/70-tapir-uinput.rules
sudo udevadm control --reload-rules
sudo udevadm trigger --sysname-match=uinput
```

The rule uses systemd's `uaccess` tag: only the user logged in at the seat gets access, not a whole group. Its file name has to sort before `73-seat-late.rules`, where udev applies `uaccess`.

When access is missing, Tapir shows these instructions instead of starting.

On Hyprland, Tapir never reads your keyboard. The evdev fallback for other compositors needs read access to `/dev/input/event*`, usually through the `input` group. Being in that group lets every program you run read every keystroke, passwords included, so Tapir never adds you to it. Prefer your compositor's own shortcuts (see below).

## Usage

Set the interval, button, click type and repeat mode, then press **Start**. The status line shows *Stopped*, *Starting in N s* or *Running*, and the counter shows the clicks of the current session. In "Repeat N times" mode the session stops on its own.

The settings are locked while a session runs. When a tray is available, closing the window hides it to the tray; **Quit** is in the tray menu. Without a tray, closing the window quits.

## Global hotkey

### Hyprland

Click **Set…** next to *Hotkey* and press the combination: a key with optional Super, Ctrl, Alt and Shift, or a mouse side button (Mouse 4 / Mouse 5). Esc cancels, Backspace removes the hotkey.

Tapir adds the bind to Hyprland itself with `hyprctl eval` (`hl.bind`, tagged with the description `tapir`). The hotkey works when Tapir's window is not focused, and the key press does not reach other applications.

- A combination that your Hyprland config already uses is refused.
- The bind is added again when Hyprland reloads its config, and removed when Tapir quits.
- Hotkey starts are immediate: the countdown only applies to the window and tray.

Tested with Hyprland 0.57 and a Lua config, where `hyprctl keyword` is not available.

### Static bind

If you prefer a permanent bind in your own config, leave Tapir's hotkey empty and add one of these.

Lua config (`binds.lua`):

```lua
hl.bind("SUPER + F8", hl.dsp.exec_cmd("tapir toggle"))
```

hyprlang config (`hyprland.conf`):

```
bind = SUPER, F8, exec, tapir toggle
```

Do not set the same combination in both places, or each press toggles twice.

### Other compositors

Bind `tapir toggle` in your compositor's shortcut settings.

Alternatively, when Tapir runs outside Hyprland and can read `/dev/input/event*` (see Permissions), **Set…** works the same way and Tapir listens to your input devices itself. It reads them without grabbing them, so the key press also reaches the focused application. Devices plugged in later are picked up within a couple of seconds.

## Command line

```
tapir           open the window, or show the one already running
tapir toggle    start or stop clicking
tapir start     start clicking now (no countdown)
tapir stop      stop clicking
```

Commands go to the running instance through `$XDG_RUNTIME_DIR/tapir.sock`, which only your user can reach. They exit with code 1 when no instance is running. Only one instance runs at a time.

## Configuration

Settings are saved to `~/.config/tapir/config.toml` (or `$XDG_CONFIG_HOME/tapir/config.toml`) on every change and loaded at startup. Invalid values fall back to their defaults.

## Known limitations

- Tapir clicks wherever the cursor is; it cannot move the cursor or target a window.
- The tray is detected at startup. If Tapir starts before your bar, there is no tray icon and closing the window quits.
- On Wayland, `tapir` or **Show** may not raise a window that is already visible: compositors limit focus stealing (Hyprland: `misc:focus_on_activate`).
- The Hyprland conflict check compares key codes and key names. A bind written with a key name that Qt spells differently (`Prior` and `PgUp`, `Escape` and `Esc`) is not detected.
- The managed Hyprland bind has only been tested with a Lua config.
- When the 10 ms minimum clips the random variation, the average interval is slightly longer than the one set.
- evdev fallback: the hotkey also reaches the focused application, and a modifier held while its device is unplugged counts as held until it is pressed again.
- Two instances launched within the same few milliseconds can both start.

## Development

```
python -m pytest
```

`tapir/engine.py` holds the click worker and the virtual mouse (no Qt), `hotkey.py` the hotkey model, Hyprland binds and evdev listener, `ipc.py` the socket and command line, `config.py` the settings file, and `ui/` the window and tray.

## License

MIT, see [LICENSE](LICENSE).
