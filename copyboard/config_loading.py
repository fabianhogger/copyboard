"""Load :class:`AppConfig` from ``config.json``, falling back to defaults for anything missing.

This is the infrastructure counterpart to :mod:`copyboard.config`: it performs the file I/O and
tolerant parsing, so the pure config value objects never touch the filesystem.
"""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path
from typing import Any

from copyboard.config import AppConfig, HotkeyConfig, RetentionPolicy, Theme, UIConfig

DEFAULT_CONFIG_FILENAME = "config.json"


def write_default_config_file(config_path: Path, config: AppConfig) -> None:
    """Serialise ``config`` to ``config_path`` as pretty JSON, seeding a file the user can edit."""
    document = {
        "retention": {
            "max_items": config.retention.max_items,
            "max_age_minutes": config.retention.max_age.total_seconds() / 60,
        },
        "hotkey": {"toggle_viewer_hotkey": config.hotkey.toggle_viewer_hotkey},
        "ui": {"actions_on_right_click": config.ui.actions_on_right_click},
        "theme": config.theme.value,
    }
    config_path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")


def load_app_config_from_json(config_path: Path) -> AppConfig:
    """Return config parsed from ``config_path``, or built-in defaults if it is missing/empty.

    Unknown keys are ignored and missing sections fall back to their defaults, so a partial or
    hand-edited file never crashes the app.
    """
    if not config_path.is_file():
        return AppConfig()
    raw_text = config_path.read_text(encoding="utf-8")
    if not raw_text.strip():
        return AppConfig()
    document = json.loads(raw_text)
    if not isinstance(document, dict):
        return AppConfig()
    return _build_app_config_from_document(document)


def _build_app_config_from_document(document: dict[str, Any]) -> AppConfig:
    defaults = AppConfig()
    return AppConfig(
        retention=_build_retention_policy(document.get("retention"), defaults.retention),
        hotkey=_build_hotkey_config(document.get("hotkey"), defaults.hotkey),
        ui=_build_ui_config(document.get("ui"), defaults.ui),
        theme=_build_theme(document.get("theme"), defaults.theme),
    )


def _build_ui_config(section: Any, default: UIConfig) -> UIConfig:
    if not isinstance(section, dict):
        return default
    actions_on_right_click = bool(section.get("actions_on_right_click", default.actions_on_right_click))
    return UIConfig(actions_on_right_click=actions_on_right_click)


def _build_theme(value: Any, default: Theme) -> Theme:
    if not isinstance(value, str):
        return default
    try:
        return Theme(value.strip().lower())
    except ValueError:
        return default


def _build_retention_policy(section: Any, default: RetentionPolicy) -> RetentionPolicy:
    if not isinstance(section, dict):
        return default
    max_items = int(section.get("max_items", default.max_items))
    default_minutes = default.max_age.total_seconds() / 60
    max_age_minutes = float(section.get("max_age_minutes", default_minutes))
    return RetentionPolicy(max_items=max_items, max_age=timedelta(minutes=max_age_minutes))


def _build_hotkey_config(section: Any, default: HotkeyConfig) -> HotkeyConfig:
    if not isinstance(section, dict):
        return default
    toggle_hotkey = str(section.get("toggle_viewer_hotkey", default.toggle_viewer_hotkey))
    return HotkeyConfig(toggle_viewer_hotkey=toggle_hotkey)
