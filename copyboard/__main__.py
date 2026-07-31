"""Composition root — the only place concrete adapters are wired into the service.

Builds the Qt application, the pure core (classifier, history, service) and every adapter
(clock, vault, clipboard source/sink, viewer, tray, global keyboard observers), connects them, and
runs the event loop. Keyboard callbacks fire on background threads, so they are bounced onto the GUI
thread through queued Qt signals.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QApplication

from copyboard.adapters.clipboardechoguard import ClipboardEchoGuard
from copyboard.adapters.processdetach import relaunch_detached, should_relaunch_detached
from copyboard.adapters.pynputhotkeybinder import PynputHotkeyBinder
from copyboard.adapters.pynputpasteobserver import PynputPasteObserver
from copyboard.adapters.qt.qtclipboard import QtClipboardSink, QtClipboardSource
from copyboard.adapters.systemclock import SystemClock
from copyboard.adapters.tempdirvault import TempDirVault
from copyboard.adapters.ui.apptheme import ThemeController
from copyboard.adapters.ui.mainwindow import MainWindow
from copyboard.adapters.ui.trayicon import TrayIcon, create_default_tray_icon
from copyboard.application.copyboardservice import CopyboardService
from copyboard.config import AppConfig
from copyboard.config_loading import (
    DEFAULT_CONFIG_FILENAME,
    load_app_config_from_json,
    write_default_config_file,
)
from copyboard.domain.clippingclassifier import ClippingClassifier
from copyboard.domain.clippinghistory import ClippingHistory


class _GlobalInputBridge(QObject):
    """Marshals background-thread keyboard callbacks onto the Qt GUI thread."""

    viewer_toggle_requested = Signal()
    paste_shortcut_released = Signal()


def _handle_lifo_paste(service: CopyboardService) -> None:
    """Pop the top clipping onto the clipboard.

    The original Ctrl+V keystroke that triggered this is still dispatched by the OS, so no
    synthetic paste is needed — the focused app will paste the swapped clipboard content.
    """
    service.pop_and_recopy_top_clipping()


def _open_config_in_editor(config_path: Path, config: AppConfig) -> None:
    """Open ``config.json`` in the OS default editor, seeding it with defaults if absent."""
    if not config_path.is_file():
        write_default_config_file(config_path, config)
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(config_path.resolve())))


def main() -> int:
    # A tray app should free the terminal it was launched from: re-spawn detached and return the
    # shell immediately. The detached child (guard set) falls through and runs the real app.
    if should_relaunch_detached(os.environ):
        relaunch_detached()
        return 0

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    config_path = Path(DEFAULT_CONFIG_FILENAME)
    config = load_app_config_from_json(config_path)

    clock = SystemClock()
    classifier = ClippingClassifier(vault=TempDirVault(), clock=clock)
    history = ClippingHistory(config.retention)
    echo_guard = ClipboardEchoGuard()
    clipboard = app.clipboard()
    sink = QtClipboardSink(clipboard, echo_guard)
    service = CopyboardService(classifier=classifier, history=history, clock=clock, sink=sink)

    source = QtClipboardSource(clipboard, echo_guard)
    source.set_new_content_listener(service.handle_new_clipboard_content)

    window = MainWindow(service, config.ui)
    # ThemeController is created after the window so it can apply WA_TranslucentBackground
    # before window.show(), which is required on some platforms (notably Windows).
    theme_controller = ThemeController(app, config.theme, window)
    window.show()

    tray = TrayIcon(
        create_default_tray_icon(),
        window.toggle_visibility,
        service.set_stack_paste_mode_enabled,
        theme_controller.toggle,
        lambda: _open_config_in_editor(config_path, config),
        app.quit,
    )
    service.register_stack_paste_mode_observer(tray)
    tray.show()

    bridge = _GlobalInputBridge()
    bridge.viewer_toggle_requested.connect(
        window.toggle_visibility, Qt.ConnectionType.QueuedConnection
    )
    bridge.paste_shortcut_released.connect(
        service.consume_prepared_clipping_after_paste,
        Qt.ConnectionType.QueuedConnection,
    )
    viewer_hotkey = PynputHotkeyBinder(
        config.hotkey.toggle_viewer_hotkey,
        lambda: bridge.viewer_toggle_requested.emit(),
    )
    paste_observer = PynputPasteObserver(lambda: bridge.paste_shortcut_released.emit())
    viewer_hotkey.start()
    paste_observer.start()

    paste_hotkey: PynputHotkeyBinder | None = None
    if config.ui.lifo_paste_enabled:
        paste_bridge = _HotkeyToggleBridge()
        paste_bridge.triggered.connect(
            lambda: _handle_lifo_paste(service), Qt.ConnectionType.QueuedConnection
        )
        paste_hotkey = PynputHotkeyBinder(
            config.hotkey.pop_and_paste_hotkey, lambda: paste_bridge.triggered.emit()
        )
        paste_hotkey.start()

    try:
        return app.exec()
    finally:
        hotkey.stop()
        if paste_hotkey is not None:
            paste_hotkey.stop()


if __name__ == "__main__":
    raise SystemExit(main())
