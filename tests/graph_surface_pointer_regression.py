from __future__ import annotations

import atexit
import gc
import itertools
import multiprocessing
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
import threading
import time
import traceback
import unittest

_REPO_ROOT = Path(__file__).resolve().parents[1]
_PROBE_LOCK = threading.RLock()
_PROBE_REQUEST_IDS = itertools.count(1)
_QML_PROBE_TIMEOUT_SECONDS = 60.0
_worker_process = None
_worker_connection = None
_worker_log_path: Path | None = None
_worker_owner_pid: int | None = None

QML_POINTER_REGRESSION_HELPERS = textwrap.dedent(
    """
    from PyQt6.QtCore import QPoint, QPointF, Qt
    from PyQt6.QtQuick import QQuickItem, QQuickWindow
    from PyQt6.QtTest import QTest

    def variant_value(value):
        return value.toVariant() if hasattr(value, "toVariant") else value

    def variant_list(value):
        normalized = variant_value(value)
        if normalized is None:
            return []
        return list(normalized)

    def rect_field(rect, key):
        normalized = variant_value(rect)
        if isinstance(normalized, dict):
            return float(normalized[key])
        try:
            value = normalized[key]
        except Exception:
            value = getattr(normalized, key)
        value = variant_value(value)
        return float(value() if callable(value) else value)

    def walk_items(item):
        if isinstance(item, QQuickItem):
            yield item
            for child in item.childItems():
                yield from walk_items(child)

    def named_item(root, object_name, property_key=None):
        for child in walk_items(root):
            if child.objectName() != object_name:
                continue
            if property_key is None or str(child.property("propertyKey")) == property_key:
                return child
        raise AssertionError(f"Missing object {object_name!r} propertyKey={property_key!r}")

    def named_child_items(root, object_name):
        return [child for child in walk_items(root) if child.objectName() == object_name]

    def item_scene_point(item, x_factor=0.5, y_factor=0.5):
        scene_point = item.mapToScene(QPointF(item.width() * x_factor, item.height() * y_factor))
        return QPoint(round(scene_point.x()), round(scene_point.y()))

    def host_scene_point(host, local_x, local_y):
        scene_point = host.mapToScene(QPointF(local_x, local_y))
        return QPoint(round(scene_point.x()), round(scene_point.y()))

    def settle_events(cycles=1):
        for _index in range(max(1, int(cycles))):
            app.processEvents()

    def attach_host_to_window(host, width=480, height=360):
        window = QQuickWindow()
        window.resize(int(width), int(height))
        host.setParentItem(window.contentItem())
        window.show()
        app.processEvents()
        return window

    def dispose_host_window(host, window):
        if window is not None:
            window.close()
        if host is not None:
            host.setParentItem(None)
            host.deleteLater()
        if window is not None:
            window.deleteLater()
        app.processEvents()

    def hover_host_local_point(window, host, local_x, local_y, settle_cycles=5):
        point = host_scene_point(host, local_x, local_y)
        QTest.mouseMove(window, host_scene_point(host, -1.0, -1.0))
        settle_events(1)
        QTest.mouseMove(window, point)
        settle_events(settle_cycles)
        return point

    def host_pointer_events(host):
        clicked = []
        opened = []
        contexts = []
        host.nodeClicked.connect(lambda node_id, additive: clicked.append((node_id, additive)))
        host.nodeOpenRequested.connect(lambda node_id: opened.append(node_id))
        host.nodeContextRequested.connect(
            lambda node_id, local_x, local_y: contexts.append((node_id, local_x, local_y))
        )
        return {"clicked": clicked, "opened": opened, "contexts": contexts}

    def mouse_click(window, point, button=Qt.MouseButton.LeftButton):
        QTest.mouseClick(window, button, Qt.KeyboardModifier.NoModifier, point)
        app.processEvents()

    def mouse_double_click(window, point, button=Qt.MouseButton.LeftButton):
        QTest.mouseDClick(window, button, Qt.KeyboardModifier.NoModifier, point)
        app.processEvents()

    def assert_host_pointer_routing(
        host,
        window,
        control_point,
        body_point,
        expected_node_id,
        expected_body_local=None,
    ):
        events = host_pointer_events(host)

        mouse_click(window, control_point)
        mouse_double_click(window, control_point)
        mouse_click(window, control_point, Qt.MouseButton.RightButton)

        assert events["clicked"] == []
        assert events["opened"] == []
        assert events["contexts"] == []

        mouse_click(window, body_point)
        mouse_double_click(window, body_point)
        mouse_click(window, body_point, Qt.MouseButton.RightButton)

        assert len(events["clicked"]) >= 1
        assert all(entry == (expected_node_id, False) for entry in events["clicked"])
        assert events["opened"] == [expected_node_id]
        assert len(events["contexts"]) == 1
        assert events["contexts"][0][0] == expected_node_id

        if expected_body_local is not None:
            expected_x, expected_y = expected_body_local
            assert abs(float(events["contexts"][0][1]) - float(expected_x)) < 0.5
            assert abs(float(events["contexts"][0][2]) - float(expected_y)) < 0.5
    """
)


