"""The bounded, in-memory store of recent clippings.

Replaces the sketch's ``ClippingsDequeue(deque)`` with composition: time-based pruning needs to
scan, which a ``deque`` subclass would not express cleanly. Clippings are held oldest-first
(insertion order), which is also time order because captures arrive chronologically.
"""

from __future__ import annotations

from datetime import datetime

from copyboard.config import RetentionPolicy
from copyboard.domain.clipping import Clipping


class ClippingHistory:
    """Holds recent clippings under a :class:`RetentionPolicy` (max count and max age)."""

    def __init__(self, policy: RetentionPolicy) -> None:
        self._policy = policy
        self._clippings: list[Clipping] = []

    def add_clipping(self, clipping: Clipping) -> None:
        """Append a newly captured clipping and trim to the count limit."""
        self._clippings.append(clipping)
        self._trim_to_count_limit()

    def enforce_retention(self, now: datetime) -> list[Clipping]:
        """Drop clippings that are too old or beyond the count limit; return the removed ones."""
        try:
            cutoff = now - self._policy.max_age
        except OverflowError:
            cutoff = datetime.min  # max_age is timedelta.max — nothing ever expires by age
        removed = [clipping for clipping in self._clippings if clipping.created_at < cutoff]
        self._clippings = [
            clipping for clipping in self._clippings if clipping.created_at >= cutoff
        ]
        removed.extend(self._trim_to_count_limit())
        return removed

    def remove_clipping_by_id(self, clipping_id: str) -> bool:
        """Remove the clipping with the given id; return whether one was found."""
        for index, clipping in enumerate(self._clippings):
            if clipping.id == clipping_id:
                del self._clippings[index]
                return True
        return False

    def find_clipping_by_id(self, clipping_id: str) -> Clipping | None:
        for clipping in self._clippings:
            if clipping.id == clipping_id:
                return clipping
        return None

    def list_clippings_newest_first(self) -> list[Clipping]:
        return list(reversed(self._clippings))

    def count(self) -> int:
        return len(self._clippings)

    def _trim_to_count_limit(self) -> list[Clipping]:
        overflow = len(self._clippings) - self._policy.max_items
        if overflow <= 0:
            return []
        removed = self._clippings[:overflow]
        self._clippings = self._clippings[overflow:]
        return removed
