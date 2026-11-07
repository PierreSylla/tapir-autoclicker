import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

pytest.importorskip("PySide6")

APP = """
import sys
from tapir import hotkey
from tapir.ui import app

class FakeEmitter:
    def press(self, button): pass
    def release(self, button): pass
    def close(self): pass

app.UInputEmitter = FakeEmitter
hotkey.EvdevListener.available = staticmethod(lambda: False)
sys.exit(app.run())
"""


@pytest.mark.parametrize("sig", [signal.SIGTERM, signal.SIGINT, signal.SIGHUP])
def test_signal_quits_through_the_cleanup(tmp_path, sig):
    # Own runtime and config dirs: no clash with a running Tapir, no D-Bus (so no tray), no Hyprland bind.
    env = {**os.environ, "QT_QPA_PLATFORM": "offscreen", "XDG_RUNTIME_DIR": str(tmp_path),
           "XDG_CONFIG_HOME": str(tmp_path)}
    for var in ("HYPRLAND_INSTANCE_SIGNATURE", "DBUS_SESSION_BUS_ADDRESS"):
        env.pop(var, None)
    sock = tmp_path / "tapir.sock"
    proc = subprocess.Popen([sys.executable, "-c", APP], env=env, cwd=Path(__file__).parent.parent)
    try:
        deadline = time.monotonic() + 10
        while not sock.exists():
            assert proc.poll() is None and time.monotonic() < deadline
            time.sleep(0.05)
        proc.send_signal(sig)
        assert proc.wait(timeout=5) == 0
        assert not sock.exists()
    finally:
        proc.kill()
