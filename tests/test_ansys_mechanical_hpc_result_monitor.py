from __future__ import annotations

import importlib.util
import os
from pathlib import Path
from types import SimpleNamespace

import pytest


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "ansys_mechanical_hpc_result_monitor.py"


def load_monitor():
    spec = importlib.util.spec_from_file_location("ansys_mechanical_hpc_result_monitor", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def write_result_pair(folder: Path, output_text: str | None = None) -> None:
    (folder / "file.rst").write_bytes(b"RST\x00payload")
    (folder / "file.out").write_text(
        output_text
        or "NUMBER OF ERROR   MESSAGES ENCOUNTERED= 0\n"
        "RUN COMPLETED\n",
        encoding="utf-8",
    )


def configured_job(monitor, folder: Path, **changes):
    values = {
        "analysis_name": "Static Structural",
        "folder": str(folder),
        "result_filename": "file.rst",
        "output_filename": "file.out",
        "unit_system": "UnitsNMM",
        "poll_seconds": 1,
        "settle_seconds": 5,
        "max_retries": 1,
        "retry_delay_seconds": 10,
    }
    values.update(changes)
    return monitor.new_job(**values)


def complete_analysis_choice(monitor, name, analysis_id, solution_id, tree_path=None):
    return {
        "analysis_object_id": analysis_id,
        "solution_object_id": solution_id,
        "analysis_tree_path": tree_path or "Model / " + name,
        "analysis_name": name,
        "solution_name": "Solution",
        "analysis_type": "Static Structural",
        "analysis_api_type": "Static",
        "analysis_physics_type": "Mechanical",
        "analysis_clr_type": "Ansys.ACT.Automation.Mechanical.Analysis",
        "display": name + " / Solution  [Static Structural; Mechanical]",
    }


class FalseyEnumLike:
    def __init__(self, text):
        self.text = text

    def __bool__(self):
        return False

    __nonzero__ = __bool__

    def __str__(self):
        return self.text


def test_output_parser_requires_completion_and_zero_errors_with_error_precedence(tmp_path: Path) -> None:
    monitor = load_monitor()
    output = tmp_path / "solve.out"

    output.write_text(
        "NUMBER OF ERROR   MESSAGES ENCOUNTERED= 0\n*** WARNING ***\nRUN COMPLETED\n",
        encoding="utf-8",
    )
    parsed = monitor.parse_mapdl_output(str(output))
    assert parsed["ready"] is True
    assert parsed["error_count"] == 0

    output.write_text(
        "*** ERROR ***\nNUMBER OF ERROR MESSAGES ENCOUNTERED= 1\nRUN COMPLETED\n",
        encoding="utf-8",
    )
    parsed = monitor.parse_mapdl_output(str(output))
    assert parsed["ready"] is False
    assert "*** ERROR ***" in parsed["fatal_markers"]

    output.write_text(
        "*** FATAL ***\nNUMBER OF ERROR MESSAGES ENCOUNTERED= 0\nRUN COMPLETED\n",
        encoding="utf-8",
    )
    assert monitor.parse_mapdl_output(str(output))["ready"] is False

    output.write_text("NUMBER OF ERROR MESSAGES ENCOUNTERED= 0\n", encoding="utf-8")
    assert monitor.parse_mapdl_output(str(output))["ready"] is False


def test_validation_rejects_subfolders_and_wrong_result_types(tmp_path: Path) -> None:
    monitor = load_monitor()
    job = configured_job(monitor, tmp_path)
    assert monitor.validate_job_config(job) is True

    job["result_filename"] = r"nested\file.rst"
    with pytest.raises(ValueError, match="filename only"):
        monitor.validate_job_config(job)
    job["result_filename"] = "file.d3plot"
    with pytest.raises(ValueError, match="extensions"):
        monitor.validate_job_config(job)
    job["result_filename"] = "file.rst"
    job["folder"] = "relative"
    with pytest.raises(ValueError, match="absolute Windows"):
        monitor.validate_job_config(job)

    unresolved = configured_job(monitor, tmp_path, unit_system="")
    with pytest.raises(ValueError, match="unit system"):
        monitor.validate_job_config(unresolved)


def test_v261_analysis_family_normalization_uses_exact_raw_tuples() -> None:
    monitor = load_monitor()
    expected = (
        (FalseyEnumLike("Static"), "Mechanical", "Static Structural"),
        ("Modal", "Mechanical", "Modal"),
        ("Transient", "Mechanical", "Transient Structural"),
        (FalseyEnumLike("Static"), FalseyEnumLike("Thermal"), "Steady-State Thermal"),
    )
    for analysis_type, physics_type, family in expected:
        assert monitor.normalize_analysis_family(analysis_type, physics_type) == family

    unsupported = (
        ("Harmonic", "Mechanical"),
        ("Static", "Acoustic"),
        ("Modal", "Thermal"),
        ("Transient", "Thermal"),
    )
    for analysis_type, physics_type in unsupported:
        assert monitor.normalize_analysis_family(analysis_type, physics_type) is None


def test_analysis_choices_exclude_unsupported_families_and_persist_semantics() -> None:
    monitor = load_monitor()

    class FakeSolution:
        def __init__(self, object_id):
            self.Name = "Solution"
            self.ObjectId = object_id

    class FakeAnalysis:
        def __init__(self, name, object_id, analysis_type, physics_type):
            self.Name = name
            self.ObjectId = object_id
            self.AnalysisType = analysis_type
            self.PhysicsType = physics_type
            self.Solution = FakeSolution(object_id + 1)
            self.Parent = SimpleNamespace(Name="Model", Parent=None)

    static = FakeAnalysis(
        "Supported Static", 10, FalseyEnumLike("Static"), "Mechanical"
    )
    modal = FakeAnalysis("Supported Modal", 20, "Modal", "Mechanical")
    transient = FakeAnalysis("Supported Transient", 30, "Transient", "Mechanical")
    thermal = FakeAnalysis(
        "Supported Thermal",
        40,
        FalseyEnumLike("Static"),
        FalseyEnumLike("Thermal"),
    )
    harmonic = FakeAnalysis("Unsupported Harmonic", 50, "Harmonic", "Mechanical")
    adapter = object.__new__(monitor.MechanicalAdapter)
    adapter.extapi = SimpleNamespace(
        DataModel=SimpleNamespace(
            Project=SimpleNamespace(
                Model=SimpleNamespace(
                    Analyses=[static, modal, transient, thermal, harmonic]
                )
            )
        )
    )

    choices = adapter._analysis_choices_ui()
    assert [choice["analysis_type"] for choice in choices] == [
        "Static Structural",
        "Modal",
        "Transient Structural",
        "Steady-State Thermal",
    ]
    assert choices[0]["analysis_type"] == "Static Structural"
    assert choices[0]["analysis_api_type"] == "Static"
    assert choices[0]["analysis_physics_type"] == "Mechanical"
    assert "Static Structural" in choices[0]["display"]
    assert choices[3]["analysis_api_type"] == "Static"
    assert choices[3]["analysis_physics_type"] == "Thermal"


def test_both_files_must_settle_and_either_change_restarts_timer(tmp_path: Path) -> None:
    monitor = load_monitor()
    write_result_pair(tmp_path)
    job = configured_job(monitor, tmp_path, accept_existing=True)
    monitor.begin_monitoring_job(job, now=0)

    assert monitor.update_job_readiness(job, now=0) is False
    assert monitor.update_job_readiness(job, now=4) is False
    assert job["status"] == monitor.STATUS_SETTLING

    result = tmp_path / "file.rst"
    result.write_bytes(result.read_bytes() + b"changed")
    os.utime(result, (10, 10))
    assert monitor.update_job_readiness(job, now=5) is False
    assert job["stable_since"] == 5
    assert monitor.update_job_readiness(job, now=9) is False
    assert monitor.update_job_readiness(job, now=10) is True
    assert job["status"] == monitor.STATUS_READY


def test_ready_job_is_rechecked_while_queued_and_can_demote_or_fail(tmp_path: Path) -> None:
    monitor = load_monitor()
    write_result_pair(tmp_path)
    queued = configured_job(monitor, tmp_path, accept_existing=True, settle_seconds=5)
    monitor.begin_monitoring_job(queued, now=0)
    assert monitor.update_job_readiness(queued, now=0) is False
    assert monitor.update_job_readiness(queued, now=5) is True
    assert queued["ready_at"] == 5

    active = configured_job(monitor, tmp_path, status=monitor.STATUS_IMPORTING)
    engine = monitor.MonitorEngine([active, queued])
    engine.active_job_id = active["id"]

    result = tmp_path / "file.rst"
    result.write_bytes(result.read_bytes() + b"new payload")
    os.utime(result, (6, 6))
    changed, _events = engine.scan_due(now=6)
    assert changed is True
    assert queued["status"] == monitor.STATUS_SETTLING
    assert queued["ready_at"] is None
    assert engine.next_dispatch(now=6) is None

    assert engine.scan_due(now=11)[0] is True
    assert queued["status"] == monitor.STATUS_READY
    assert queued["ready_at"] == 11

    output = tmp_path / "file.out"
    output.write_text(
        "*** FATAL ***\nNUMBER OF ERROR MESSAGES ENCOUNTERED= 0\nRUN COMPLETED\n",
        encoding="utf-8",
    )
    os.utime(output, (12, 12))
    engine.scan_due(now=12)
    assert queued["status"] == monitor.STATUS_SETTLING
    assert queued["ready_at"] is None
    engine.scan_due(now=17)
    assert queued["status"] == monitor.STATUS_FAILED
    assert queued["failed_phase"] == "readiness"


def test_ready_scan_is_atomic_against_dispatch_and_fatal_result_cannot_import(
    tmp_path: Path, monkeypatch
) -> None:
    monitor = load_monitor()
    ready = configured_job(
        monitor,
        tmp_path,
        status=monitor.STATUS_READY,
        ready_at=1,
        next_scan_at=0,
        last_result_signature={"exists": True, "size": 10, "mtime": 1},
        last_output_signature={"exists": True, "size": 10, "mtime": 1},
    )
    engine = monitor.MonitorEngine([ready])
    dispatch_attempts = []

    def fatal_scan(scanned_job, now=None, pair=None):
        dispatch_attempts.append(engine.next_dispatch(now=now))
        scanned_job["status"] = monitor.STATUS_FAILED
        scanned_job["message"] = "Solver output contains *** FATAL ***."
        scanned_job["failed_phase"] = "readiness"
        scanned_job["ready_at"] = None
        scanned_job["next_scan_at"] = now + 1
        return False

    monkeypatch.setattr(monitor, "update_job_readiness", fatal_scan)
    changed, _events = engine.scan_due(now=2)

    assert dispatch_attempts == [None]
    assert changed is True
    assert ready["status"] == monitor.STATUS_FAILED
    assert ready["ready_at"] is None
    assert engine.next_dispatch(now=2) is None
    with pytest.raises(ValueError, match="stale"):
        engine.mark_phase(ready, "import", now=2)


def test_restored_ready_job_requires_a_fresh_settle_cycle(tmp_path: Path) -> None:
    monitor = load_monitor()
    write_result_pair(tmp_path)
    job = configured_job(monitor, tmp_path, accept_existing=True, settle_seconds=5)
    monitor.begin_monitoring_job(job, now=0)
    monitor.update_job_readiness(job, now=0)
    assert monitor.update_job_readiness(job, now=5) is True

    project = str(tmp_path / "SYS.mechdb")
    Path(project).write_bytes(b"db")
    state = monitor.MonitorEngine([job]).to_state(project)
    restored_engine = monitor.MonitorEngine.from_state(state, project)
    restored = restored_engine.jobs[0]
    assert restored["status"] == monitor.STATUS_SETTLING
    assert restored["ready_at"] is None
    assert restored["stable_since"] is None

    assert monitor.update_job_readiness(restored, now=100) is False
    assert restored["stable_since"] == 100
    assert monitor.update_job_readiness(restored, now=104) is False
    assert monitor.update_job_readiness(restored, now=105) is True
    assert restored["ready_at"] == 105


def test_stale_baseline_requires_both_files_to_change_unless_overridden(tmp_path: Path) -> None:
    monitor = load_monitor()
    write_result_pair(tmp_path)
    job = configured_job(monitor, tmp_path, accept_existing=False)
    monitor.begin_monitoring_job(job, now=0)
    monitor.update_job_readiness(job, now=0)

    monitor.update_job_readiness(job, now=10)
    assert job["status"] == monitor.STATUS_WAITING
    assert "baseline unchanged" in job["message"]

    result = tmp_path / "file.rst"
    result.write_bytes(result.read_bytes() + b"new")
    os.utime(result, (20, 20))
    monitor.update_job_readiness(job, now=20)
    assert "file.out" in job["message"]

    output = tmp_path / "file.out"
    output.write_text(output.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    os.utime(output, (21, 21))
    assert monitor.update_job_readiness(job, now=21) is False
    assert job["status"] == monitor.STATUS_SETTLING
    assert monitor.update_job_readiness(job, now=26) is True


def test_unavailable_folder_consumes_no_retry_and_scan_is_non_recursive(tmp_path: Path) -> None:
    monitor = load_monitor()
    missing = tmp_path / "missing"
    job = configured_job(monitor, missing, accept_existing=True)
    monitor.begin_monitoring_job(job, now=0)
    assert monitor.update_job_readiness(job, now=1) is False
    assert job["retry_count"] == 0
    assert "Folder unavailable" in job["message"]

    nested = tmp_path / "nested"
    nested.mkdir()
    write_result_pair(nested)
    pair = monitor.scan_file_pair(str(tmp_path), "file.rst", "file.out")
    assert pair["folder_available"] is True
    assert pair["result"]["exists"] is False
    assert pair["output"]["exists"] is False


def test_fifo_retry_priority_and_only_one_active_chain(tmp_path: Path) -> None:
    monitor = load_monitor()
    first = configured_job(monitor, tmp_path, order=1, status=monitor.STATUS_READY, ready_at=100)
    second = configured_job(monitor, tmp_path, order=2, status=monitor.STATUS_READY, ready_at=100)
    engine = monitor.MonitorEngine([first, second])
    assert engine.next_dispatch(now=100)["id"] == first["id"]
    assert engine.active_job_id == first["id"]
    assert first["status"] == monitor.STATUS_IMPORTING

    engine.mark_phase(first, "import", now=100)
    assert engine.next_dispatch(now=100) is None
    engine.active_job_id = None
    first["status"] = monitor.STATUS_COMPLETED

    retry = configured_job(
        monitor,
        tmp_path,
        order=3,
        status=monitor.STATUS_RETRY_WAITING,
        retry_due_at=99,
        failed_phase="evaluate",
    )
    engine.jobs.append(retry)
    engine._renumber()
    assert engine.next_dispatch(now=100)["id"] == retry["id"]


def test_nonmutating_retry_allows_work_but_mutation_uncertainty_blocks_and_escalates(tmp_path: Path) -> None:
    monitor = load_monitor()
    failed = configured_job(monitor, tmp_path, status=monitor.STATUS_IMPORTING)
    ready = configured_job(monitor, tmp_path, status=monitor.STATUS_READY, ready_at=1)
    engine = monitor.MonitorEngine([failed, ready])
    engine.active_job_id = failed["id"]

    engine.fail_phase(failed, "import", "file vanished", False, now=0)
    assert failed["status"] == monitor.STATUS_RETRY_WAITING
    assert engine.next_dispatch(now=1)["id"] == ready["id"]
    engine.finish_job(ready, {"verified_at": 2}, now=2)
    assert engine.next_dispatch(now=9) is None
    assert engine.next_dispatch(now=10)["id"] == failed["id"]
    engine.mark_phase(failed, "import", now=10)
    engine.fail_phase(failed, "import", "unknown partial import", True, now=10)
    assert failed["status"] == monitor.STATUS_ATTENTION
    assert engine.attention_required is True
    assert engine.next_dispatch(now=100) is None


def test_unacknowledged_recovery_stop_guards_skip_remove_and_update(tmp_path: Path) -> None:
    monitor = load_monitor()
    stopped = configured_job(
        monitor,
        tmp_path,
        status=monitor.STATUS_ATTENTION,
        mutation_uncertain=True,
        recovery_acknowledged=False,
    )
    engine = monitor.MonitorEngine([stopped])
    engine._refresh_attention_required()
    replacement = configured_job(monitor, tmp_path)

    with pytest.raises(ValueError, match="recovery is explicitly acknowledged"):
        engine.skip_job(stopped)
    with pytest.raises(ValueError, match="recovery is explicitly acknowledged"):
        engine.remove_job(stopped["id"])
    with pytest.raises(ValueError, match="recovery is explicitly acknowledged"):
        engine.update_job(stopped["id"], replacement)
    assert engine.attention_required is True

    engine.acknowledge_recovery(stopped)
    assert engine.attention_required is False
    engine.skip_job(stopped)
    assert stopped["status"] == monitor.STATUS_SKIPPED

    retry = configured_job(
        monitor,
        tmp_path,
        status=monitor.STATUS_ATTENTION,
        mutation_uncertain=True,
        recovery_acknowledged=False,
    )
    retry_engine = monitor.MonitorEngine([retry])
    retry_engine._refresh_attention_required()
    retry_engine.release_attention_for_retry(retry, now=42)
    assert retry["status"] == monitor.STATUS_RETRY_WAITING
    assert retry["retry_due_at"] == 42
    assert retry["recovery_acknowledged"] is True
    assert retry_engine.attention_required is False


def test_mutating_retry_wait_blocks_until_due_then_prioritizes_same_job(tmp_path: Path) -> None:
    monitor = load_monitor()
    failed = configured_job(
        monitor,
        tmp_path,
        max_retries=2,
        status=monitor.STATUS_IMPORTING,
    )
    ready = configured_job(monitor, tmp_path, status=monitor.STATUS_READY, ready_at=1)
    engine = monitor.MonitorEngine([failed, ready])
    engine.active_job_id = failed["id"]
    engine.fail_phase(failed, "import", "partial", True, now=0)
    assert engine.next_dispatch(now=9) is None
    assert engine.next_dispatch(now=10)["id"] == failed["id"]


def test_atomic_state_round_trip_and_project_mismatch(tmp_path: Path) -> None:
    monitor = load_monitor()
    project = str(tmp_path / "SYS.mechdb")
    Path(project).write_bytes(b"db")
    job = configured_job(monitor, tmp_path)
    engine = monitor.MonitorEngine([job])
    state_path = tmp_path / "state.json"

    monitor.atomic_write_json(str(state_path), engine.to_state(project))
    state = monitor.load_json(str(state_path))
    restored = monitor.MonitorEngine.from_state(state, project)
    assert restored.jobs[0]["id"] == job["id"]
    assert restored.paused is True

    state["saved_at"] = 123
    monitor.atomic_write_json(str(state_path), state)
    assert (tmp_path / "state.json.previous").is_file()
    with pytest.raises(ValueError, match="different Workbench project"):
        monitor.MonitorEngine.from_state(state, str(tmp_path / "OTHER.mechdb"))


def test_atomic_replace_failure_preserves_current_state(tmp_path: Path, monkeypatch) -> None:
    monitor = load_monitor()
    state_path = tmp_path / "state.json"
    state_path.write_text('{"known": "good"}', encoding="utf-8")

    def fail_replace(_source, _destination):
        raise OSError("simulated replace failure")

    monkeypatch.setattr(monitor.os, "replace", fail_replace)
    with pytest.raises(OSError, match="simulated replace failure"):
        monitor.atomic_write_json(str(state_path), {"new": "state"})

    assert state_path.read_text(encoding="utf-8") == '{"known": "good"}'
    assert (tmp_path / "state.json.previous").read_text(encoding="utf-8") == '{"known": "good"}'
    assert (tmp_path / "state.json.tmp").is_file()


def test_repeated_execfile_style_execution_preserves_singleton_sentinel() -> None:
    namespace = {
        "__name__": "ansys_monitor_execfile_test",
        "__file__": str(SCRIPT_PATH),
        "_HPC_RESULT_MONITOR": object(),
    }
    sentinel = namespace["_HPC_RESULT_MONITOR"]
    code = compile(SCRIPT_PATH.read_bytes(), str(SCRIPT_PATH), "exec")
    exec(code, namespace)
    exec(code, namespace)
    assert namespace["_HPC_RESULT_MONITOR"] is sentinel


def test_solution_rebind_requires_full_identity_even_when_object_ids_match() -> None:
    monitor = load_monitor()

    class FakeSolution:
        def __init__(self, name, object_id):
            self.Name = name
            self.ObjectId = object_id

    class FakeAnalysis:
        def __init__(self, name, object_id, solution):
            self.Name = name
            self.ObjectId = object_id
            self.Solution = solution
            self.AnalysisType = FalseyEnumLike("Static")
            self.PhysicsType = FalseyEnumLike("Thermal")
            self.Parent = SimpleNamespace(Name="Model", Parent=None)

    wrong = FakeAnalysis("Wrong Thermal", 10, FakeSolution("Solution", 20))
    correct = FakeAnalysis("Target Thermal", 30, FakeSolution("Solution", 40))
    adapter = object.__new__(monitor.MechanicalAdapter)
    adapter.extapi = SimpleNamespace(
        DataModel=SimpleNamespace(
            Project=SimpleNamespace(Model=SimpleNamespace(Analyses=[wrong, correct]))
        )
    )
    job = monitor.new_job(
        analysis_object_id=10,
        solution_object_id=20,
        analysis_tree_path=adapter._object_path(correct),
        analysis_name="Target Thermal",
        solution_name="Solution",
        analysis_type="Steady-State Thermal",
        analysis_api_type="Static",
        analysis_physics_type="Thermal",
        analysis_clr_type=monitor.type_name(correct),
    )
    assert adapter._resolve_solution_ui(job) is correct.Solution

    duplicate = FakeAnalysis("Target Thermal", 50, FakeSolution("Solution", 60))
    adapter.extapi.DataModel.Project.Model.Analyses.append(duplicate)
    with pytest.raises(RuntimeError, match="ambiguous"):
        adapter._resolve_solution_ui(job)


def test_choice_refresh_repopulates_display_and_preserves_only_complete_identity() -> None:
    monitor = load_monitor()

    class FakeItems(list):
        @property
        def Count(self):
            return len(self)

        def Add(self, value):
            self.append(value)

        def Clear(self):
            del self[:]

    class FakeCombo:
        def __init__(self):
            self.Items = FakeItems()
            self.SelectedIndex = -1

    first = complete_analysis_choice(monitor, "First", 10, 11)
    second = complete_analysis_choice(monitor, "Second", 20, 21)
    renamed = complete_analysis_choice(monitor, "Second renamed", 20, 21)
    batches = iter(([second, first], [renamed, first], [first]))
    form = object.__new__(monitor.HpcResultMonitorForm)
    form.adapter = SimpleNamespace(analysis_choices=lambda: list(next(batches)))
    form.analysis_choices = [first, second]
    form.analysis_combo = FakeCombo()
    form.analysis_combo.Items.extend([first["display"], second["display"]])
    form.analysis_combo.SelectedIndex = 1
    form.validation_label = SimpleNamespace(Text="")
    form.unit_combo = SimpleNamespace(SelectedItem="UnitsNMM - NMM")
    form.folder_box = SimpleNamespace(Text=r"C:\HPC\run")
    form.result_box = SimpleNamespace(Text="file.rst")
    form.output_box = SimpleNamespace(Text="file.out")
    form.poll_numeric = SimpleNamespace(Value=300)
    form.settle_numeric = SimpleNamespace(Value=300)
    form.retries_numeric = SimpleNamespace(Value=3)
    form.retry_delay_numeric = SimpleNamespace(Value=600)
    form.accept_existing_box = SimpleNamespace(Checked=False)

    form._reload_analysis_choices()
    assert form.analysis_combo.SelectedIndex == 0
    assert form.analysis_combo.Items[0] == second["display"]
    assert form.analysis_choices[0] is second
    stored = form._job_from_editor()
    assert monitor.analysis_identity_tuple(stored) == monitor.analysis_identity_tuple(
        second
    )

    form._reload_analysis_choices()
    assert form.analysis_combo.SelectedIndex == -1
    assert form.analysis_combo.Items == [renamed["display"], first["display"]]
    assert monitor.analysis_identity_tuple(renamed) != monitor.analysis_identity_tuple(second)

    form._reload_analysis_choices()
    assert form.analysis_combo.SelectedIndex == -1
    assert form.analysis_combo.Items == [first["display"]]
    assert [choice["display"] for choice in form.analysis_choices] == list(
        form.analysis_combo.Items
    )


def test_attention_skip_is_enabled_and_requires_explicit_recovery_confirmation(
    tmp_path: Path,
) -> None:
    monitor = load_monitor()
    job = configured_job(
        monitor,
        tmp_path,
        status=monitor.STATUS_ATTENTION,
        mutation_uncertain=True,
        recovery_acknowledged=False,
    )
    engine = monitor.MonitorEngine([job])
    engine._refresh_attention_required()
    form = object.__new__(monitor.HpcResultMonitorForm)
    form.engine = engine
    form.form = None
    form._editing_allowed = lambda: True
    form._selected_job = lambda: job
    controls = [SimpleNamespace(Enabled=None) for _index in range(13)]
    (
        form.analysis_combo,
        form.folder_box,
        form.folder_button,
        form.result_box,
        form.result_button,
        form.output_box,
        form.output_button,
        form.unit_combo,
        form.poll_numeric,
        form.settle_numeric,
        form.retries_numeric,
        form.retry_delay_numeric,
        form.accept_existing_box,
    ) = controls
    for name in (
        "add_button",
        "update_button",
        "remove_button",
        "up_button",
        "down_button",
        "start_button",
        "pause_button",
        "stop_button",
        "retry_button",
        "skip_button",
        "restore_button",
    ):
        setattr(form, name, SimpleNamespace(Enabled=None))
    form._update_enabled_state()
    assert form.skip_button.Enabled is True
    assert form.update_button.Enabled is False
    assert form.remove_button.Enabled is False

    confirmations = []
    yes = object()
    form.ui = {
        "MessageBox": SimpleNamespace(
            Show=lambda *args: confirmations.append(args) or yes
        ),
        "MessageBoxButtons": SimpleNamespace(YesNo=object()),
        "MessageBoxIcon": SimpleNamespace(Warning=object()),
        "DialogResult": SimpleNamespace(Yes=yes),
    }
    form._persist = lambda: None
    form._log = lambda *args: None
    form._refresh_grid = lambda: None
    form._schedule_dispatch = lambda: None
    form._show_error = lambda exc: pytest.fail(str(exc))

    form._skip_clicked(None, None)
    assert len(confirmations) == 1
    assert job["recovery_acknowledged"] is True
    assert job["status"] == monitor.STATUS_SKIPPED
    assert engine.attention_required is False


def test_import_allows_solve_required_until_evaluation(tmp_path: Path) -> None:
    monitor = load_monitor()
    result = tmp_path / "file.rst"
    result.write_bytes(b"real-looking result bytes")

    class FakeSolution:
        Status = FalseyEnumLike("SolveRequired")
        Children = []
        ResultFileSize = 24
        ResultFileTimestamp = "now"
        ResultFileUnitSystem = FalseyEnumLike("UnitsMKS")

        def ReadGivenAnsysResultFileByReference(self, path, unit):
            self.ResultFilePath = path
            self.loaded_path = path
            self.unit = unit

        def IsResultFileSameAsLoaded(self, path):
            return path == self.loaded_path

    solution = FakeSolution()
    adapter = object.__new__(monitor.MechanicalAdapter)
    adapter._unit_enum = SimpleNamespace(UnitsNMM=object())
    adapter._resolve_solution_ui = lambda _job: solution
    project = SimpleNamespace(FilePath=str(tmp_path / "SYS.mechdb"), UserFiles=str(tmp_path))
    adapter.extapi = SimpleNamespace(DataModel=SimpleNamespace(Project=project))
    adapter.bind_project(
        {"project_path": project.FilePath, "user_files": project.UserFiles}
    )
    job = monitor.new_job(
        folder=str(tmp_path), result_filename="file.rst", unit_system="UnitsNMM"
    )

    evidence = adapter._import_ui(job)
    assert evidence["solution_status"] == "SolveRequired"
    assert evidence["result_file_unit_system"] == "UnitsMKS"
    with pytest.raises(monitor.MechanicalPhaseError, match="not acceptable after result evaluation"):
        adapter._verify_loaded_ui(job, True)


def test_falsey_failed_child_blocks_evaluation_and_pre_save(tmp_path: Path) -> None:
    monitor = load_monitor()
    result = tmp_path / "file.rst"
    result.write_bytes(b"result bytes")
    database = tmp_path / "SYS.mechdb"
    database.write_bytes(b"database")

    failed_result = SimpleNamespace(
        Name="Failed deformation",
        ObjectState=FalseyEnumLike("SolveFailed"),
        Status=None,
        Children=[],
    )

    class FakeSolution:
        Status = "Done"
        Children = [failed_result]
        ResultFileSize = 12
        ResultFileTimestamp = "now"
        ResultFileUnitSystem = "ConsistentNMM"
        evaluate_calls = 0

        def EvaluateAllResults(self):
            self.evaluate_calls += 1

        def IsResultFileSameAsLoaded(self, path):
            return path == self.ResultFilePath

    class FakeApplication:
        def __init__(self):
            self.save_calls = 0

        def ScriptByName(self, _name):
            self.save_calls += 1
            raise AssertionError("Save Database must not execute after a failed result state.")

    solution = FakeSolution()
    solution.ResultFilePath = str(result)
    application = FakeApplication()
    adapter = object.__new__(monitor.MechanicalAdapter)
    adapter._resolve_solution_ui = lambda _job: solution
    adapter.extapi = SimpleNamespace(
        DataModel=SimpleNamespace(
            Project=SimpleNamespace(FilePath=str(database), UserFiles=str(tmp_path))
        ),
        Application=application,
    )
    adapter.bind_project(
        {"project_path": str(database), "user_files": str(tmp_path)}
    )
    job = monitor.new_job(folder=str(tmp_path), result_filename="file.rst")

    assert adapter._bad_status(FalseyEnumLike("SolveFailed")) is True
    solution.Children = []
    for unhealthy in (
        FalseyEnumLike("NotSolved"),
        FalseyEnumLike("Unsolved"),
        FalseyEnumLike("PostProcessingRequired"),
        FalseyEnumLike("NotEvaluated"),
        None,
    ):
        solution.Status = unhealthy
        with pytest.raises(
            monitor.MechanicalPhaseError,
            match="not acceptable after result evaluation",
        ):
            adapter._evaluate_ui(job)

    solution.Status = "Done"
    solution.Children = [failed_result]
    evaluate_calls_before_child = solution.evaluate_calls
    with pytest.raises(monitor.MechanicalPhaseError, match="result objects failed"):
        adapter._evaluate_ui(job)
    assert solution.evaluate_calls == evaluate_calls_before_child + 1

    with pytest.raises(monitor.MechanicalPhaseError, match="result objects failed"):
        adapter._save_ui(job)
    assert application.save_calls == 0

    solution.Children = [
        SimpleNamespace(Name="Unreadable", ObjectState=None, Status=None, Children=[])
    ]
    with pytest.raises(monitor.MechanicalPhaseError, match="result objects failed"):
        adapter._verify_loaded_ui(job, True)


def test_phase_callbacks_abort_after_project_switch_before_any_mutation(
    tmp_path: Path,
) -> None:
    monitor = load_monitor()
    result = tmp_path / "file.rst"
    result.write_bytes(b"result bytes")
    original_database = tmp_path / "A.mechdb"
    original_database.write_bytes(b"database A")
    switched_database = tmp_path / "B.mechdb"
    switched_database.write_bytes(b"database B")
    counters = {"import": 0, "evaluate": 0, "save": 0}

    class FakeSolution:
        Status = "Done"
        Children = []
        ResultFilePath = str(result)

        def ReadGivenAnsysResultFileByReference(self, _path, _unit):
            counters["import"] += 1

        def EvaluateAllResults(self):
            counters["evaluate"] += 1

        def IsResultFileSameAsLoaded(self, path):
            return path == self.ResultFilePath

    class FakeApplication:
        def ScriptByName(self, _name):
            counters["save"] += 1
            raise AssertionError("Save must not be reached after a project switch.")

    solution = FakeSolution()
    switched_project = SimpleNamespace(
        FilePath=str(switched_database), UserFiles=str(tmp_path / "B_files")
    )
    adapter = object.__new__(monitor.MechanicalAdapter)
    adapter._unit_enum = SimpleNamespace(UnitsNMM=object())
    adapter._resolve_solution_ui = lambda _job: solution
    adapter.extapi = SimpleNamespace(
        DataModel=SimpleNamespace(Project=switched_project),
        Application=FakeApplication(),
    )
    adapter.bind_project(
        {
            "project_path": str(original_database),
            "user_files": str(tmp_path / "A_files"),
        }
    )
    job = monitor.new_job(
        folder=str(tmp_path), result_filename="file.rst", unit_system="UnitsNMM"
    )

    for callback in (adapter._import_ui, adapter._evaluate_ui, adapter._save_ui):
        with pytest.raises(monitor.MechanicalPhaseError, match="project changed"):
            callback(job)
    assert counters == {"import": 0, "evaluate": 0, "save": 0}


def test_project_switch_requires_reopening_monitor(tmp_path: Path) -> None:
    monitor = load_monitor()
    original = {
        "project_path": str(tmp_path / "A.mechdb"),
        "user_files": str(tmp_path / "A_files"),
    }
    changed = {
        "project_path": str(tmp_path / "B.mechdb"),
        "user_files": str(tmp_path / "B_files"),
    }
    form = object.__new__(monitor.HpcResultMonitorForm)
    form.project = original
    form.adapter = SimpleNamespace(project_info=lambda: changed)
    with pytest.raises(RuntimeError, match="Close this window"):
        form._require_original_project()