def _read_native_log(log_file) -> str:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.flush()
        except Exception:
            pass
    log_file.flush()
    log_file.seek(0)
    return log_file.read().decode("utf-8", errors="replace").strip()


def _restore_probe_baseline(app, baseline: dict[str, object]) -> None:
    from PyQt6.QtCore import QCoreApplication, QEvent
    from PyQt6.QtWidgets import QApplication

    focus_widget = app.focusWidget()
    if focus_widget is not None:
        focus_widget.clearFocus()
    for widget in list(app.topLevelWidgets()):
        try:
            widget.close()
            widget.deleteLater()
        except RuntimeError:
            pass
    for window in list(app.topLevelWindows()):
        try:
            window.close()
            window.deleteLater()
        except RuntimeError:
            pass
    while QApplication.overrideCursor() is not None:
        QApplication.restoreOverrideCursor()
    for _ in range(3):
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        app.processEvents()
    gc.collect()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()

    os.chdir(baseline["cwd"])
    baseline_env = baseline["env"]
    for key in set(os.environ) - set(baseline_env):
        del os.environ[key]
    os.environ.update(baseline_env)
    app.setQuitOnLastWindowClosed(baseline["quit_on_last_window"])
    app.setApplicationName(baseline["application_name"])
    app.setApplicationDisplayName(baseline["application_display_name"])
    app.setOrganizationName(baseline["organization_name"])
    app.setOrganizationDomain(baseline["organization_domain"])
    app.setStyleSheet(baseline["style_sheet"])


def _qml_probe_worker(connection, log_path: str, repo_root: str) -> None:
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")
    os.chdir(repo_root)

    with open(log_path, "w+b", buffering=0) as native_log:
        for stream in (sys.stdout, sys.stderr):
            try:
                stream.flush()
            except Exception:
                pass
        os.dup2(native_log.fileno(), 1)
        os.dup2(native_log.fileno(), 2)
        sys.stdout = open(1, "w", encoding="utf-8", errors="replace", buffering=1, closefd=False)
        sys.stderr = open(2, "w", encoding="utf-8", errors="replace", buffering=1, closefd=False)

        try:
            from PyQt6.QtWidgets import QApplication

            app = QApplication.instance() or QApplication([])
            baseline = {
                "cwd": repo_root,
                "env": os.environ.copy(),
                "quit_on_last_window": app.quitOnLastWindowClosed(),
                "application_name": app.applicationName(),
                "application_display_name": app.applicationDisplayName(),
                "organization_name": app.organizationName(),
                "organization_domain": app.organizationDomain(),
                "style_sheet": app.styleSheet(),
            }
            connection.send(("ready", 0, ""))
        except BaseException:
            traceback.print_exc()
            connection.send(("startup_error", 0, _read_native_log(native_log)))
            return

        while True:
            try:
                message = connection.recv()
            except EOFError:
                return
            if message[0] == "shutdown":
                return

            _, request_id, script = message
            native_log.seek(0)
            native_log.truncate()
            connection.send(("running", request_id, ""))
            namespace = {"__name__": "__main__", "__builtins__": __builtins__}
            try:
                exec(script, namespace, namespace)
            except BaseException:
                traceback.print_exc()
                connection.send(("error", request_id, _read_native_log(native_log)))
                return

            connection.send(("completed", request_id, _read_native_log(native_log)))
            connection.send(("cleanup", request_id, ""))
            namespace.clear()
            try:
                _restore_probe_baseline(app, baseline)
            except BaseException:
                traceback.print_exc()
                connection.send(("cleanup_error", request_id, _read_native_log(native_log)))
                return
            connection.send(("ready", request_id, ""))


