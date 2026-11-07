import logging

from evdev import ecodes
from PySide6.QtCore import QEvent, QObject, Qt, Signal
from PySide6.QtGui import QFont, QKeySequence
from PySide6.QtNetwork import QLocalSocket
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from tapir import config as cfg
from tapir import hotkey
from tapir.engine import MIN_INTERVAL_MS, Clicker, ClickSettings, State, total_ms

log = logging.getLogger(__name__)

WIDTH = 380
WARNING_COLOR = "#d29922"
STATE_COLORS = {State.STOPPED: "#8b949e", State.PENDING: WARNING_COLOR, State.RUNNING: "#3fb950"}
QT_MODIFIERS = {
    Qt.KeyboardModifier.MetaModifier: "SUPER",
    Qt.KeyboardModifier.ControlModifier: "CTRL",
    Qt.KeyboardModifier.AltModifier: "ALT",
    Qt.KeyboardModifier.ShiftModifier: "SHIFT",
}
QT_MOUSE_BUTTONS = {Qt.MouseButton.BackButton: ecodes.BTN_SIDE, Qt.MouseButton.ForwardButton: ecodes.BTN_EXTRA}
MODIFIER_KEYS = {
    Qt.Key.Key_Shift, Qt.Key.Key_Control, Qt.Key.Key_Meta, Qt.Key.Key_Alt, Qt.Key.Key_AltGr,
    Qt.Key.Key_Super_L, Qt.Key.Key_Super_R, Qt.Key.Key_Hyper_L, Qt.Key.Key_Hyper_R, Qt.Key.Key_CapsLock,
}


class Bridge(QObject):
    """Carries events from background threads (engine, IPC, evdev) to the GUI thread."""

    state_changed = Signal(str, int)
    count_changed = Signal(int)
    command_received = Signal(str)


def _qt_mods(modifiers) -> frozenset[str]:
    return frozenset(name for flag, name in QT_MODIFIERS.items() if modifiers & flag)


def state_text(state: State, countdown: int) -> str:
    return {
        State.STOPPED: "Stopped",
        State.PENDING: f"Starting in {countdown} s",
        State.RUNNING: "Running",
    }[state]


