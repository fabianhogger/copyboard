"""Qt-backed clipboard adapters: capture changes and write clippings back.

``QtClipboardSource`` implements the ``ClipboardSource`` port and drives the service on every
clipboard change; ``QtClipboardSink`` implements the ``ClipboardSink`` port. Both share a
:class:`ClipboardEchoGuard` so a re-copy does not get re-captured as a new clipping.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QBuffer, QByteArray, QIODevice
from PySide6.QtGui import QClipboard, QImage, QImageWriter

from copyboard.adapters.clipboardechoguard import ClipboardEchoGuard
from copyboard.domain.clipping import Clipping
from copyboard.domain.content import ImagePayload, RawClipboardData

_DEFAULT_IMAGE_FORMAT = "png"


class QtClipboardSource:
    """Watches the system clipboard and reports new content as :class:`RawClipboardData`.

    The clipboard exposes an image as a raw in-memory ``QImage`` (there is no original file), so we
    serialise it ourselves. ``image_format`` chooses that container — the default ``png`` is
    lossless and transparency-aware, ideal for screenshots; ``jpg`` etc. work if size matters.

    Windows fires ``dataChanged`` several times for a single copy (twice from browsers, ~4 times
    from a console), so we remember the last emitted snapshot and drop consecutive duplicates.
    """

    def __init__(
        self,
        clipboard: QClipboard,
        echo_guard: ClipboardEchoGuard,
        image_format: str = _DEFAULT_IMAGE_FORMAT,
    ) -> None:
        self._clipboard = clipboard
        self._echo_guard = echo_guard
        self._image_format = image_format
        self._on_new_content: Callable[[RawClipboardData], None] | None = None
        self._last_content: RawClipboardData | None = None
        self._clipboard.dataChanged.connect(self._handle_clipboard_data_changed)

    def set_new_content_listener(self, listener: Callable[[RawClipboardData], None]) -> None:
        self._on_new_content = listener

    def read_current_content(self) -> RawClipboardData:
        image = self._clipboard.image()
        if not image.isNull():
            return RawClipboardData(image=self._encode_image(image))
        text = self._clipboard.text()
        if text:
            return RawClipboardData(text=text)
        return RawClipboardData()

    def _handle_clipboard_data_changed(self) -> None:
        content = self.read_current_content()
        if content.is_empty():
            return
        if self._echo_guard.consume_if_armed():
            self._last_content = content
            return
        if content == self._last_content:
            return
        self._last_content = content
        if self._on_new_content is not None:
            self._on_new_content(content)

    def _encode_image(self, image: QImage) -> ImagePayload:
        byte_array = QByteArray()
        buffer = QBuffer(byte_array)
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        # QImageWriter, not QImage.save(): PySide6's save() rejects a bytes format at runtime
        # despite its type stub, silently breaking image capture.
        writer = QImageWriter(buffer, QByteArray(self._image_format.upper().encode("ascii")))
        writer.write(image)
        buffer.close()
        return ImagePayload(data=bytes(byte_array.data()), image_format=self._image_format)


class QtClipboardSink:
    """Writes a clipping's payload back onto the system clipboard."""

    def __init__(self, clipboard: QClipboard, echo_guard: ClipboardEchoGuard) -> None:
        self._clipboard = clipboard
        self._echo_guard = echo_guard

    def copy_clipping_to_system_clipboard(self, clipping: Clipping) -> None:
        payload = clipping.to_clipboard_payload()
        if payload.image_path is not None:
            image = QImage(str(payload.image_path))
            if image.isNull():
                return
            self._echo_guard.arm()
            self._clipboard.setImage(image)
        elif payload.text is not None:
            self._echo_guard.arm()
            self._clipboard.setText(payload.text)