def _remove_worker_log(path: Path | None) -> None:
    if path is None:
        return
    for attempt in range(20):
        try:
            path.unlink(missing_ok=True)
            return
        except OSError:
            if attempt == 19:
                raise
            time.sleep(0.01)


def _discard_qml_probe_worker(*, graceful: bool = False) -> None:
    global _worker_process, _worker_connection, _worker_log_path, _worker_owner_pid

    process = _worker_process
    connection = _worker_connection
    log_path = _worker_log_path
    owns_worker = _worker_owner_pid == os.getpid()
    _worker_process = None
    _worker_connection = None
    _worker_log_path = None
    _worker_owner_pid = None

    try:
        if (
            connection is not None
            and graceful
            and owns_worker
            and process is not None
            and process.pid is not None
            and process.is_alive()
        ):
            try:
                connection.send(("shutdown", 0, ""))
            except (BrokenPipeError, EOFError, OSError):
                pass
    finally:
        if connection is not None:
            try:
                connection.close()
            except OSError:
                pass

    try:
        if process is not None and owns_worker and process.pid is not None:
            process.join(2.0)
            if process.is_alive():
                try:
                    process.terminate()
                except PermissionError as error:
                    if os.name != "nt" or getattr(error, "winerror", None) != 5:
                        raise
                process.join(5.0)
                if process.is_alive() and os.name != "nt":
                    process.kill()
                    process.join(5.0)
    finally:
        if owns_worker:
            try:
                _remove_worker_log(log_path)
            except OSError:
                pass


def _stop_qml_probe_worker() -> None:
    with _PROBE_LOCK:
        _discard_qml_probe_worker(graceful=True)


def _next_worker_message(deadline: float):
    while _worker_process is not None and _worker_connection is not None:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError
        if _worker_connection.poll(min(0.02, remaining)):
            try:
                return _worker_connection.recv()
            except (EOFError, OSError):
                return None
        if not _worker_process.is_alive():
            return None
    return None


def _worker_log_contents() -> str:
    if _worker_log_path is None:
        return ""
    try:
        return _worker_log_path.read_text(encoding="utf-8", errors="replace").strip()
    except (FileNotFoundError, PermissionError, OSError):
        return ""


def _fail_qml_probe_worker_death(test_case: unittest.TestCase, label: str) -> None:
    process = _worker_process
    if process is not None and process.pid is not None:
        process.join(1.0)
    exit_code = process.exitcode if process is not None else None
    details = _worker_log_contents()
    _discard_qml_probe_worker()
    test_case.fail(f"{label} probe failed with exit code {exit_code if exit_code is not None else 1}\n{details}")