class MainWindow(QWidget):
    hide_on_close = False

    def __init__(self, config: cfg.Config, emitter):
        super().__init__()
        self.config = config
        self.bridge = Bridge()
        self.clicker = Clicker(
            emitter,
            on_state=lambda state, countdown=0: self.bridge.state_changed.emit(state, countdown),
            on_count=self.bridge.count_changed.emit,
        )
        queued = Qt.ConnectionType.QueuedConnection
        self.bridge.state_changed.connect(self._show_state, queued)
        self.bridge.count_changed.connect(self._show_count, queued)
        self.bridge.command_received.connect(self.handle_command, queued)
        self.hotkey: hotkey.Hotkey | None = None
        self.hyprland = hotkey.on_hyprland()
        self.listener = None
        if not self.hyprland and hotkey.EvdevListener.available():
            self.listener = hotkey.EvdevListener(lambda: self.bridge.command_received.emit("toggle"))
            self.listener.start()
        self.setWindowTitle("Tapir")
        self._build()
        self._show_state(State.STOPPED, 0)
        self._show_count(0)
        self._restore_hotkey()
        # A fixed size also makes Hyprland float the window instead of tiling it.
        self.setFixedSize(WIDTH, self.sizeHint().height())

    def start(self, with_delay: bool = True) -> None:
        if self.clicker.active:
            return
        self._show_count(0)
        self.clicker.start(self.click_settings(), self.config.start_delay_s if with_delay else 0)

    def stop(self) -> None:
        self.clicker.stop()

    def toggle(self, with_delay: bool = False) -> None:
        if self.clicker.active:
            self.stop()
        else:
            self.start(with_delay)

    def handle_command(self, command: str) -> None:
        if command == "show":
            self.showNormal()
            self.raise_()
            self.activateWindow()
        elif command == "start":
            self.start(with_delay=False)
        elif command == "stop":
            self.stop()
        elif command == "toggle":
            self.toggle()

    def closeEvent(self, event) -> None:
        if self.hide_on_close:
            event.ignore()
            self.hide()

    def shutdown(self) -> None:
        self.clicker.stop()
        if self.hyprland and self.hotkey:
            try:
                hotkey.hyprland_unbind(self.hotkey)
            except hotkey.HotkeyError as e:
                log.warning("Could not remove the Hyprland bind: %s", e)

    def click_settings(self) -> ClickSettings:
        c = self.config
        return ClickSettings(
            interval_ms=total_ms(c.hours, c.minutes, c.seconds, c.milliseconds),
            button=c.button,
            double=c.double_click,
            repeat=None if c.repeat_forever else c.repeat_count,
        )

    def _build(self) -> None:
        self.settings = QWidget()
        groups = QVBoxLayout(self.settings)
        groups.setContentsMargins(0, 0, 0, 0)

        interval = QGroupBox("Interval")
        spins = QHBoxLayout()
        for field, maximum, suffix in (
            ("hours", 99, " h"), ("minutes", 59, " min"), ("seconds", 59, " s"), ("milliseconds", 999, " ms"),
        ):
            spins.addWidget(self._spin(field, maximum, suffix))
        self.interval_hint = QLabel()
        box = QVBoxLayout(interval)
        box.addLayout(spins)
        box.addWidget(self.interval_hint)
        groups.addWidget(interval)

        click = QGroupBox("Click")
        row = QHBoxLayout(click)
        row.addWidget(QLabel("Button"))
        row.addWidget(self._combo("button", {"left": "Left", "right": "Right", "middle": "Middle"}), 1)
        row.addSpacing(8)
        row.addWidget(QLabel("Type"))
        row.addWidget(self._combo("double_click", {False: "Single", True: "Double"}), 1)
        groups.addWidget(click)

        repeat = QGroupBox("Repeat")
        times = QRadioButton("Repeat")
        forever = QRadioButton("Until stopped")
        count = self._spin("repeat_count", 1_000_000, " times", minimum=1)
        (forever if self.config.repeat_forever else times).setChecked(True)
        count.setEnabled(times.isChecked())
        times.toggled.connect(count.setEnabled)
        forever.toggled.connect(lambda on: self._set("repeat_forever", on))
        times_row = QHBoxLayout()
        times_row.addWidget(times)
        times_row.addWidget(count, 1)
        box = QVBoxLayout(repeat)
        box.addLayout(times_row)
        box.addWidget(forever)
        groups.addWidget(repeat)

        start = QGroupBox("Start")
        delay_row = QHBoxLayout()
        delay_row.addWidget(QLabel("Delay before start"))
        delay_row.addWidget(self._spin("start_delay_s", 10, " s"), 1)
        self.hotkey_label = QLabel()
        self.hotkey_button = QPushButton("Set…")
        self.hotkey_button.setToolTip("Press the new hotkey. Esc cancels, Backspace removes it.")
        self.hotkey_button.clicked.connect(self._start_capture)
        if not (self.hyprland or self.listener):
            self.hotkey_button.setEnabled(False)
            self.hotkey_label.setToolTip("Needs Hyprland, or read access to /dev/input/event*")
        hotkey_row = QHBoxLayout()
        hotkey_row.addWidget(QLabel("Hotkey"))
        hotkey_row.addWidget(self.hotkey_label, 1)
        hotkey_row.addWidget(self.hotkey_button)
        box = QVBoxLayout(start)
        box.addLayout(delay_row)
        box.addLayout(hotkey_row)
        groups.addWidget(start)

        self.status = QLabel()
        self.counter = QLabel()
        self.counter.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        status_row = QHBoxLayout()
        status_row.addWidget(self.status)
        status_row.addWidget(self.counter)

        self.start_button = QPushButton()
        self.start_button.setMinimumHeight(44)
        font = QFont(self.start_button.font())
        font.setBold(True)
        font.setPointSizeF(font.pointSizeF() * 1.2)
        self.start_button.setFont(font)
        self.start_button.clicked.connect(lambda: self.toggle(with_delay=True))

        layout = QVBoxLayout(self)
        layout.addWidget(self.settings)
        layout.addLayout(status_row)
        layout.addWidget(self.start_button)
        self._update_interval_hint()

    def _spin(self, field: str, maximum: int, suffix: str, minimum: int = 0) -> QSpinBox:
        box = QSpinBox(minimum=minimum, maximum=maximum, suffix=suffix)
        box.setValue(getattr(self.config, field))
        setattr(self.config, field, box.value())  # out-of-range values from the file are clamped by the spin box
        box.valueChanged.connect(lambda value: self._set(field, value))
        return box

    def _combo(self, field: str, options: dict) -> QComboBox:
        values = list(options)
        combo = QComboBox()
        combo.addItems(options.values())
        combo.setCurrentIndex(values.index(getattr(self.config, field)))
        combo.currentIndexChanged.connect(lambda i: self._set(field, values[i]))
        return combo

    def _set(self, field: str, value) -> None:
        setattr(self.config, field, value)
        cfg.save(self.config)
        self._update_interval_hint()

    def _update_interval_hint(self) -> None:
        ms = self.click_settings().interval_ms
        if ms < MIN_INTERVAL_MS:
            self.interval_hint.setText(
                f'<span style="color:{WARNING_COLOR}">Minimum is {MIN_INTERVAL_MS} ms, '
                f"using {MIN_INTERVAL_MS} ms</span>"
            )
        else:
            self.interval_hint.setText(f"{ms:,} ms between clicks")

    def _show_state(self, state: str, countdown: int) -> None:
        state = State(state)
        self.status.setText(
            f'<span style="color:{STATE_COLORS[state]}">●</span> <b>{state_text(state, countdown)}</b>'
        )
        self.start_button.setText("Start" if state == State.STOPPED else "Stop")
        self.settings.setEnabled(state == State.STOPPED)

    def _show_count(self, count: int) -> None:
        self.counter.setText(f"Clicks: {count:,}")

    def _show_hotkey(self) -> None:
        if not self.config.hotkey:
            self.hotkey_label.setText("None")
        elif self.hotkey:
            self.hotkey_label.setText(self.config.hotkey_label)
        else:
            self.hotkey_label.setText(f"{self.config.hotkey_label} (inactive)")

    def _restore_hotkey(self) -> None:
        if self.config.hotkey and (self.hyprland or self.listener):
            try:
                self._activate_hotkey(hotkey.Hotkey.parse(self.config.hotkey), self.config.hotkey_label)
            except ValueError as e:
                log.warning("Ignoring saved hotkey: %s", e)
        if self.hyprland:
            self._hyprland_events = QLocalSocket(self)
            self._hyprland_events.readyRead.connect(self._on_hyprland_event)
            self._hyprland_events.connectToServer(str(hotkey.hyprland_event_socket()))
        self._show_hotkey()

    def _on_hyprland_event(self) -> None:
        # A config reload (Hyprland does one on every config save) wipes binds added at runtime.
        reloaded = b"configreloaded>>" in bytes(self._hyprland_events.readAll())
        if reloaded and self.hotkey and not self._activate_hotkey(self.hotkey, self.config.hotkey_label):
            self.hotkey = None
            self._show_hotkey()

    def _activate_hotkey(self, new: hotkey.Hotkey | None, label: str) -> bool:
        try:
            if self.hyprland:
                if new:
                    hotkey.hyprland_bind(new, label.rsplit("+", 1)[-1])
                if self.hotkey and self.hotkey != new:
                    hotkey.hyprland_unbind(self.hotkey)
        except hotkey.HotkeyError as e:
            QMessageBox.warning(self, "Tapir", f"Could not set the hotkey.\n\n{e}")
            return False
        if self.listener:
            self.listener.hotkey = new
        self.hotkey = new
        return True

    def _set_hotkey(self, new: hotkey.Hotkey | None, label: str) -> None:
        self._end_capture()
        if self._activate_hotkey(new, label):
            self.config.hotkey = new.spec if new else ""
            self.config.hotkey_label = label
            cfg.save(self.config)
        self._show_hotkey()

    def _start_capture(self) -> None:
        self.hotkey_label.setText("Press a key or side button…")
        QApplication.instance().installEventFilter(self)

    def _end_capture(self) -> None:
        QApplication.instance().removeEventFilter(self)
        self._show_hotkey()

    def eventFilter(self, watched, event) -> bool:
        kind = event.type()
        if kind == QEvent.Type.KeyPress:
            if not event.isAutoRepeat():
                self._capture_key(event)
            return True
        if kind == QEvent.Type.MouseButtonPress:
            self._capture_mouse(event)
            return True
        return kind in (QEvent.Type.KeyRelease, QEvent.Type.MouseButtonRelease, QEvent.Type.MouseButtonDblClick)

    def _capture_key(self, event) -> None:
        key = event.key()
        if key in MODIFIER_KEYS:
            return
        mods = _qt_mods(event.modifiers())
        if key == Qt.Key.Key_Escape and not mods:
            self._end_capture()
        elif key == Qt.Key.Key_Backspace and not mods:
            self._set_hotkey(None, "")
        elif (code := event.nativeScanCode() - hotkey.XKB_KEYCODE_OFFSET) > 0:
            new = hotkey.Hotkey(mods, code)
            self._set_hotkey(new, new.label(QKeySequence(key).toString()))
        else:
            log.warning("Key without a scan code, cannot bind it")
            self._end_capture()

    def _capture_mouse(self, event) -> None:
        code = QT_MOUSE_BUTTONS.get(event.button())
        if code is None:
            self._end_capture()
            return
        new = hotkey.Hotkey(_qt_mods(event.modifiers()), code)
        self._set_hotkey(new, new.label())
