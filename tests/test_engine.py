import threading
import time

from tapir.engine import (
    DOUBLE_CLICK_GAP_S,
    MIN_INTERVAL_MS,
    Clicker,
    ClickSettings,
    State,
    gap_ms,
    gap_range_ms,
    total_ms,
)


class FakeEmitter:
    def __init__(self):
        self.events = []

    def press(self, button):
        self.events.append(("press", button, time.monotonic()))

    def release(self, button):
        self.events.append(("release", button, time.monotonic()))

    def presses(self):
        return [e for e in self.events if e[0] == "press"]


class Recorder:
    def __init__(self, settings, start_delay_s=0):
        self.emitter = FakeEmitter()
        self.states = []
        self.counts = []
        self.stopped = threading.Event()
        self.first_click = threading.Event()
        self.clicker = Clicker(self.emitter, self.on_state, self.on_count)
        self.clicker.start(settings, start_delay_s)

    def on_state(self, state, countdown=0):
        self.states.append((state, countdown))
        if state == State.STOPPED:
            self.stopped.set()

    def on_count(self, count):
        self.counts.append(count)
        self.first_click.set()


def test_total_ms():
    assert total_ms() == 0
    assert total_ms(1, 2, 3, 4) == 3_723_004
    assert total_ms(milliseconds=250) == 250


def test_gap_without_jitter_is_the_interval():
    assert {gap_ms(250) for _ in range(100)} == {250}
    assert gap_ms(0) == MIN_INTERVAL_MS


def test_jitter_stays_within_bounds_and_varies():
    gaps = [gap_ms(100, 20) for _ in range(2000)]
    assert min(gaps) >= 80 and max(gaps) <= 120
    assert min(gaps) < 85 and max(gaps) > 115


def test_jitter_never_goes_below_floor():
    assert gap_range_ms(15, 50) == (MIN_INTERVAL_MS, 65)
    assert gap_range_ms(0, 5) == (MIN_INTERVAL_MS, 15)
    assert min(gap_ms(15, 50) for _ in range(2000)) >= MIN_INTERVAL_MS


def test_interval_floor_applies_below_minimum():
    rec = Recorder(ClickSettings(interval_ms=0, repeat=5))
    assert rec.stopped.wait(2)
    times = [e[2] for e in rec.emitter.presses()]
    assert len(times) == 5
    assert times[-1] - times[0] >= 4 * MIN_INTERVAL_MS / 1000 - 0.001


def test_repeat_n_stops_after_exactly_n_clicks():
    rec = Recorder(ClickSettings(interval_ms=10, repeat=7))
    assert rec.stopped.wait(2)
    assert len(rec.emitter.presses()) == 7
    assert rec.counts == list(range(1, 8))
    assert rec.states[-1] == (State.STOPPED, 0)
    assert not rec.clicker.active


def test_stop_during_wait_is_immediate():
    rec = Recorder(ClickSettings(interval_ms=10_000))
    assert rec.first_click.wait(1)
    t0 = time.monotonic()
    rec.clicker.stop()
    assert time.monotonic() - t0 < 0.05
    assert rec.stopped.is_set()
    assert len(rec.emitter.presses()) == 1


def test_double_click_emits_two_press_release_pairs():
    rec = Recorder(ClickSettings(interval_ms=100, button="right", double=True, repeat=1))
    assert rec.stopped.wait(2)
    assert [e[:2] for e in rec.emitter.events] == [
        ("press", "right"), ("release", "right"), ("press", "right"), ("release", "right"),
    ]
    assert rec.emitter.events[2][2] - rec.emitter.events[1][2] >= DOUBLE_CLICK_GAP_S - 0.005
    assert rec.counts == [1]


def test_start_delay_counts_down_then_clicks():
    t0 = time.monotonic()
    rec = Recorder(ClickSettings(interval_ms=10, repeat=1), start_delay_s=0.3)
    assert rec.stopped.wait(2)
    assert rec.emitter.events[0][2] - t0 >= 0.3
    assert rec.states[0] == (State.PENDING, 1)
    assert (State.RUNNING, 0) in rec.states


def test_stop_during_countdown_cancels_without_clicking():
    rec = Recorder(ClickSettings(interval_ms=10), start_delay_s=5)
    time.sleep(0.05)
    rec.clicker.stop()
    assert rec.emitter.events == []
    assert rec.states[0] == (State.PENDING, 5)
    assert rec.states[-1] == (State.STOPPED, 0)


def test_start_while_active_is_ignored():
    rec = Recorder(ClickSettings(interval_ms=10_000))
    assert rec.first_click.wait(1)
    rec.clicker.start(ClickSettings(interval_ms=10))
    time.sleep(0.05)
    rec.clicker.stop()
    assert len(rec.emitter.presses()) == 1
