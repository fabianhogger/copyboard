"""Ports — the abstractions the core owns and the outside world implements.

These ``Protocol`` interfaces are the seam of the hexagonal architecture look up what this
architectur use if you do not know. Basically, we use protocols because we want the logic
to work independenty of the UI library choice [ASTERIOS]. The domain and
application layers depend only on these; concrete adapters (Qt, OS, filesystem) implement them.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Protocol

from copyboard.domain.clipping import Clipping
from copyboard.domain.content import RawClipboardData


class Clock(Protocol):
    """Supplies the current time, so time-based logic is injectable and testable."""

    def now(self) -> datetime: ...


class ClippingVault(Protocol):
    """Persists image bytes somewhere durable enough to reference by path."""

    def store_image_bytes(self, data: bytes, suffix: str) -> Path: ...


class ClipboardSource(Protocol):
    """Reads the current contents of the system clipboard."""

    def read_current_content(self) -> RawClipboardData: ...


class ClipboardSink(Protocol):
    """Writes a clipping back onto the system clipboard."""

    def copy_clipping_to_system_clipboard(self, clipping: Clipping) -> None: ...
