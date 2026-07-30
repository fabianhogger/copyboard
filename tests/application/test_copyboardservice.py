"""The application service: capture → classify → store → notify, plus re-copy/delete/prune."""

from __future__ import annotations

from datetime import datetime, timedelta

from copyboard.application.copyboardservice import CopyboardService
from copyboard.application.events import ClippingAdded, ClippingRemoved, HistoryPruned
from copyboard.config import RetentionPolicy
from copyboard.domain.clippingclassifier import ClippingClassifier
from copyboard.domain.clippinghistory import ClippingHistory
from copyboard.domain.content import RawClipboardData
from tests.fakes import (
    FakeClipboardSink,
    FakeClock,
    FakeVault,
    RecordingHistoryObserver,
    RecordingStackPasteModeObserver,
)

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


def test_stack_paste_consumes_clippings_newest_first_and_clears_after_last() -> None:
    service, sink, observer, _ = _build_service()
    for text in ["first", "second", "third"]:
        service.handle_new_clipboard_content(RawClipboardData(text=text))

    service.set_stack_paste_mode_enabled(True)

    assert sink.copied_clippings[-1].build_preview_text() == "third"
    for expected_remaining, expected_prepared in [
        (["second", "first"], "second"),
        (["first"], "first"),
    ]:
        service.consume_prepared_clipping_after_paste()
        assert [
            clipping.build_preview_text() for clipping in service.list_clippings_newest_first()
        ] == expected_remaining
        assert sink.copied_clippings[-1].build_preview_text() == expected_prepared

    service.consume_prepared_clipping_after_paste()

    assert service.list_clippings_newest_first() == []
    assert sink.clear_count == 1
    removed_previews = [
        event.clipping.build_preview_text()
        for event in observer.events
        if isinstance(event, ClippingRemoved)
    ]
    assert removed_previews == ["third", "second", "first"]


def test_paste_does_not_consume_history_while_stack_mode_is_disabled() -> None:
    service, sink, _, _ = _build_service()
    service.handle_new_clipboard_content(RawClipboardData(text="keep me"))

    service.consume_prepared_clipping_after_paste()

    assert len(service.list_clippings_newest_first()) == 1
    assert sink.copied_clippings == []
    assert sink.clear_count == 0


def test_recopying_older_clipping_makes_it_the_next_stack_item_consumed() -> None:
    service, sink, _, _ = _build_service()
    for text in ["first", "second", "third"]:
        service.handle_new_clipboard_content(RawClipboardData(text=text))
    oldest = service.list_clippings_newest_first()[-1]
    service.set_stack_paste_mode_enabled(True)

    service.recopy_clipping_by_id(oldest.id)
    service.consume_prepared_clipping_after_paste()

    remaining_previews = [
        clipping.build_preview_text() for clipping in service.list_clippings_newest_first()
    ]
    assert remaining_previews == ["third", "second"]
    assert sink.copied_clippings[-1].build_preview_text() == "third"


def test_external_empty_clipboard_disarms_stack_without_removing_history() -> None:
    service, sink, _, _ = _build_service()
    service.handle_new_clipboard_content(RawClipboardData(text="keep me"))
    service.set_stack_paste_mode_enabled(True)

    service.handle_new_clipboard_content(RawClipboardData())
    service.consume_prepared_clipping_after_paste()

    assert len(service.list_clippings_newest_first()) == 1
    assert sink.clear_count == 0


def test_deleting_prepared_stack_item_preloads_the_next_item() -> None:
    service, sink, _, _ = _build_service()
    service.handle_new_clipboard_content(RawClipboardData(text="first"))
    service.handle_new_clipboard_content(RawClipboardData(text="second"))
    prepared = service.list_clippings_newest_first()[0]
    service.set_stack_paste_mode_enabled(True)

    service.delete_clipping_by_id(prepared.id)

    assert sink.copied_clippings[-1].build_preview_text() == "first"


def test_disabling_stack_mode_leaves_prepared_clipboard_and_history_unchanged() -> None:
    service, sink, _, _ = _build_service()
    service.handle_new_clipboard_content(RawClipboardData(text="keep me"))
    service.set_stack_paste_mode_enabled(True)

    service.set_stack_paste_mode_enabled(False)
    service.consume_prepared_clipping_after_paste()

    assert service.is_stack_paste_mode_enabled() is False
    assert len(service.list_clippings_newest_first()) == 1
    assert len(sink.copied_clippings) == 1
    assert sink.clear_count == 0


def test_stack_paste_mode_observers_receive_distinct_state_changes() -> None:
    service, _, _, _ = _build_service()
    observer = RecordingStackPasteModeObserver()
    service.register_stack_paste_mode_observer(observer)

    service.set_stack_paste_mode_enabled(True)
    service.set_stack_paste_mode_enabled(True)
    service.set_stack_paste_mode_enabled(False)

    assert observer.enabled_states == [True, False]
