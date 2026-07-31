"""Observe the platform's native keyboard-paste shortcut without suppressing it.

The callback runs after the first key in the active paste chord is released. By then the focused
application has handled the real Ctrl+V or Cmd+V key press, so Copyboard can safely advance its
stack without synthesising input or racing the destination's clipboard read.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from typing import Any, Protocol

from pynput import keyboard


def system_paste_hotkey_for_platform(platform: str) -> str:
    """Return pynput syntax for the native paste shortcut on ``platform``."""
    return "<cmd>+v" if platform == "darwin" else "<ctrl>+v"


class PasteObserver(Protocol):
    """A startable/stoppable observer of completed native keyboard-paste shortcuts."""

    def start(self) -> None: ...

    def stop(self) -> None: ...


class PasteShortcutReleaseGate:
    """Emit once when a previously activated paste chord begins to be released."""

    def __init__(self, on_paste_shortcut_released: Callable[[], None]) -> None:
        self._on_paste_shortcut_released = on_paste_shortcut_released
        self._paste_shortcut_is_active = False

    def record_paste_shortcut_activated(self) -> None:
        self._paste_shortcut_is_active = True

    def record_key_released(self) -> None:
        if not self._paste_shortcut_is_active:
            return
        self._paste_shortcut_is_active = False
        self._on_paste_shortcut_released()

    def reset(self) -> None:
        self._paste_shortcut_is_active = False


class PynputPasteObserver:
    """Observe Ctrl+V on Windows/Linux and Cmd+V on macOS using ``pynput``."""

    def __init__(
        self,
        on_paste_shortcut_released: Callable[[], None],
        platform: str = sys.platform,
    ) -> None:
        self._hotkey_text = system_paste_hotkey_for_platform(platform)
        self._release_gate = PasteShortcutReleaseGate(on_paste_shortcut_released)
        self._hotkey: Any = None
        self._listener: Any = None

    def start(self) -> None:
        self._release_gate.reset()
        self._hotkey = keyboard.HotKey(
            keyboard.HotKey.parse(self._hotkey_text),
            self._release_gate.record_paste_shortcut_activated,
        )
        self._listener = keyboard.Listener(
            on_press=self._handle_key_pressed,
            on_release=self._handle_key_released,
        )
        self._listener.start()

    def stop(self) -> None:
        if self._listener is not None:
            self._listener.stop()
        self._listener = None
        self._hotkey = None
        self._release_gate.reset()

    def _handle_key_pressed(self, key: Any) -> None:
        if self._hotkey is not None:
            self._hotkey.press(self._canonicalize_key(key))

    def _handle_key_released(self, key: Any) -> None:
        if self._hotkey is not None:
            self._hotkey.release(self._canonicalize_key(key))
        self._release_gate.record_key_released()

    def _canonicalize_key(self, key: Any) -> Any:
        if self._listener is None:
            return key
        return self._listener.canonical(key)
