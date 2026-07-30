"""A single row in the viewer: a clipping's preview plus Copy / Delete actions.

Pure view code. It shows the clipping's ``build_preview_text`` (or, for images, a thumbnail rendered
from the temp-file path) under a muted timestamp. User actions are forwarded through injected
callbacks so the widget never touches the service or domain logic directly.

Two interaction modes are supported (chosen at construction time):
- **Inline buttons** (default): Copy and Delete buttons appear to the right of each row.
- **Right-click menu**: no buttons are shown; a context menu appears on right-click instead.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QContextMenuEvent, QDrag, QMouseEvent, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from copyboard.adapters.qt.clippingdragdata import build_drag_mime_data
from copyboard.domain.clipping import Clipping, ImageClipping

_THUMBNAIL_WIDTH = 160
_THUMBNAIL_HEIGHT = 90
_CURRENT_CLIPBOARD_BORDER_STYLESHEET = (
    "#currentClipboardClipping { border: 2px solid palette(highlight); }"
)


class ClippingWidget(QWidget):
    """Renders one clipping and forwards Copy/Delete to the given callbacks by clipping id."""

    def __init__(
        self,
        clipping: Clipping,
        on_recopy: Callable[[str], None],
        on_delete: Callable[[str], None],
        actions_on_right_click: bool = True,
        is_current_clipboard_item: bool = False,
    ) -> None:
        super().__init__()
        # Required for Qt to paint a stylesheet `background` on a plain QWidget subclass.
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setProperty("currentClipboardItem", is_current_clipboard_item)
        if is_current_clipboard_item:
            self.setObjectName("currentClipboardClipping")
            self.setStyleSheet(_CURRENT_CLIPBOARD_BORDER_STYLESHEET)
            self.setToolTip("Currently on the system clipboard")
        self._clipping_id = clipping.id
        self._clipboard_payload = clipping.to_clipboard_payload()
        self._on_recopy = on_recopy
        self._on_delete = on_delete
        self._actions_on_right_click = actions_on_right_click
        self._drag_start_position: QPoint | None = None

        row = QHBoxLayout(self)
        row.addLayout(self._build_content_column(clipping), stretch=1)
        if not actions_on_right_click:
            row.addWidget(self._build_copy_button())
            row.addWidget(self._build_delete_button())

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start_position = event.position().toPoint()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if not event.buttons() & Qt.MouseButton.LeftButton:
            return
        if self._drag_start_position is None:
            return
        moved_far_enough = (
            event.position().toPoint() - self._drag_start_position
        ).manhattanLength() >= QApplication.startDragDistance()
        if moved_far_enough:
            self._start_drag()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        # _start_drag clears _drag_start_position; if it is still set here the press never became
        # a drag, so this is a plain click — copy in right-click mode.
        if (
            event.button() == Qt.MouseButton.LeftButton
            and self._drag_start_position is not None
            and self._actions_on_right_click
        ):
            self._drag_start_position = None
            self._request_recopy()

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:
        menu = QMenu(self)
        menu.addAction("Copy").triggered.connect(self._request_recopy)
        menu.addAction("Delete").triggered.connect(self._request_delete)
        menu.exec(event.globalPos())

    def _start_drag(self) -> None:
        self._drag_start_position = None
        drag = QDrag(self)
        drag.setMimeData(build_drag_mime_data(self._clipboard_payload))
        drag.exec(Qt.DropAction.CopyAction)

    def _build_content_column(self, clipping: Clipping) -> QVBoxLayout:
        column = QVBoxLayout()
        timestamp = QLabel(f"{clipping.created_at:%H:%M:%S}")
        timestamp.setStyleSheet("color: gray; font-size: 11px;")
        column.addWidget(timestamp)
        column.addWidget(self._build_preview_label(clipping))
        return column

    def _build_preview_label(self, clipping: Clipping) -> QLabel:
        if isinstance(clipping, ImageClipping):
            return self._build_thumbnail_label(clipping)
        label = QLabel(clipping.build_preview_text())
        label.setWordWrap(True)
        return label

    def _build_thumbnail_label(self, clipping: ImageClipping) -> QLabel:
        label = QLabel()
        pixmap = QPixmap(str(clipping.path))
        if pixmap.isNull():
            label.setText(clipping.build_preview_text())
            return label
        label.setPixmap(
            pixmap.scaled(
                _THUMBNAIL_WIDTH,
                _THUMBNAIL_HEIGHT,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        return label

    def _build_copy_button(self) -> QPushButton:
        button = QPushButton("Copy")
        button.clicked.connect(self._request_recopy)
        return button

    def _build_delete_button(self) -> QPushButton:
        button = QPushButton("Delete")
        button.clicked.connect(self._request_delete)
        return button

    def _request_recopy(self) -> None:
        self._on_recopy(self._clipping_id)

    def _request_delete(self) -> None:
        self._on_delete(self._clipping_id)
