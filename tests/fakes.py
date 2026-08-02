"""In-memory fakes implementing the ports, for Qt-free unit tests."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from copyboard.application.events import HistoryChangeEvent
from copyboard.domain.clipping import Clipping


class FakeClock:
    """A controllable :class:`~copyboard.domain.ports.Clock` for deterministic time in tests."""

    def __init__(self, current_time: datetime) -> None:
        self._current_time = current_time

    def now(self) -> datetime:
        return self._current_time

    def advance(self, delta: timedelta) -> None:
        self._current_time += delta


class FakeVault:
    """A ``ClippingVault`` that records image bytes instead of writing them to disk."""

    def __init__(self) -> None:
        self.stored_images: list[tuple[bytes, str]] = []

    def store_image_bytes(self, data: bytes, suffix: str) -> Path:
        self.stored_images.append((data, suffix))
        return Path(f"/fake/vault/image_{len(self.stored_images)}{suffix}")


class FakeClipboardSink:
    """A :class:`~copyboard.domain.ports.ClipboardSink` that records what was re-copied."""

    def __init__(self) -> None:
        self.copied_clippings: list[Clipping] = []

    def copy_clipping_to_system_clipboard(self, clipping: Clipping) -> None:
        self.copied_clippings.append(clipping)


class RecordingHistoryObserver:
    """A :class:`~copyboard.application.events.HistoryObserver` that records received events."""

    def __init__(self) -> None:
        self.events: list[HistoryChangeEvent] = []

    def on_history_changed(self, event: HistoryChangeEvent) -> None:
        self.events.append(event)
