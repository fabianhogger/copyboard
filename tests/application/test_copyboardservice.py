"""The application service: capture → classify → store → notify, plus re-copy/delete/prune."""

from __future__ import annotations

from datetime import datetime, timedelta

from copyboard.application.copyboardservice import CopyboardService
from copyboard.application.events import ClippingAdded, ClippingRemoved, HistoryPruned
from copyboard.config import RetentionPolicy
from copyboard.domain.clippingclassifier import ClippingClassifier
from copyboard.domain.clippinghistory import ClippingHistory
from copyboard.domain.content import RawClipboardData
from tests.fakes import FakeClipboardSink, FakeClock, FakeVault, RecordingHistoryObserver

_MOMENT = datetime(2026, 1, 1, 12, 0, 0)


def _build_service(
    policy: RetentionPolicy | None = None,
) -> tuple[CopyboardService, FakeClipboardSink, RecordingHistoryObserver, FakeClock]:
    clock = FakeClock(_MOMENT)
    classifier = ClippingClassifier(vault=FakeVault(), clock=clock)
    history = ClippingHistory(policy or RetentionPolicy())
    sink = FakeClipboardSink()
    service = CopyboardService(classifier=classifier, history=history, clock=clock, sink=sink)
    observer = RecordingHistoryObserver()
    service.register_observer(observer)
    return service, sink, observer, clock


def test_new_content_is_added_and_observers_notified() -> None:
    service, _, observer, _ = _build_service()

    service.handle_new_clipboard_content(RawClipboardData(text="hello"))

    assert len(service.list_clippings_newest_first()) == 1
    assert isinstance(observer.events[0], ClippingAdded)


def test_empty_clipboard_is_ignored() -> None:
    service, _, observer, _ = _build_service()

    service.handle_new_clipboard_content(RawClipboardData())

    assert service.list_clippings_newest_first() == []
    assert observer.events == []


def test_recopy_puts_the_clipping_back_on_the_clipboard() -> None:
    service, sink, _, _ = _build_service()
    service.handle_new_clipboard_content(RawClipboardData(text="hello"))
    clipping = service.list_clippings_newest_first()[0]

    service.recopy_clipping_by_id(clipping.id)

    assert sink.copied_clippings == [clipping]


def test_delete_removes_the_clipping_and_notifies() -> None:
    service, _, observer, _ = _build_service()
    service.handle_new_clipboard_content(RawClipboardData(text="hello"))
    clipping = service.list_clippings_newest_first()[0]

    service.delete_clipping_by_id(clipping.id)

    assert service.list_clippings_newest_first() == []
    assert any(isinstance(event, ClippingRemoved) for event in observer.events)


def test_pop_and_recopy_returns_false_when_history_is_empty() -> None:
    service, _, _, _ = _build_service()

    result = service.pop_and_recopy_top_clipping()

    assert result is False


def test_pop_and_recopy_writes_top_clipping_to_sink_and_removes_it() -> None:
    service, sink, _, _ = _build_service()
    service.handle_new_clipboard_content(RawClipboardData(text="first"))
    service.handle_new_clipboard_content(RawClipboardData(text="second"))

    result = service.pop_and_recopy_top_clipping()

    assert result is True
    assert len(sink.copied_clippings) == 1
    assert sink.copied_clippings[0].build_preview_text() == "second"
    remaining = [c.build_preview_text() for c in service.list_clippings_newest_first()]
    assert remaining == ["first"]


def test_pop_and_recopy_notifies_observers_with_clipping_removed() -> None:
    service, _, observer, _ = _build_service()
    service.handle_new_clipboard_content(RawClipboardData(text="hello"))
    observer.events.clear()

    service.pop_and_recopy_top_clipping()

    assert len(observer.events) == 1
    assert isinstance(observer.events[0], ClippingRemoved)


def test_expired_clippings_are_pruned_when_new_content_arrives() -> None:
    service, _, observer, clock = _build_service(
        RetentionPolicy(max_items=100, max_age=timedelta(minutes=20))
    )
    service.handle_new_clipboard_content(RawClipboardData(text="old"))
    clock.advance(timedelta(minutes=21))

    service.handle_new_clipboard_content(RawClipboardData(text="new"))

    previews = [clip.build_preview_text() for clip in service.list_clippings_newest_first()]
    assert previews == ["new"]
    assert any(isinstance(event, HistoryPruned) for event in observer.events)
