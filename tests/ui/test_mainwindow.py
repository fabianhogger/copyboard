"""Headless smoke test: the window builds a row per clipping and Copy re-copies via the service."""

from __future__ import annotations

from datetime import datetime

from PySide6.QtWidgets import QApplication, QLabel, QPushButton

from copyboard.adapters.ui.clippingwidget import ClippingWidget
from copyboard.adapters.ui.mainwindow import MainWindow
from copyboard.application.copyboardservice import CopyboardService
from copyboard.config import RetentionPolicy
from copyboard.domain.clippingclassifier import ClippingClassifier
from copyboard.domain.clippinghistory import ClippingHistory
from copyboard.domain.content import ImagePayload, RawClipboardData
from tests.fakes import FakeClipboardSink, FakeClock, FakeVault


def _build_populated_window() -> tuple[MainWindow, FakeClipboardSink]:
    clock = FakeClock(datetime(2026, 1, 1, 12, 0, 0))
    sink = FakeClipboardSink()
    service = CopyboardService(
        classifier=ClippingClassifier(vault=FakeVault(), clock=clock),
        history=ClippingHistory(RetentionPolicy()),
        clock=clock,
        sink=sink,
    )
    service.handle_new_clipboard_content(RawClipboardData(text="hello world"))
    service.handle_new_clipboard_content(RawClipboardData(image=ImagePayload(b"x", "png")))
    return MainWindow(service, prune_interval_ms=100_000), sink


def _find_current_clipboard_rows_in_layout(window: MainWindow) -> list[ClippingWidget]:
    current_rows: list[ClippingWidget] = []
    for index in range(window._list_layout.count()):
        item = window._list_layout.itemAt(index)
        if item is None:
            continue
        widget = item.widget()
        if isinstance(widget, ClippingWidget) and widget.property("currentClipboardItem") is True:
            current_rows.append(widget)
    return current_rows


def test_window_builds_one_row_per_clipping(qt_app: QApplication) -> None:
    window, _ = _build_populated_window()
    assert len(window.findChildren(ClippingWidget)) == 2


def test_current_clipboard_row_has_a_single_solid_outline(qt_app: QApplication) -> None:
    window, _ = _build_populated_window()
    current_rows = _find_current_clipboard_rows_in_layout(window)

    assert len(current_rows) == 1
    assert current_rows[0].objectName() == "currentClipboardClipping"
    assert "#currentClipboardClipping" in current_rows[0].styleSheet()
    assert "2px solid" in current_rows[0].styleSheet()
    assert "gradient" not in current_rows[0].styleSheet()


def test_copy_button_recopies_through_the_service(qt_app: QApplication) -> None:
    window, sink = _build_populated_window()
    copy_buttons = [b for b in window.findChildren(QPushButton) if b.text() == "Copy"]

    copy_buttons[0].click()

    assert len(sink.copied_clippings) == 1


def test_copying_an_older_row_moves_the_current_clipboard_outline(qt_app: QApplication) -> None:
    window, _ = _build_populated_window()
    copy_buttons = [
        button for button in window.findChildren(QPushButton) if button.text() == "Copy"
    ]

    copy_buttons[1].click()
    qt_app.processEvents()

    current_rows = _find_current_clipboard_rows_in_layout(window)
    assert len(current_rows) == 1
    assert any(label.text() == "hello world" for label in current_rows[0].findChildren(QLabel))


def test_stack_paste_button_toggles_mode_and_shows_current_state(qt_app: QApplication) -> None:
    window, sink = _build_populated_window()
    stack_paste_button = window.findChild(QPushButton, "stackPasteToggleButton")
    assert stack_paste_button is not None
    assert stack_paste_button.text() == "Stack paste: Off"

    stack_paste_button.click()
    qt_app.processEvents()

    assert stack_paste_button.isChecked()
    assert stack_paste_button.text() == "Stack paste: On"
    assert len(sink.copied_clippings) == 1

    stack_paste_button.click()
    qt_app.processEvents()

    assert not stack_paste_button.isChecked()
    assert stack_paste_button.text() == "Stack paste: Off"


def test_toggle_from_hidden_brings_window_to_front(qt_app: QApplication) -> None:
    window, _ = _build_populated_window()
    assert not window.isVisible()

    window.toggle_visibility()

    assert window.isVisible()


def test_bring_to_front_shows_a_hidden_window(qt_app: QApplication) -> None:
    window, _ = _build_populated_window()
    window.hide()

    window.bring_to_front()

    assert window.isVisible()


def test_rows_do_not_label_the_clipping_kind(qt_app: QApplication) -> None:
    window, _ = _build_populated_window()
    # The old header was "KIND · HH:MM:SS"; the kind label (and its "·" separator) is now gone.
    assert all("·" not in label.text() for label in window.findChildren(QLabel))
