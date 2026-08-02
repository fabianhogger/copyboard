"""Headless smoke test: the tray icon and its menu build without error."""

from __future__ import annotations

from PySide6.QtWidgets import QApplication

from copyboard.adapters.ui.trayicon import TrayIcon, create_default_tray_icon


def test_tray_icon_and_menu_build(qt_app: QApplication) -> None:
    recorded: list[str] = []
    tray = TrayIcon(
        create_default_tray_icon(),
        on_toggle_viewer=lambda: recorded.append("toggle"),
        on_toggle_theme=lambda: recorded.append("theme"),
        on_edit_config=lambda: recorded.append("edit"),
        on_quit=lambda: recorded.append("quit"),
    )
    assert tray is not None
