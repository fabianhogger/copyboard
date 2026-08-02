"""The application core that ties capture, classification, history and re-copy together.

``CopyboardService`` is pure orchestration: it depends only on the domain and on ports, never on
Qt. Adapters drive it (``handle_new_clipboard_content`` from the clipboard source, the UI's
``recopy``/``delete`` from user actions) and observe it (via :class:`ObserverRegistry`).
"""

from __future__ import annotations

from copyboard.application.events import (
    ClippingAdded,
    ClippingRemoved,
    HistoryObserver,
    HistoryPruned,
    ObserverRegistry,
)
from copyboard.domain.clipping import Clipping
from copyboard.domain.clippingclassifier import ClippingClassifier
from copyboard.domain.clippinghistory import ClippingHistory
from copyboard.domain.content import RawClipboardData
from copyboard.domain.ports import ClipboardSink, Clock


class CopyboardService:
    """Captures clipboard content into a bounded history and re-copies/deletes on request."""

    def __init__(
        self,
        classifier: ClippingClassifier,
        history: ClippingHistory,
        clock: Clock,
        sink: ClipboardSink,
        observers: ObserverRegistry | None = None,
    ) -> None:
        self._classifier = classifier
        self._history = history
        self._clock = clock
        self._sink = sink
        self._observers = observers if observers is not None else ObserverRegistry()
        self._current_clipboard_clipping_id: str | None = None

    def register_observer(self, observer: HistoryObserver) -> None:
        self._observers.register_observer(observer)

    def handle_new_clipboard_content(self, raw: RawClipboardData) -> None:
        """Classify a fresh clipboard snapshot, store it, and prune anything now expired."""
        clipping = self._classifier.classify_clipboard_content(raw)
        if clipping is None:
            return
        self._history.add_clipping(clipping)
        self._current_clipboard_clipping_id = clipping.id
        self._observers.notify_all(ClippingAdded(clipping))
        self.remove_expired_clippings()

    def remove_expired_clippings(self) -> None:
        """Drop clippings past the retention limits (driven by a UI timer and after each add)."""
        removed = self._history.enforce_retention(self._clock.now())
        if removed:
            self._observers.notify_all(HistoryPruned(tuple(removed)))
        if any(clipping.id == self._current_clipboard_clipping_id for clipping in removed):
            self._current_clipboard_clipping_id = None

    def recopy_clipping_by_id(self, clipping_id: str) -> None:
        clipping = self._history.find_clipping_by_id(clipping_id)
        if clipping is not None:
            self._sink.copy_clipping_to_system_clipboard(clipping)
            self._current_clipboard_clipping_id = clipping.id

    def delete_clipping_by_id(self, clipping_id: str) -> None:
        clipping = self._history.find_clipping_by_id(clipping_id)
        if clipping is not None and self._history.remove_clipping_by_id(clipping_id):
            self._observers.notify_all(ClippingRemoved(clipping))
            if self._current_clipboard_clipping_id == clipping_id:
                self._current_clipboard_clipping_id = None

    def get_current_clipboard_clipping_id(self) -> str | None:
        """Id of the history clipping now on the system clipboard, or None if none is."""
        return self._current_clipboard_clipping_id

    def pop_and_recopy_top_clipping(self) -> bool:
        """Copy the newest clipping to the system clipboard and remove it from history.

        Returns True if there was an item to pop, False if the history was empty.
        """
        clippings = self._history.list_clippings_newest_first()
        if not clippings:
            return False
        top = clippings[0]
        self._sink.copy_clipping_to_system_clipboard(top)
        self._history.remove_clipping_by_id(top.id)
        self._current_clipboard_clipping_id = None
        self._observers.notify_all(ClippingRemoved(top))
        return True

    def list_clippings_newest_first(self) -> list[Clipping]:
        return self._history.list_clippings_newest_first()
