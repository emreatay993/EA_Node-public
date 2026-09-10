from __future__ import annotations

import logging
import traceback
from typing import Any

from PyQt6.QtCore import QObject, QThread, pyqtSignal

from ea_node_editor.nodes.bootstrap import build_default_registry
from ea_node_editor.nodes.registry import NodeRegistry
from ea_node_editor.telemetry.startup_profile import phase


"""
Background ``NodeRegistry`` loader used by the splash screen.

``build_default_registry()`` is pure Python (see ``ea_node_editor/nodes/bootstrap.py``)
and does plugin discovery and dynamic imports.
It dominates shell startup (~3.6s measured 2026-04-18 — see
``PLANS_TO_IMPLEMENT/in_progress/splash_threaded_plugin_registry.md``), but
touches zero Qt widgets, so it runs off the GUI thread while the splash animates.

**Invariant:** ``build_default_registry()`` must stay Qt-widget-free. Any future
plugin registration that needs a ``QWidget`` / ``QPainter`` / ``QQuick*`` object
must either defer that work to the main thread or break this loader.
"""


logger = logging.getLogger(__name__)


class _RegistryWorker(QObject):
    ready = pyqtSignal(object)  # NodeRegistry
    failed = pyqtSignal(str)  # formatted traceback

    def __init__(self, *, preferences_document: Any = None) -> None:
        super().__init__()
        self._preferences_document = preferences_document

    def run(self) -> None:
        try:
            with phase("thread.build_default_registry"):
                registry = build_default_registry(preferences_document=self._preferences_document)
        except Exception:
            tb = traceback.format_exc()
            logger.exception("Background registry build failed")
            self.failed.emit(tb)
            return
        self.ready.emit(registry)


class RegistryLoader(QObject):
    """One-shot background loader for the default node registry.

    Owns a ``QThread`` + ``_RegistryWorker``. Starts on ``start()``, emits
    exactly one of ``ready(NodeRegistry)`` or ``failed(str)``, and tears down
    the thread cleanly before re-emitting on the caller's thread.
    """

    ready = pyqtSignal(object)  # NodeRegistry
    failed = pyqtSignal(str)

    def __init__(self, parent: QObject | None = None, *, preferences_document: Any = None) -> None:
        super().__init__(parent)
        self._thread = QThread(self)
        self._worker = _RegistryWorker(preferences_document=preferences_document)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.ready.connect(self._on_ready)
        self._worker.failed.connect(self._on_failed)
        # Ensure the thread exits once work is done, then the worker is cleaned up.
        self._worker.ready.connect(self._thread.quit)
        self._worker.failed.connect(self._thread.quit)
        self._thread.finished.connect(self._worker.deleteLater)

    def start(self) -> None:
        self._thread.start()

    def _on_ready(self, registry: NodeRegistry) -> None:
        self.ready.emit(registry)

    def _on_failed(self, tb: str) -> None:
        self.failed.emit(tb)


__all__ = ["RegistryLoader"]
