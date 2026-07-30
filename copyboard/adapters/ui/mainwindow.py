"""The viewer window: a scrollable, newest-first list of recent clippings.

Implements the application's ``HistoryObserver``. History-change notifications are bounced through a
Qt signal with a queued connection, so the list refresh always runs on the GUI thread regardless of
which thread produced the change. A ``QTimer`` periodically asks the service to drop expired
clippings, which drives time-based retention even when nothing new is copied.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import QPushButton, QScrollArea, QVBoxLayout, QWidget

from copyboard.adapters.ui.clippingwidget import ClippingWidget
from copyboard.application.copyboardservice import CopyboardService
from copyboard.application.events import HistoryChangeEvent
from copyboard.config import UIConfig

_DEFAULT_PRUNE_INTERVAL_MS = 1000


class MainWindow(QWidget):
    """Shows the live clipping history and wires row actions back to the service."""

    _history_changed = Signal()
    _stack_paste_mode_changed = Signal(bool)
    _current_clipboard_clipping_changed = Signal()

    def __init__(
        self,
        service: CopyboardService,
        ui_config: UIConfig | None = None,
        prune_interval_ms: int = _DEFAULT_PRUNE_INTERVAL_MS,
    ) -> None:
        super().__init__()
        self._service = service
        self._ui_config = ui_config or UIConfig()
        self.setWindowTitle("Copyboard")
        self.resize(420, 560)

        outer_layout = QVBoxLayout(self)
        self._stack_paste_button = QPushButton()
        self._stack_paste_button.setObjectName("stackPasteToggleButton")
        self._stack_paste_button.setCheckable(True)
        self._stack_paste_button.clicked.connect(self._service.set_stack_paste_mode_enabled)
        outer_layout.addWidget(self._stack_paste_button)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        self._list_container = QWidget()
        self._list_layout = QVBoxLayout(self._list_container)
        scroll_area.setWidget(self._list_container)
        outer_layout.addWidget(scroll_area)

        service.register_observer(self)
        service.register_stack_paste_mode_observer(self)
        service.register_current_clipboard_observer(self)
        self._history_changed.connect(
            self._refresh_clipping_list, Qt.ConnectionType.QueuedConnection
        )
        self._stack_paste_mode_changed.connect(
            self._synchronize_stack_paste_button, Qt.ConnectionType.QueuedConnection
        )
        self._current_clipboard_clipping_changed.connect(
            self._refresh_clipping_list, Qt.ConnectionType.QueuedConnection
        )

        self._prune_timer = QTimer(self)
        self._prune_timer.timeout.connect(self._service.remove_expired_clippings)
        self._prune_timer.start(prune_interval_ms)

        self._synchronize_stack_paste_button(service.is_stack_paste_mode_enabled())
        self._refresh_clipping_list()

    def on_history_changed(self, event: HistoryChangeEvent) -> None:
        self._history_changed.emit()

    def on_stack_paste_mode_changed(self, enabled: bool) -> None:
        self._stack_paste_mode_changed.emit(enabled)

    def on_current_clipboard_clipping_changed(self, clipping_id: str | None) -> None:
        self._current_clipboard_clipping_changed.emit()

    def toggle_visibility(self) -> None:
        """Hide only when already frontmost; otherwise surface the window to the front.

        Pressing the hotkey while the window sits behind another app should raise it, not hide it,
        so we hide only when it is both visible and the active window.
        """
        if self.isVisible() and self.isActiveWindow():
            self.hide()
            return
        self.bring_to_front()

    def bring_to_front(self) -> None:
        """Show, un-minimise, and take focus so the window pops in front of other apps."""
        self.setWindowState(
            (self.windowState() & ~Qt.WindowState.WindowMinimized) | Qt.WindowState.WindowActive
        )
        self.show()
        self.raise_()
        self.activateWindow()

    def _refresh_clipping_list(self) -> None:
        self._clear_list_layout()
        current_clipping_id = self._service.get_current_clipboard_clipping_id()
        for clipping in self._service.list_clippings_newest_first():
            self._list_layout.addWidget(
                ClippingWidget(
                    clipping,
                    self._service.recopy_clipping_by_id,
                    self._service.delete_clipping_by_id,
                    actions_on_right_click=self._ui_config.actions_on_right_click,
                    is_current_clipboard_item=clipping.id == current_clipping_id,
                )
            )
        self._list_layout.addStretch(1)

    def _synchronize_stack_paste_button(self, enabled: bool) -> None:
        self._stack_paste_button.setChecked(enabled)
        state_text = "On" if enabled else "Off"
        self._stack_paste_button.setText(f"Stack paste: {state_text}")

    def _clear_list_layout(self) -> None:
        while self._list_layout.count():
            item = self._list_layout.takeAt(0)
            if item is None:
                continue
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
