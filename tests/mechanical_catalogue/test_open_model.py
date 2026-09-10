from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from ea_node_editor.addons.mechanical.runtime import _release, execute_open_model
from ea_node_editor.addons.mechanical.backend import MechanicalOwnerBackend, deduplicate_model_systems, select_model_system
from ea_node_editor.addons.mechanical.inspection import collect_catalogue_rows
from ea_node_editor.addons.mechanical.contracts import catalogue_table, encode_selector
from ea_node_editor.addons.mechanical.property_edit import MechanicalPropertyEditAdapter
from ea_node_editor.addons.property_edit_adapters import PropertyEditAdapterContext
from ea_node_editor.runtime_contracts import DataTree
from tests.mechanical_catalogue.test_contracts import _row
from uuid import NAMESPACE_URL, uuid4, uuid5
from ea_node_editor.nodes.execution_context import NodeInputNotReadyError


class _Sessions:
    def __init__(self, result): self.result = result; self.opened = self.operated = None
    def open_session(self, **kwargs):
        self.opened = kwargs
        return SimpleNamespace(session_id="session", work_path=Path(kwargs["source_path"]).with_name("work.mechdb"), work_root=Path(kwargs["source_path"]).parent)
    def operate(self, session, **kwargs): self.operated = kwargs; return self.result
    def register_model(self, session, **kwargs): return ("model", kwargs)


def _ctx(path: Path, sessions: _Sessions):
    return SimpleNamespace(
        inputs={"file": str(path), "system": "", "mode": "background", "version": 261, "working_folder": "", "timeout_s": 600},
        properties={}, run_id="run", workspace_id="workspace", node_id="open", target_path=(2,), target_iteration=3,
        register_cancel=lambda callback: None, mechanical_sessions=sessions,
        resolve_input_path=lambda key, property_key="": path if key == "file" else None,
        resolve_path_value=lambda value: Path(value) if str(value or "").strip() else None,
        warn=lambda *args, **kwargs: None,
    )


