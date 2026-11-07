import signal
import sys

from evdev import UInputError
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMessageBox, QSystemTrayIcon

from tapir import config as cfg
from tapir import ipc
from tapir.engine import UInputEmitter
from tapir.ui.tray import Tray
from tapir.ui.window import MainWindow

UINPUT_HELP = """Tapir cannot create its virtual mouse:
{error}

Tapir needs write access to /dev/uinput. Install this udev rule as /etc/udev/rules.d/99-tapir-uinput.rules:

KERNEL=="uinput", SUBSYSTEM=="misc", TAG+="uaccess", OPTIONS+="static_node=uinput"

then reload it (or reboot):

sudo udevadm control --reload-rules
sudo udevadm trigger --name-match=uinput

From the source tree, scripts/setup-permissions.sh does all of this."""


def run() -> int:
    # The kernel releases any held button when the process dies, so a hard Ctrl+C is safe.
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    app = QApplication(sys.argv)
    app.setDesktopFileName("tapir")
    app.setWindowIcon(QIcon.fromTheme("input-mouse"))
    try:
        emitter = UInputEmitter()
    except (OSError, UInputError) as e:
        QMessageBox.critical(None, "Tapir", UINPUT_HELP.format(error=e))
        return 1
    window = MainWindow(cfg.load(), emitter)
    if QSystemTrayIcon.isSystemTrayAvailable():
        tray = Tray(window)
        tray.show()
        window.hide_on_close = True
        app.setQuitOnLastWindowClosed(False)
    ipc.serve(window.bridge.command_received.emit)
    window.show()
    try:
        return app.exec()
    finally:
        ipc.SOCKET_PATH.unlink(missing_ok=True)
        window.shutdown()
        emitter.close()