def _ensure_qml_probe_worker(test_case: unittest.TestCase, label: str) -> None:
    global _worker_process, _worker_connection, _worker_log_path, _worker_owner_pid

    if (
        _worker_process is not None
        and _worker_owner_pid == os.getpid()
        and _worker_process.is_alive()
    ):
        return
    _discard_qml_probe_worker()
    fd, log_name = tempfile.mkstemp(prefix="corex-qml-probe-", suffix=".log")
    _worker_log_path = Path(log_name)
    _worker_owner_pid = os.getpid()
    child_connection = None
    bootstrap_started_at = time.monotonic()
    bootstrap_deadline = bootstrap_started_at + _QML_PROBE_TIMEOUT_SECONDS
    try:
        os.close(fd)
        fd = -1
        context = multiprocessing.get_context("spawn")
        parent_connection, child_connection = context.Pipe()
        _worker_connection = parent_connection
        process = context.Process(
            target=_qml_probe_worker,
            args=(child_connection, log_name, str(_REPO_ROOT)),
            daemon=True,
        )
        _worker_process = process
        process.start()
    except BaseException:
        if fd >= 0:
            try:
                os.close(fd)
            except OSError:
                pass
        _discard_qml_probe_worker()
        raise
    finally:
        if child_connection is not None:
            try:
                child_connection.close()
            except OSError:
                pass
    try:
        message = _next_worker_message(bootstrap_deadline)
    except TimeoutError:
        elapsed = time.monotonic() - bootstrap_started_at
        details = _worker_log_contents() or "<no native log output>"
        log_path = _worker_log_path
        _discard_qml_probe_worker()
        test_case.fail(
            f"{label} probe timed out after {_QML_PROBE_TIMEOUT_SECONDS:g}s "
            f"(elapsed={elapsed:.3f}s)\n"
            "request=bootstrap state=starting\n"
            f"native log path: {log_path}\n"
            f"native log:\n{details}"
        )
    except BaseException:
        _discard_qml_probe_worker()
        raise
    if message is not None and message[0] == "ready":
        return
    details = message[2] if message is not None else _worker_log_contents()
    if message is None:
        process.join(1.0)
    exit_code = 1 if message is not None or process.exitcode is None else process.exitcode
    _discard_qml_probe_worker()
    test_case.fail(f"{label} probe failed with exit code {exit_code}\n{details}")


def run_qml_probe(test_case: unittest.TestCase, label: str, *blocks: str) -> None:
    script = "\n".join(textwrap.dedent(block).strip("\n") for block in blocks if block)
    with _PROBE_LOCK:
        _ensure_qml_probe_worker(test_case, label)
        request_id = next(_PROBE_REQUEST_IDS)
        request_started_at = time.monotonic()
        deadline = request_started_at + _QML_PROBE_TIMEOUT_SECONDS
        try:
            _worker_connection.send(("run", request_id, script))
        except (BrokenPipeError, EOFError, OSError):
            _fail_qml_probe_worker_death(test_case, label)
        completed = False
        request_state = "sent"
        while True:
            try:
                message = _next_worker_message(deadline)
            except TimeoutError:
                elapsed = time.monotonic() - request_started_at
                details = _worker_log_contents() or "<no native log output>"
                log_path = _worker_log_path
                _discard_qml_probe_worker()
                test_case.fail(
                    f"{label} probe timed out after {_QML_PROBE_TIMEOUT_SECONDS:g}s "
                    f"(elapsed={elapsed:.3f}s)\n"
                    f"request={request_id} state={request_state}\n"
                    f"native log path: {log_path}\n"
                    f"native log:\n{details}"
                )
            if message is None:
                if completed:
                    _discard_qml_probe_worker()
                    return
                _fail_qml_probe_worker_death(test_case, label)

            state, response_id, details = message
            request_state = state
            if response_id != request_id:
                _discard_qml_probe_worker()
                test_case.fail(f"{label} probe failed with exit code 1\nunexpected worker response")
            if state == "running" or state == "cleanup":
                continue
            if state == "completed":
                completed = True
                continue
            if state == "ready" and completed:
                return
            if state == "cleanup_error" and completed:
                _discard_qml_probe_worker()
                return
            if state == "error":
                _discard_qml_probe_worker()
                test_case.fail(f"{label} probe failed with exit code 1\n{details}")
            _discard_qml_probe_worker()
            test_case.fail(f"{label} probe failed with exit code 1\nunexpected worker state {state!r}")


atexit.register(_stop_qml_probe_worker)


def assert_no_graph_surface_pointer_regressions(test_case: unittest.TestCase) -> None:
    failures = graph_surface_pointer_audit_failures()
    if failures:
        test_case.fail("\n\n".join(failures))


