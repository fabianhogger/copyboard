"""History-change events and the observer machinery the service uses to notify the UI.

This is the *notification* side of the ports & adapters seam: the application defines the
``HistoryObserver`` interface and the UI (an adapter) implements it. Kept here rather than in the
domain because notification is an application-boundary concern, not a business rule.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from copyboard.domain.clipping import Clipping


@dataclass(frozen=True, slots=True)
class ClippingAdded:
    """A newly captured clipping was added to the history."""

    clipping: Clipping


@dataclass(frozen=True, slots=True)
class ClippingRemoved:
    """A clipping was explicitly removed (e.g. the user deleted it)."""

    clipping: Clipping


@dataclass(frozen=True, slots=True)
class HistoryPruned:
    """One or more clippings were dropped by the retention policy."""

    removed: tuple[Clipping, ...]


HistoryChangeEvent = ClippingAdded | ClippingRemoved | HistoryPruned


class HistoryObserver(Protocol):
    """Something that reacts to history changes — implemented by the UI."""

    def on_history_changed(self, event: HistoryChangeEvent) -> None: ...


class ObserverRegistry:
    """Holds observers and fans a single event out to all of them."""

    def __init__(self) -> None:
        self._observers: list[HistoryObserver] = []

    def register_observer(self, observer: HistoryObserver) -> None:
        self._observers.append(observer)

    def notify_all(self, event: HistoryChangeEvent) -> None:
        for observer in self._observers:
            observer.on_history_changed(event)
