"""Shared Qt fixtures. Forces the offscreen platform so UI/adapter tests run headless."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from collections.abc import Iterator

import pytest
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="session")
def qt_app() -> Iterator[QApplication]:
    existing = QApplication.instance()
    app = existing if isinstance(existing, QApplication) else QApplication([])
    yield app
    # Explicitly destroy all top-level widgets before Python's shutdown GC runs.
    # Tests that create MainWindow objects leave a window↔service reference cycle
    # that Python 3.11/3.12 GC collects only during interpreter shutdown, when Qt's
    # X11/compositor state is partially torn down — causing a SIGSEGV. Calling
    # shiboken6.delete() here destroys the C++ objects while QApplication is still
    # fully alive, so the Python wrappers become safe no-op shells for the GC.
    import shiboken6

    for widget in list(app.topLevelWidgets()):
        if shiboken6.isValid(widget):
            widget.close()
            shiboken6.delete(widget)
