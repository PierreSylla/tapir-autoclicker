from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from tapir import config as cfg
from tapir.engine import MIN_INTERVAL_MS, Clicker, ClickSettings, State, total_ms

WIDTH = 380
WARNING_COLOR = "#d29922"
STATE_COLORS = {State.STOPPED: "#8b949e", State.PENDING: WARNING_COLOR, State.RUNNING: "#3fb950"}


class EngineBridge(QObject):
    state_changed = Signal(str, int)
    count_changed = Signal(int)


class MainWindow(QWidget):
    def __init__(self, config: cfg.Config, emitter):
        super().__init__()
        self.config = config
        self.bridge = EngineBridge()
        self.clicker = Clicker(
            emitter,
            on_state=lambda state, countdown=0: self.bridge.state_changed.emit(state, countdown),
            on_count=self.bridge.count_changed.emit,
        )
        self.bridge.state_changed.connect(self._show_state, Qt.ConnectionType.QueuedConnection)
        self.bridge.count_changed.connect(self._show_count, Qt.ConnectionType.QueuedConnection)
        self.setWindowTitle("Tapir")
        self._build()
        self._show_state(State.STOPPED, 0)
        self._show_count(0)
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
        row = QHBoxLayout(start)
        row.addWidget(QLabel("Delay before start"))
        row.addWidget(self._spin("start_delay_s", 10, " s"), 1)
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
        text = {
            State.STOPPED: "Stopped",
            State.PENDING: f"Starting in {countdown} s",
            State.RUNNING: "Running",
        }[state]
        self.status.setText(f'<span style="color:{STATE_COLORS[state]}">●</span> <b>{text}</b>')
        self.start_button.setText("Start" if state == State.STOPPED else "Stop")
        self.settings.setEnabled(state == State.STOPPED)

    def _show_count(self, count: int) -> None:
        self.counter.setText(f"Clicks: {count:,}")
