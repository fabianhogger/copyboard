"""Platform shortcut selection and release gating for stack-paste observation."""

from __future__ import annotations

import pytest

from copyboard.adapters.pynputpasteobserver import (
    PasteShortcutReleaseGate,
    system_paste_hotkey_for_platform,
)


@pytest.mark.parametrize(
    ("platform", "expected_hotkey"),
    [
        ("win32", "<ctrl>+v"),
        ("linux", "<ctrl>+v"),
        ("darwin", "<cmd>+v"),
    ],
)
def test_system_paste_hotkey_matches_platform(platform: str, expected_hotkey: str) -> None:
    assert system_paste_hotkey_for_platform(platform) == expected_hotkey


def test_release_gate_emits_once_after_each_activated_paste_chord() -> None:
    notifications: list[str] = []
    gate = PasteShortcutReleaseGate(lambda: notifications.append("released"))

    gate.record_key_released()
    gate.record_paste_shortcut_activated()
    gate.record_key_released()
    gate.record_key_released()
    gate.record_paste_shortcut_activated()
    gate.record_key_released()

    assert notifications == ["released", "released"]


def test_release_gate_reset_cancels_an_active_paste_chord() -> None:
    notifications: list[str] = []
    gate = PasteShortcutReleaseGate(lambda: notifications.append("released"))
    gate.record_paste_shortcut_activated()

    gate.reset()
    gate.record_key_released()

    assert notifications == []
