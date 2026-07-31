"""Apply flat light, dark, and translucent colour themes to the Qt application.

Uses the Fusion style plus an explicit :class:`QPalette` so the look is identical on every platform
(Windows, Linux, macOS). ``Theme.SYSTEM`` leaves Qt's native palette untouched. ``Theme.GLASS``
draws a translucent window with a subtle top-lit gradient glint over frosted fills. A
:class:`ThemeController` keeps the current choice so the tray can flip it live.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication, QWidget

from copyboard.config import Theme

_FUSION_STYLE = "Fusion"

_GLASS_STYLESHEET = (
    "MainWindow {"
    "  background: qlineargradient(x1:0, y1:0, x2:0, y2:1,"
    "    stop:0.000 rgba(160, 200, 255, 100),"  # sky-blue glint — top rim in full light
    "    stop:0.040 rgba(100, 145, 235,  55),"  # glow fades
    "    stop:0.085 rgba(255, 255, 255,  28),"  # transitions to frosted-white body
    "    stop:0.500 rgba(255, 255, 255,  18),"  # mid-body
    "    stop:1.000 rgba(255, 255, 255,  10));"  # slight lift toward the bottom (reflected table)
    "  border-top:    1px solid rgba(200, 225, 255, 160);"  # lit rim
    "  border-left:   1px solid rgba(150, 185, 255,  90);"
    "  border-right:  1px solid rgba( 80, 115, 210,  60);"
    "  border-bottom: 1px solid rgba( 55,  85, 185,  55);"
    "  border-radius: 7px;"
    "}"
    "QScrollArea { background: transparent; border: none; }"
    "QScrollArea > QWidget > QWidget { background: transparent; }"
    "ClippingWidget {"
    "  background-color: rgba(43, 43, 43, 245);"
    "  border: 1px solid rgba(80, 80, 80, 240);"
    "  border-radius: 3px;"
    "  margin: 1px 2px;"
    "}"
    "QPushButton {"
    "  background-color: rgba(50, 50, 50, 255);"
    "  border: 1px solid rgba(85, 85, 85, 255);"
    "  border-radius: 3px;"
    "  padding: 6px 8px;"
    "}"
    "QPushButton:checked { background-color: rgba(72, 72, 72, 255); }"
)

_THEME_CYCLE: dict[Theme, Theme] = {
    Theme.DARK: Theme.LIGHT,
    Theme.LIGHT: Theme.GLASS,
    Theme.GLASS: Theme.DARK,
}


def next_theme(current: Theme) -> Theme:
    """The theme a toggle switches to; ``SYSTEM`` resolves toward dark first."""
    return _THEME_CYCLE.get(current, Theme.DARK)


def apply_theme(app: QApplication, theme: Theme) -> None:
    """Switch the whole application colour palette to ``theme``; a no-op for ``Theme.SYSTEM``."""
    if theme is Theme.SYSTEM:
        return
    app.setStyle(_FUSION_STYLE)
    if theme is Theme.LIGHT:
        app.setPalette(app.style().standardPalette())
    else:
        # DARK and GLASS share the same dark palette; GLASS adds window-level transparency.
        app.setPalette(_dark_palette())


def apply_glass_window_effect(window: QWidget, enable: bool) -> None:
    """Enable or disable the translucent-background (glass) effect on the viewer window.

    Sets ``WA_TranslucentBackground`` so the compositor can show what's beneath the window, then
    applies an RGBA stylesheet so the window draws a semi-opaque dark tint instead of a solid fill.
    Clearing the stylesheet and the attribute restores normal opaque rendering.

    Note: on X11 without a compositor the transparency will not show through — the window will
    simply look darker than normal because the attribute is set but not composited.
    """
    window.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, enable)
    window.setStyleSheet(_GLASS_STYLESHEET if enable else "")


def _dark_palette() -> QPalette:
    window = QColor(30, 30, 30)
    base = QColor(23, 23, 23)
    text = QColor(220, 220, 220)
    disabled = QColor(120, 120, 120)
    accent = QColor(45, 108, 223)

    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, window)
    palette.setColor(QPalette.ColorRole.WindowText, text)
    palette.setColor(QPalette.ColorRole.Base, base)
    palette.setColor(QPalette.ColorRole.AlternateBase, window)
    palette.setColor(QPalette.ColorRole.ToolTipBase, window)
    palette.setColor(QPalette.ColorRole.ToolTipText, text)
    palette.setColor(QPalette.ColorRole.Text, text)
    palette.setColor(QPalette.ColorRole.Button, window)
    palette.setColor(QPalette.ColorRole.ButtonText, text)
    palette.setColor(QPalette.ColorRole.BrightText, QColor(255, 80, 80))
    palette.setColor(QPalette.ColorRole.Link, accent)
    palette.setColor(QPalette.ColorRole.Highlight, accent)
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(255, 255, 255))
    for role in (
        QPalette.ColorRole.WindowText,
        QPalette.ColorRole.Text,
        QPalette.ColorRole.ButtonText,
    ):
        palette.setColor(QPalette.ColorGroup.Disabled, role, disabled)
    return palette


class ThemeController:
    """Holds the active theme and re-applies it to the application when toggled.

    If a ``window`` is provided, toggling to/from ``Theme.GLASS`` also applies or removes the
    translucent-background effect on that window.
    """

    def __init__(
        self,
        app: QApplication,
        initial_theme: Theme,
        window: QWidget | None = None,
    ) -> None:
        self._app = app
        self._theme = initial_theme
        self._window = window
        apply_theme(app, initial_theme)
        if window is not None:
            apply_glass_window_effect(window, initial_theme is Theme.GLASS)

    @property
    def theme(self) -> Theme:
        return self._theme

    def toggle(self) -> None:
        self._theme = next_theme(self._theme)
        apply_theme(self._app, self._theme)
        if self._window is not None:
            apply_glass_window_effect(self._window, self._theme is Theme.GLASS)
