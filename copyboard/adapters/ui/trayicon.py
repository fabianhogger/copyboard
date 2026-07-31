"""System-tray presence: a menu to show/hide the viewer and to quit.

Uses ``QSystemTrayIcon``, which is cross-platform. The icon is drawn programmatically so the app
ships without image assets. User actions are forwarded through injected callbacks.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

_ICON_SIZE = 64
_ICON_BACKGROUND = "#2d6cdf"


def create_default_tray_icon() -> QIcon:
    """Draw a simple lettered badge to use as the tray icon (no asset files needed)."""
    pixmap = QPixmap(_ICON_SIZE, _ICON_SIZE)
    pixmap.fill(QColor(_ICON_BACKGROUND))
    painter = QPainter(pixmap)
    painter.setPen(QColor("white"))
    font = QFont()
    font.setPointSize(34)
    font.setBold(True)
    painter.setFont(font)
    painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "C")
    painter.end()
    return QIcon(pixmap)


class TrayIcon:
    """Owns the tray icon and its menu, delegating actions to the given callbacks."""

    def __init__(
        self,
        icon: QIcon,
        on_toggle_viewer: Callable[[], None],
        on_stack_paste_mode_changed: Callable[[bool], None],
        on_toggle_theme: Callable[[], None],
        on_edit_config: Callable[[], None],
        on_quit: Callable[[], None],
    ) -> None:
        self._on_toggle_viewer = on_toggle_viewer
        self._tray = QSystemTrayIcon(icon)
        self._tray.setToolTip("Copyboard")
        self._tray.setContextMenu(
            self._build_menu(
                on_toggle_viewer,
                on_stack_paste_mode_changed,
                on_toggle_theme,
                on_edit_config,
                on_quit,
            )
        )
        self._tray.activated.connect(self._handle_activation)

    def show(self) -> None:
        self._tray.show()

    def _build_menu(
        self,
        on_toggle_viewer: Callable[[], None],
        on_stack_paste_mode_changed: Callable[[bool], None],
        on_toggle_theme: Callable[[], None],
        on_edit_config: Callable[[], None],
        on_quit: Callable[[], None],
    ) -> QMenu:
        menu = QMenu()
        menu.addAction("Show / hide viewer").triggered.connect(lambda: on_toggle_viewer())
        self._stack_paste_action = menu.addAction("Stack paste mode (LIFO)")
        self._stack_paste_action.setCheckable(True)
        self._stack_paste_action.triggered.connect(
            lambda: on_stack_paste_mode_changed(self._stack_paste_action.isChecked())
        )
        menu.addAction("Cycle theme").triggered.connect(lambda: on_toggle_theme())
        menu.addAction("Edit config…").triggered.connect(lambda: on_edit_config())
        menu.addSeparator()
        menu.addAction("Quit Copyboard").triggered.connect(lambda: on_quit())
        return menu

    def on_stack_paste_mode_changed(self, enabled: bool) -> None:
        """Keep the checkable tray action synchronized with the application state."""
        self._stack_paste_action.setChecked(enabled)

    def _handle_activation(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self._on_toggle_viewer()
