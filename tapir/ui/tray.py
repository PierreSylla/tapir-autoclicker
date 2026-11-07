from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from tapir.engine import State
from tapir.i18n import tr
from tapir.ui.window import STATE_COLORS, MainWindow, state_text


def state_icon(state: State) -> QIcon:
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    color = QColor(STATE_COLORS[state])
    painter.setPen(QPen(color.darker(170), 4))
    painter.setBrush(color)
    painter.drawRoundedRect(QRectF(14, 4, 36, 56), 18, 18)
    painter.drawLine(32, 4, 32, 26)
    painter.drawLine(14, 26, 50, 26)
    painter.end()
    return QIcon(pixmap)


class Tray(QSystemTrayIcon):
    def __init__(self, window: MainWindow):
        self.icons = {state: state_icon(state) for state in State}
        super().__init__(self.icons[State.STOPPED], window)
        self.window = window
        self.menu = QMenu()  # kept on self: setContextMenu does not take ownership
        self.toggle_action = self.menu.addAction("", lambda: window.toggle(with_delay=True))
        self.show_action = self.menu.addAction("", lambda: window.handle_command("show"))
        self.menu.addSeparator()
        self.quit_action = self.menu.addAction("", QApplication.quit)
        self.setContextMenu(self.menu)
        self.activated.connect(self._on_activated)
        window.bridge.state_changed.connect(self._show_state, Qt.ConnectionType.QueuedConnection)
        window.language_changed.connect(self._retranslate)
        self._retranslate()

    def _retranslate(self) -> None:
        self.show_action.setText(tr("Show"))
        self.quit_action.setText(tr("Quit"))
        self._show_state(self.window.state, self.window.countdown)

    def _show_state(self, state: str, countdown: int) -> None:
        state = State(state)
        self.setIcon(self.icons[state])
        self.setToolTip(tr("Tapir: {state}", state=state_text(state, countdown)))
        self.toggle_action.setText(tr("Start") if state == State.STOPPED else tr("Stop"))

    def _on_activated(self, reason) -> None:
        if reason != QSystemTrayIcon.ActivationReason.Trigger:
            return
        if self.window.isVisible():
            self.window.hide()
        else:
            self.window.handle_command("show")
