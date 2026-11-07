import math
import threading
import time
from dataclasses import dataclass
from enum import StrEnum

from evdev import UInput, ecodes

MIN_INTERVAL_MS = 10
DOUBLE_CLICK_GAP_S = 0.04
UINPUT_NAME = "tapir-virtual-mouse"
BUTTON_CODES = {"left": ecodes.BTN_LEFT, "right": ecodes.BTN_RIGHT, "middle": ecodes.BTN_MIDDLE}
BUTTONS = tuple(BUTTON_CODES)


class State(StrEnum):
    STOPPED = "stopped"
    PENDING = "pending"
    RUNNING = "running"


@dataclass(frozen=True)
class ClickSettings:
    interval_ms: int
    button: str = "left"
    double: bool = False
    repeat: int | None = None  # None = until stopped


def total_ms(hours: int = 0, minutes: int = 0, seconds: int = 0, milliseconds: int = 0) -> int:
    return ((hours * 60 + minutes) * 60 + seconds) * 1000 + milliseconds


class UInputEmitter:
    """Virtual mouse; clicks land wherever the compositor's cursor is."""

    def __init__(self):
        # REL axes are never used but make libinput classify the device as a pointer.
        self._ui = UInput(
            {ecodes.EV_KEY: list(BUTTON_CODES.values()), ecodes.EV_REL: [ecodes.REL_X, ecodes.REL_Y, ecodes.REL_WHEEL]},
            name=UINPUT_NAME,
        )

    def press(self, button: str) -> None:
        self._ui.write(ecodes.EV_KEY, BUTTON_CODES[button], 1)
        self._ui.syn()

    def release(self, button: str) -> None:
        self._ui.write(ecodes.EV_KEY, BUTTON_CODES[button], 0)
        self._ui.syn()

    def close(self) -> None:
        # The kernel drops releases for buttons that are not down, so releasing everything is safe.
        for code in BUTTON_CODES.values():
            self._ui.write(ecodes.EV_KEY, code, 0)
        self._ui.syn()
        self._ui.close()


class Clicker:
    """Click worker thread; callbacks run on the worker thread."""

    def __init__(self, emitter, on_state=None, on_count=None):
        self._emitter = emitter
        self._on_state = on_state or (lambda state, countdown=0: None)
        self._on_count = on_count or (lambda count: None)
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    @property
    def active(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self, settings: ClickSettings, start_delay_s: float = 0) -> None:
        if self.active:
            return
        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=self._run, args=(settings, start_delay_s, self._stop), name="tapir-clicker", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join()

    def _run(self, settings: ClickSettings, start_delay_s: float, stop: threading.Event) -> None:
        try:
            if self._countdown(start_delay_s, stop):
                return
            self._on_state(State.RUNNING)
            self._click_loop(settings, stop)
        finally:
            self._on_state(State.STOPPED)

    def _countdown(self, seconds: float, stop: threading.Event) -> bool:
        end = time.monotonic() + seconds
        while (left := end - time.monotonic()) > 0:
            whole = math.ceil(left)
            self._on_state(State.PENDING, whole)
            if stop.wait(left - whole + 1):
                return True
        return stop.is_set()

    def _click_loop(self, settings: ClickSettings, stop: threading.Event) -> None:
        interval = max(settings.interval_ms, MIN_INTERVAL_MS) / 1000
        count = 0
        next_at = time.monotonic()
        while settings.repeat is None or count < settings.repeat:
            if stop.wait(max(0.0, next_at - time.monotonic())):
                return
            self._click(settings, stop)
            count += 1
            self._on_count(count)
            # After a stall (suspend, overload) resume from now instead of firing a burst of late clicks.
            next_at = max(next_at + interval, time.monotonic())

    def _click(self, settings: ClickSettings, stop: threading.Event) -> None:
        self._emitter.press(settings.button)
        self._emitter.release(settings.button)
        if settings.double and not stop.wait(DOUBLE_CLICK_GAP_S):
            self._emitter.press(settings.button)
            self._emitter.release(settings.button)
