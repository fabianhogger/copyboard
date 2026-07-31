"""Application configuration — plain, immutable value objects with sensible defaults.

Loading these from ``config.json`` lives in :mod:`copyboard.config_loading` so this module stays
pure (no file I/O), which keeps it safe to import from the domain layer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from enum import Enum

_DEFAULT_MAX_ITEMS = 30
_DEFAULT_MAX_AGE = timedelta.max  # no age limit unless the user sets max_age_minutes
_DEFAULT_TOGGLE_HOTKEY = "ctrl+shift+h"
_DEFAULT_POP_AND_PASTE_HOTKEY = "ctrl+v"


class Theme(Enum):
    """The viewer's colour theme. ``SYSTEM`` leaves Qt's native palette untouched."""

    DARK = "dark"
    LIGHT = "light"
    SYSTEM = "system"
    GLASS = "glass"


@dataclass(frozen=True, slots=True)
class RetentionPolicy:
    """How many clippings to keep and for how long. Both limits apply together."""

    max_items: int = _DEFAULT_MAX_ITEMS
    max_age: timedelta = _DEFAULT_MAX_AGE


@dataclass(frozen=True, slots=True)
class HotkeyConfig:
    """The global hotkeys that control viewer and clipboard-stack behaviour."""

    toggle_viewer_hotkey: str = _DEFAULT_TOGGLE_HOTKEY
    pop_and_paste_hotkey: str = _DEFAULT_POP_AND_PASTE_HOTKEY


@dataclass(frozen=True, slots=True)
class UIConfig:
    """UI behaviour options."""

    actions_on_right_click: bool = False
    lifo_paste_enabled: bool = True


@dataclass(frozen=True, slots=True)
class AppConfig:
    """Top-level configuration bundle wired in at the composition root."""

    retention: RetentionPolicy = field(default_factory=RetentionPolicy)
    hotkey: HotkeyConfig = field(default_factory=HotkeyConfig)
    ui: UIConfig = field(default_factory=UIConfig)
    theme: Theme = Theme.DARK
