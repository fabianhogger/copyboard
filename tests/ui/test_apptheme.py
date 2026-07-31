"""Theme selection: the dark palette is dark, and toggling cycles through dark → light → glass."""

from __future__ import annotations

from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QApplication

from copyboard.adapters.ui.apptheme import (
    _GLASS_STYLESHEET,
    ThemeController,
    _dark_palette,
    next_theme,
)
from copyboard.config import Theme


def test_dark_palette_uses_a_dark_window_colour(qt_app: QApplication) -> None:
    palette = _dark_palette()
    assert palette.color(QPalette.ColorRole.Window).lightness() < 128


def test_translucent_theme_uses_flat_colours_without_gradients() -> None:
    assert "qlineargradient" not in _GLASS_STYLESHEET
    assert "background-color" in _GLASS_STYLESHEET


def test_next_theme_cycles_dark_light_glass() -> None:
    assert next_theme(Theme.DARK) is Theme.LIGHT
    assert next_theme(Theme.LIGHT) is Theme.GLASS
    assert next_theme(Theme.GLASS) is Theme.DARK
    assert next_theme(Theme.SYSTEM) is Theme.DARK


def test_controller_cycles_through_all_non_system_themes(qt_app: QApplication) -> None:
    controller = ThemeController(qt_app, Theme.DARK)
    assert controller.theme is Theme.DARK

    controller.toggle()
    assert controller.theme is Theme.LIGHT

    controller.toggle()
    assert controller.theme is Theme.GLASS

    controller.toggle()
    assert controller.theme is Theme.DARK
