"""Adapter integration: the Qt clipboard source de-dupes repeat OS events and captures images.

Runs headless on the offscreen platform. The Windows clipboard fires ``dataChanged`` several times
for a single copy; these tests drive that handler directly to prove the de-dup collapses repeats.
"""

from __future__ import annotations

from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication

from copyboard.adapters.clipboardechoguard import ClipboardEchoGuard
from copyboard.adapters.qt.qtclipboard import QtClipboardSource
from copyboard.domain.content import RawClipboardData


def test_repeated_change_events_for_one_copy_are_captured_once(qt_app: QApplication) -> None:
    clipboard = qt_app.clipboard()
    source = QtClipboardSource(clipboard, ClipboardEchoGuard())
    received: list[RawClipboardData] = []
    source.set_new_content_listener(received.append)

    clipboard.setText("git status")
    source._handle_clipboard_data_changed()  # simulate the extra OS fires for one copy
    source._handle_clipboard_data_changed()

    clipboard.setText("git log")
    source._handle_clipboard_data_changed()
    source._handle_clipboard_data_changed()

    assert [content.text for content in received] == ["git status", "git log"]


def test_image_on_clipboard_is_captured_and_encoded(qt_app: QApplication) -> None:
    clipboard = qt_app.clipboard()
    source = QtClipboardSource(clipboard, ClipboardEchoGuard())

    image = QImage(4, 3, QImage.Format.Format_RGB32)
    image.fill(QColor("red"))
    clipboard.setImage(image)

    content = source.read_current_content()

    assert content.has_image()
    assert content.image is not None
    assert content.image.size_bytes > 0
    assert content.image.image_format == "png"
