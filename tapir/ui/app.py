import signal
import sys

from evdev import UInputError
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMessageBox, QSystemTrayIcon

from tapir import config as cfg
from tapir import ipc
from tapir.engine import UInputEmitter
from tapir.i18n import UINPUT_HELP, set_language, tr
from tapir.ui.tray import Tray
from tapir.ui.window import MainWindow


def run() -> int:
    # The kernel releases any held button when the process dies, so a hard Ctrl+C is safe.
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    app = QApplication(sys.argv)
    app.setDesktopFileName("tapir")
    app.setWindowIcon(QIcon.fromTheme("input-mouse"))
    config = cfg.load()
    set_language(config.language)
    try:
        emitter = UInputEmitter()
    except (OSError, UInputError) as e:
        QMessageBox.critical(None, "Tapir", tr(UINPUT_HELP, error=e))
        return 1
    window = MainWindow(config, emitter)
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
