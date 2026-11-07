import signal
import socket
import sys

from evdev import UInputError
from PySide6.QtCore import QSocketNotifier, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMessageBox, QSystemTrayIcon

from tapir import config as cfg
from tapir import ipc
from tapir.engine import UInputEmitter
from tapir.i18n import UINPUT_HELP, set_language, tr
from tapir.ui.tray import Tray
from tapir.ui.window import MainWindow


def run() -> int:
    app = QApplication(sys.argv)
    # Ctrl+C, kill and hangup quit like the tray's Quit, so the Hyprland bind and the socket are removed.
    # Python runs signal handlers only when the interpreter gets control, which Qt's idle C++ loop never
    # gives it: the wakeup fd wakes the loop and the notifier's slot runs Python code.
    wake_read, wake_write = socket.socketpair()
    wake_read.setblocking(False)
    wake_write.setblocking(False)
    signal.set_wakeup_fd(wake_write.fileno())
    notifier = QSocketNotifier(wake_read.fileno(), QSocketNotifier.Type.Read)
    notifier.activated.connect(lambda: wake_read.recv(64))
    for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        # Queued, because exiting before app.exec() starts is forgotten; exit() and not quit() so that
        # an open dialog's loop ends too.
        signal.signal(sig, lambda *_: QTimer.singleShot(0, app.exit))
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