def test_open_routes_exact_source_and_registers_selected_model(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "source.mechdb"; source.write_bytes(b"source")
    sessions = _Sessions({"status": "opened", "system_key": "standalone", "catalogue": "table"})
    monkeypatch.setattr("ea_node_editor.addons.mechanical.runtime.discover_mechanical_releases", lambda: (261,))
    result = execute_open_model(_ctx(source, sessions))
    assert result["info"] == "table" and result["model"][0] == "model"
    assert sessions.operated["operation"] == "open"
    assert sessions.operated["args"]["source_path"] == str(source.resolve())
    assert sessions.operated["args"]["work_path"].endswith("work.mechdb")


@pytest.mark.parametrize("suffix", [".dsdb", ".txt", ".rst"])
def test_open_rejects_non_public_formats_before_owner(tmp_path: Path, monkeypatch, suffix: str) -> None:
    source = tmp_path / ("source" + suffix); source.write_bytes(b"x")
    monkeypatch.setattr("ea_node_editor.addons.mechanical.runtime.discover_mechanical_releases", lambda: (261,))
    with pytest.raises(ValueError, match="must be"):
        execute_open_model(_ctx(source, _Sessions({})))


def test_open_requires_an_existing_source(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="existing regular file"):
        execute_open_model(_ctx(tmp_path / "missing.mechdb", _Sessions({})))
    ctx = _ctx(tmp_path / "missing.mechdb", _Sessions({}))
    ctx.inputs["file"] = ""
    with pytest.raises(NodeInputNotReadyError):
        execute_open_model(ctx)


def test_release_auto_explicit_and_failure_policies(monkeypatch) -> None:
    monkeypatch.setattr("ea_node_editor.addons.mechanical.runtime.discover_mechanical_releases", lambda: (271, 261))
    assert _release(0) == 271 and _release(261) == 261 and _release(271) == 271
    with pytest.raises(ValueError, match="earlier"):
        _release(252)
    with pytest.raises(RuntimeError, match="not installed"):
        _release(262)
    monkeypatch.setattr("ea_node_editor.addons.mechanical.runtime.discover_mechanical_releases", lambda: (271,))
    with pytest.raises(RuntimeError, match="not installed"):
        _release(261)
    monkeypatch.setattr("ea_node_editor.addons.mechanical.runtime.discover_mechanical_releases", lambda: ())
    with pytest.raises(RuntimeError, match="no supported"):
        _release(0)


@pytest.mark.parametrize("suffix", [".mechdat", ".mechdb", ".mechpz", ".wbpj", ".wbpz"])
@pytest.mark.parametrize("mode", ["background", "interactive"])
def test_all_public_formats_and_modes_reach_the_owner(tmp_path: Path, monkeypatch, suffix: str, mode: str) -> None:
    source = tmp_path / ("source" + suffix); source.write_bytes(b"source")
    sessions = _Sessions({"status": "opened", "system_key": "standalone", "catalogue": "table"})
    ctx = _ctx(source, sessions); ctx.inputs["mode"] = mode
    monkeypatch.setattr("ea_node_editor.addons.mechanical.runtime.discover_mechanical_releases", lambda: (261,))
    execute_open_model(ctx)
    assert sessions.opened["backend_mode"] == mode


def test_system_required_publishes_info_without_model(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "source.wbpj"; source.write_bytes(b"source")
    sessions = _Sessions({"status": "system_required", "catalogue": "systems"})
    ctx = _ctx(source, sessions); warnings = []; ctx.warn = lambda *args, **kwargs: warnings.append((args, kwargs))
    monkeypatch.setattr("ea_node_editor.addons.mechanical.runtime.discover_mechanical_releases", lambda: (261,))
    assert execute_open_model(ctx) == {"info": "systems"}
    assert warnings


def test_accepted_system_selector_roundtrips_into_next_open(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "source.wbpj"; source.write_bytes(b"source")
    import os
    import hashlib
    source_key = "sha256:" + hashlib.sha256(source.read_bytes()).hexdigest()
    document_id = str(uuid5(NAMESPACE_URL, f"corex-mechanical:{os.path.normcase(str(source.resolve()))}:{source_key}"))
    selector = encode_selector(
        "system", document_id=document_id, system_key="SYS",
        object_path="", native_id="SYS",
    )
    catalogue_id = str(uuid4())
    rows = [
        _row(
            catalogue_id=catalogue_id, producer_node_id="open", document_id=document_id,
            source_key=source_key, system_key="", producer_path="[2]", producer_iteration=3,
        ),
        _row(
            "system", catalogue_id=catalogue_id, producer_node_id="open",
            document_id=document_id, source_key=source_key, system_key="SYS",
            system_label="Shared Model", selector_code=selector,
            producer_path="[2]", producer_iteration=3,
        ),
    ]
    table = catalogue_table(rows)
    item = MechanicalPropertyEditAdapter().build_property_items(
        PropertyEditAdapterContext(
            node=SimpleNamespace(node_id="open", type_id="mechanical.open_model"),
            current_output_provider=lambda *_: DataTree({(2,): (table,)}),
        ),
        [{"key": "system", "value": ""}],
    )[0]
    selector = item["enum_codes"][0]
    sessions = _Sessions({"status": "opened", "system_key": "SYS", "catalogue": "table"})
    ctx = _ctx(source, sessions); ctx.inputs["system"] = selector
    monkeypatch.setattr("ea_node_editor.addons.mechanical.runtime.discover_mechanical_releases", lambda: (261,))
    execute_open_model(ctx)
    assert sessions.operated["args"]["system"] == "SYS"
    tampered = selector.replace('"system_key":"SYS"', '"system_key":"OTHER"')
    ctx.inputs["system"] = tampered
    with pytest.raises(ValueError, match="another source or kind"):
        execute_open_model(ctx)


def test_workbench_shared_model_keeps_each_stable_system_alias() -> None:
    choices = deduplicate_model_systems([
        {"key": "SYS", "label": "Primary", "model_key": "Model"},
        {"key": "SYS 1", "label": "Shared", "model_key": "Model"},
        {"key": "SYS 2", "label": "Independent", "model_key": "Model 2"},
    ])
    assert len(choices) == 2
    assert choices[0]["system_keys"] == ["SYS", "SYS 1"]
    assert select_model_system(choices, "SYS 1") is choices[0]
    assert select_model_system(choices, "SYS") is choices[0]
    assert select_model_system(choices, "") is None


def test_workbench_inventory_skips_model_less_system_but_propagates_model_failure(
    tmp_path: Path,
) -> None:
    class System:
        def __init__(self, name: str, components: tuple[str, ...], *, fail: bool = False):
            self.Name = name
            self.DisplayText = name
            self.Components = [SimpleNamespace(UserId=value) for value in components]
            self.fail = fail
            self.calls = 0

        def GetContainer(self, *, ComponentName: str):
            self.calls += 1
            assert ComponentName == "Model"
            if self.fail:
                raise RuntimeError("applicable Model lookup failed")
            return SimpleNamespace(Name="Model")

    class Workbench:
        def __init__(self, systems):
            self.systems = systems

        def run_script_string(self, script: str):
            namespace = {"GetAllSystems": lambda: self.systems}
            exec(compile(script, "<workbench-systems-test>", "exec"), namespace)
            return json.loads(namespace["wb_script_result"])

    external = System("External Model", ("Setup",))
    mechanical = System("Static Structural", ("Engineering Data", "Model 1", "Setup 1"))
    backend = MechanicalOwnerBackend()
    backend.work_root = tmp_path
    backend.workbench = Workbench([external, mechanical])
    assert backend._workbench_systems() == [{
        "key": "Static Structural",
        "label": "Static Structural",
        "model_key": "Model",
        "system_keys": ["Static Structural"],
    }]
    assert external.calls == 0 and mechanical.calls == 1

    backend.workbench = Workbench([System("Broken", ("Model",), fail=True)])
    with pytest.raises(RuntimeError, match="applicable Model lookup failed"):
        backend._workbench_systems()


def test_discovery_emits_table_and_type_aware_relation_descriptors(tmp_path: Path) -> None:
    class Native:
        ObjectId = 7; Name = "Body"; Parent = None; VisibleProperties = []
        Hidden = True
        TabularData = SimpleNamespace(Keys=["Time", "Value"])
        def GetType(self): return SimpleNamespace(FullName="Ansys.ACT.Automation.Mechanical.Body")
    manager = SimpleNamespace(NumberOfViews=0)
    manager.ExportModelViews = lambda path: Path(path).write_text("<Views/>", encoding="utf-8")
    identity = {
        "schema_version": 1, "model_revision": 0, "producer_iteration": 0,
        "catalogue_id": str(uuid4()), "producer_node_id": "open", "producer_port": "info",
        "producer_path": "[0]", "run_id": "run", "session_id": "session",
        "document_id": "document", "source_key": "source", "system_key": "standalone",
        "view_export_path": str(tmp_path / "views.xml"),
    }
    rows = collect_catalogue_rows(
        tree=SimpleNamespace(AllObjects=[Native()]),
        graphics=SimpleNamespace(ModelViewManager=manager), identity=identity,
        systems=[{"key": "SYS", "label": "Model"}],
    )
    assert {row["record_kind"] for row in rows} == {"session", "system", "object", "table", "relation", "view"}
    assert next(row for row in rows if row["record_kind"] == "view")["view_key"] == "current"
    relations = [row for row in rows if row["record_kind"] == "relation"]
    assert {row["relation_kind"] for row in relations} == {
        "coordinate_system", "source_model", "body_visibility", "environment", "scope"
    }
    assert next(row for row in relations if row["relation_kind"] == "body_visibility")["body_hidden"] is True
    catalogue_table(rows)


def test_workbench_receipts_and_cleanup_do_not_skip_sibling_owners() -> None:
    with pytest.raises(RuntimeError, match="Archive failed"):
        MechanicalOwnerBackend._require_receipt(None, "Archive")

    class Client:
        def __init__(self, fail=False): self.fail = fail; self.exits = 0
        def exit(self):
            self.exits += 1
            if self.fail: raise RuntimeError("exit failed")

    backend = MechanicalOwnerBackend()
    backend.workbench = reader = Client(fail=True)
    with pytest.raises(RuntimeError, match="cleanup failed"):
        backend.close()
    assert reader.exits == 1
    assert backend.workbench is reader