def graph_surface_pointer_audit_failures() -> list[str]:
    graph_dir = _REPO_ROOT / "ea_node_editor" / "ui_qml" / "components" / "graph"
    passive_dir = graph_dir / "passive"
    surface_files = [
        graph_dir / "GraphInlinePropertiesLayer.qml",
        graph_dir / "GraphStandardNodeSurface.qml",
        *sorted(passive_dir.glob("*Surface.qml")),
    ]
    failures: list[str] = []

    hover_proxy_matches = _search_pattern(
        r"hoverActionHitRect|graphNodeSurfaceHoverActionButton",
        [graph_dir, passive_dir],
    )
    if hover_proxy_matches:
        failures.append(
            "Removed hover-proxy compatibility shims reappeared:\n"
            + "\n".join(hover_proxy_matches)
        )

    tap_handler_matches = _search_pattern(r"\bTapHandler\s*\{", surface_files)
    if tap_handler_matches:
        failures.append(
            "Unexpected TapHandler usage in graph-surface QML:\n"
            + "\n".join(tap_handler_matches)
        )

    unexpected_mouse_areas: list[str] = []
    for path in surface_files:
        matches = _search_pattern(r"\bMouseArea\s*\{", [path])
        if not matches:
            continue
        if path.name == "GraphMediaPanelSurface.qml":
            if len(matches) != 1:
                unexpected_mouse_areas.append(
                    f"{path.relative_to(_REPO_ROOT)}: expected exactly one crop-handle MouseArea, found {len(matches)}"
                )
            text = path.read_text(encoding="utf-8")
            if 'objectName: "graphNodeMediaCropHandleMouseArea"' not in text:
                unexpected_mouse_areas.append(
                    f"{path.relative_to(_REPO_ROOT)}: allowed crop-handle MouseArea objectName is missing"
                )
            if "targetItem: handleMouseArea" not in text:
                unexpected_mouse_areas.append(
                    f"{path.relative_to(_REPO_ROOT)}: crop-handle MouseArea is no longer tied to GraphSurfaceInteractiveRegion"
                )
            continue
        if path.name == "GraphNativeExplorerSurface.qml":
            if len(matches) != 2:
                unexpected_mouse_areas.append(
                    f"{path.relative_to(_REPO_ROOT)}: expected exactly two registered folder-explorer MouseAreas, found {len(matches)}"
                )
            text = path.read_text(encoding="utf-8")
            required_snippets = {
                'objectName: "graphFolderExplorerRowMouseArea"': "row MouseArea objectName is missing",
                'objectName: "graphFolderExplorerHeaderMouseArea"': "header MouseArea objectName is missing",
                "targetItem: rowMouseArea": "row MouseArea is no longer tied to GraphSurfaceInteractiveRegion",
                "targetItem: headerMouseArea": "header MouseArea is no longer tied to GraphSurfaceInteractiveRegion",
            }
            for snippet, message in required_snippets.items():
                if snippet not in text:
                    unexpected_mouse_areas.append(
                        f"{path.relative_to(_REPO_ROOT)}: {message}"
                    )
            continue
        unexpected_mouse_areas.extend(matches)

    if unexpected_mouse_areas:
        failures.append(
            "Unexpected raw MouseArea usage in graph-surface QML:\n"
            + "\n".join(unexpected_mouse_areas)
        )

    return failures


def _expand_scan_paths(paths: list[Path]) -> list[Path]:
    expanded: list[Path] = []
    for path in paths:
        if path.is_dir():
            expanded.extend(sorted(path.rglob("*.qml")))
        else:
            expanded.append(path)
    return expanded


def _search_pattern(pattern: str, paths: list[Path]) -> list[str]:
    if shutil.which("rg"):
        scan_paths: list[str] = []
        for path in paths:
            try:
                scan_paths.append(path.relative_to(_REPO_ROOT).as_posix())
            except ValueError:
                scan_paths.append(str(path))
        result = subprocess.run(
            ["rg", "--with-filename", "-n", pattern, *scan_paths],
            cwd=_REPO_ROOT,
            capture_output=True,
            text=True,
        )
        if result.returncode not in (0, 1):
            raise AssertionError(
                f"rg audit failed for pattern {pattern!r} with exit code {result.returncode}: {result.stderr.strip()}"
            )
        return [line.strip() for line in result.stdout.splitlines() if line.strip()]

    compiled = re.compile(pattern)
    matches: list[str] = []
    for path in _expand_scan_paths(paths):
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if compiled.search(line):
                matches.append(f"{path.relative_to(_REPO_ROOT)}:{line_number}:{line.strip()}")
    return matches
