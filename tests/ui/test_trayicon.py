"""Headless smoke test: the tray icon and its menu build without error."""

from __future__ import annotations

from PySide6.QtWidgets import QApplication

from copyboard.adapters.ui.trayicon import TrayIcon, create_default_tray_icon


def test_tray_icon_and_menu_build(qt_app: QApplication) -> None:
    recorded: list[str] = []
    tray = TrayIcon(
        create_default_tray_icon(),
        on_toggle_viewer=lambda: recorded.append("toggle"),
        on_stack_paste_mode_changed=lambda enabled: recorded.append(f"stack:{enabled}"),
        on_toggle_theme=lambda: recorded.append("theme"),
        on_edit_config=lambda: recorded.append("edit"),
        on_quit=lambda: recorded.append("quit"),
    )
    assert tray is not None


def test_stack_paste_menu_action_is_checkable_and_reports_state(qt_app: QApplication) -> None:
    recorded_states: list[bool] = []
    tray = TrayIcon(
        create_default_tray_icon(),
        on_toggle_viewer=lambda: None,
        on_stack_paste_mode_changed=recorded_states.append,
        on_toggle_theme=lambda: None,
        on_edit_config=lambda: None,
        on_quit=lambda: None,
    )
    menu = tray._tray.contextMenu()
    assert menu is not None
    stack_action = next(action for action in menu.actions() if "Stack paste" in action.text())

    tray.on_stack_paste_mode_changed(True)
    assert stack_action.isChecked()
    assert recorded_states == []

    stack_action.trigger()

    assert stack_action.isCheckable()
    assert recorded_states == [False]
