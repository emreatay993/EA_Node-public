from __future__ import annotations

import logging
import threading
from typing import Any

import plotly.graph_objects as go
from dash import Dash, Input, Output, dcc, html, no_update
from werkzeug.serving import make_server


GRAPH_ID = "resampled-plot"


class LocalResamplerDashHost:
    """Serve one resampler-backed Plotly figure from localhost.

    Plotly Resampler needs callbacks for dynamic zoom-window aggregation. This
    tiny Dash host keeps those callbacks local to 127.0.0.1 and serves Dash
    assets from installed Python packages, so it works without internet access.
    """

    def __init__(self):
        self._figure: Any | None = None
        self._version = 0
        self._lock = threading.RLock()
        self._server: Any | None = None
        self._thread: threading.Thread | None = None
        self._host = "127.0.0.1"
        self._port: int | None = None
        self._app = Dash(
            __name__,
            serve_locally=True,
            external_scripts=[],
            external_stylesheets=[],
            suppress_callback_exceptions=True,
            title="Sensor Data Plot",
        )
        self._app.layout = self._layout
        self._register_callbacks()

    def set_figure(self, figure: Any) -> str:
        with self._lock:
            self._figure = figure
            self._version += 1
            version = self._version
        self.start()
        return f"http://{self._host}:{self._port}/?v={version}"

    def set_trace_visibility(self, mask: list[bool] | tuple[bool, ...]) -> None:
        with self._lock:
            figure = self._figure
            if figure is None:
                return
            for trace, visible in zip(figure.data, mask):
                trace.visible = bool(visible)

    def start(self) -> None:
        if self._server is not None:
            return
        logging.getLogger("werkzeug").setLevel(logging.ERROR)
        self._server = make_server(self._host, 0, self._app.server, threaded=True)
        self._port = int(self._server.server_port)
        self._thread = threading.Thread(target=self._server.serve_forever, name="sensor-compare-plotly-resampler", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._server is None:
            return
        self._server.shutdown()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        self._server = None
        self._thread = None
        self._port = None

    def _layout(self) -> html.Div:
        with self._lock:
            figure = self._figure or go.Figure()
        return html.Div(
            dcc.Graph(
                id=GRAPH_ID,
                figure=figure,
                config={"responsive": True, "displaylogo": False},
                style={"width": "100vw", "height": "100vh"},
            ),
            style={"margin": "0", "padding": "0", "width": "100vw", "height": "100vh", "background": "#ffffff"},
        )

    def _register_callbacks(self) -> None:
        @self._app.callback(
            Output(GRAPH_ID, "figure", allow_duplicate=True),
            Input(GRAPH_ID, "relayoutData"),
            prevent_initial_call=True,
        )
        def _update_resampled_figure(relayout_data: dict[str, Any] | None) -> Any:
            if not relayout_data:
                return no_update
            with self._lock:
                figure = self._figure
            updater = getattr(figure, "construct_update_data_patch", None)
            if not callable(updater):
                return no_update
            try:
                return updater(relayout_data)
            except Exception:
                return no_update
