# Purpose: Prove native Mechanical result, probe, and spatial table adapters.
# Map: subsystems/addons.md
# Tests: tests/mechanical_catalogue/test_result_tables.py

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from ea_node_editor.addons.mechanical.backend import MechanicalOwnerBackend
from ea_node_editor.addons.mechanical.contracts import (
    DEFINITIONS_COLUMNS,
    encode_selector,
    model_handle,
    object_value,
)
from ea_node_editor.addons.mechanical.function_nodes import SOURCE
from ea_node_editor.addons.mechanical.runtime import execute_fea_table
from ea_node_editor.execution.plugin_worker_runtime import WorkerPluginRuntime
from ea_node_editor.execution.registry_agreement import catalog_agreement, runtime_registry_fingerprint
from ea_node_editor.execution.run_messages import StartRunCommand
from ea_node_editor.execution.signal_plot_renderer import render_signal_plot
from ea_node_editor.nodes.bootstrap import build_default_registry
from ea_node_editor.nodes.execution_context import ExecutionContext
from ea_node_editor.nodes.function_plugin import PythonFunctionAdapter
from ea_node_editor.nodes.plugin_declaration import discover_plugin_declarations
from ea_node_editor.runtime_contracts import ImageValue, TableValue


class Quantity:
    def __init__(self, value, unit="", quantity_name=""):
        if isinstance(value, str) and "[" in value:
            number, suffix = value.split("[", 1)
            value, unit = float(number.strip()), suffix.rstrip("]").strip()
        self.Value = float(value)
        self.Unit = unit
        self.QuantityName = quantity_name or {
            "s": "Time", "sec": "Time", "mm": "Length", "N": "Force", "Hz": "Frequency"
        }.get(unit, "")

    def ConvertToUnitSystem(self, system, quantity_name):
        assert system == "SI"
        if quantity_name == "Length" and self.Unit == "mm":
            return Quantity(self.Value / 1000.0, "m", quantity_name)
        if quantity_name == "Time" and self.Unit == "sec":
            return Quantity(self.Value, "s", quantity_name)
        return Quantity(self.Value, self.Unit, quantity_name)

    def ConvertUnit(self, target):
        if self.Unit == "mm" and target == "m":
            return Quantity(self.Value / 1000.0, "m")
        if self.Unit == "C" and target == "K":
            return Quantity(self.Value + 273.15, "K")
        return Quantity(self.Value, target)

    def __str__(self):
        return f"{self.Value:g} [{self.Unit}]"


class Column(list):
    def __init__(self, values, unit="", quantity_name=""):
        super().__init__(values)
        self.Unit = unit
        self.QuantityName = quantity_name


class ITable:
    def __init__(self, columns, *, independents=(), dependents=()):
        self.Keys = list(columns)
        self._columns = columns
        self.Independents = [SimpleNamespace(Key=key, Value=columns[key]) for key in independents]
        self.Dependents = [SimpleNamespace(Key=key, Value=columns[key]) for key in dependents]
        self.requested = []

    def get_Item(self, key):
        self.requested.append(str(key))
        return self._columns[str(key)]

    def __getattr__(self, name):
        if name in {"Columns", "GetColumnValues"}:
            raise AssertionError(f"unsupported IDataTable API used: {name}")
        raise AttributeError(name)


class Native(SimpleNamespace):
    def GetType(self):
        return SimpleNamespace(FullName=self.api_type)


class Reader:
    def __init__(self, values):
        self.ListTimeFreq = list(values)
        self.disposed = False

    def Dispose(self):
        self.disposed = True


class Analysis(Native):
    def __init__(self, values=(1.0, 2.0, 3.0)):
        super().__init__(ObjectId=20, Name="Analysis", Parent=None, api_type="Ansys.ACT.Automation.Mechanical.Analysis")
        self.values = list(values)
        self.readers = []
        self.Solve = lambda *_: (_ for _ in ()).throw(AssertionError("Solve must not run"))

    def GetResultsData(self):
        reader = Reader(self.values)
        self.readers.append(reader)
        return reader


class ConfiguredResult(Native):
    def __init__(self, analysis, *, set_number=0, reject_zero=True, fail_on=None, fail_message="injected retrieval failure", fail_restore=False, fail_by_verify=False):
        super().__init__(
            ObjectId=45,
            Name="COREX total deformation",
            Parent=analysis,
            api_type="Ansys.ACT.Automation.Mechanical.Results.DeformationResults.TotalDeformation",
            VisibleProperties=[],
        )
        self._by = "Time"
        self._fail_next_by_read = False
        self.fail_by_verify = fail_by_verify
        self.DisplayTime = Quantity(0, "sec", "Time")
        self.CalculateTimeHistory = True
        self._set_number = set_number
        self.reject_zero = reject_zero
        self.fail_on = fail_on
        self.fail_message = fail_message
        self.fail_restore = fail_restore
        self.calls = []
        self.Minimum = Quantity(0, "mm", "Length")
        self.Maximum = Quantity(0, "mm", "Length")
        self.Average = Quantity(0, "mm", "Length")
        self.PlotData = ITable({"Body": Column([14]), "Node": Column([1]), "Values": Column([0.0], "mm", "Length")})

    @property
    def By(self):
        if self._fail_next_by_read:
            self._fail_next_by_read = False
            raise RuntimeError("injected By verification failure")
        return self._by

    @By.setter
    def By(self, value):
        self._by = value
        if self.fail_by_verify and value == "Time":
            self._fail_next_by_read = True

    @property
    def SetNumber(self):
        return self._set_number

    @SetNumber.setter
    def SetNumber(self, value):
        if value == 0 and self.reject_zero:
            raise ValueError("The input is outside of the valid range.")
        if self.fail_restore and value == 2:
            raise ValueError("injected SetNumber restore failure")
        self._set_number = int(value)

    def RetrieveResult(self):
        self.calls.append(self.SetNumber)
        if self.fail_on == self.SetNumber:
            raise RuntimeError(self.fail_message)
        maximum = (0.02318177359646269, 0.0453398728173768, 0.06772866955018697)[self.SetNumber - 1]
        average = (0.008999214179743342, 0.017596547693706485, 0.02628158613992489)[self.SetNumber - 1]
        self.Minimum = Quantity(0, "mm", "Length")
        self.Maximum = Quantity(maximum, "mm", "Length")
        self.Average = Quantity(average, "mm", "Length")
        self.PlotData = ITable(
            {
                "Body": Column([14, 14, 14]),
                "Node": Column([1, 2, 3]),
                "Values": Column(
                    np.array([1.63170693668e-6, 5.90759646002e-6, 1.25040869534e-5]) * self.SetNumber,
                    "mm",
                    "Length",
                ),
            }
        )


class ForceReaction(Native):
    def __init__(self, analysis, *, times=(1.0, 2.0, 3.0), by="Time", clamp=False, fail_by_verify=False):
        super().__init__(
            ObjectId=38,
            Name="COREX force reaction",
            Parent=analysis,
            api_type="Ansys.ACT.Automation.Mechanical.Results.ProbeResults.ForceReaction",
            VisibleProperties=[],
            BoundaryConditionSelection=SimpleNamespace(Name="COREX fixed end", ObjectId=39),
            Orientation=None,
        )
        analysis.values = list(times)
        self._by = by
        self._by_reads = 0
        self.fail_by_verify = fail_by_verify
        self.clamp = clamp
        self.by_assignments = 0
        self.DisplayTime = Quantity(0, "sec", "Time")
        self.calls = []
        for name in ("XAxis", "YAxis", "ZAxis", "Total"):
            setattr(self, name, Quantity(0, "N", "Force"))

    @property
    def By(self):
        self._by_reads += 1
        if self.fail_by_verify and self._by_reads >= 3:
            raise RuntimeError("injected probe By verification failure")
        return self._by

    @By.setter
    def By(self, value):
        self.by_assignments += 1
        raise ValueError("This property is read-only.")

    def RetrieveResult(self):
        time_value = int(self.DisplayTime.Value)
        self.calls.append(time_value)
        if self.clamp:
            self.DisplayTime = Quantity(time_value - 0.5, "sec", "Time")
        values = {
            1: (-99.99999941896519, -24.999999393321936, 1.3419767412869987e-6, 103.07763992961392),
            2: (-199.99999898515085, -24.99999872167403, 2.674065271435211e-6, 201.55644254189457),
            3: (-299.999997898301, -24.9999979218071, 2.8110964649386005e-6, 301.0398622027837),
        }[time_value]
        self.XAxis, self.YAxis, self.ZAxis, self.Total = [Quantity(value, "N", "Force") for value in values]


class FakeTree:
    def __init__(self, objects, fail_after=False):
        self.AllObjects = objects
        self.fail_after = fail_after
        self.reads = 0

    @property
    def ActiveObjects(self):
        self.reads += 1
        if self.fail_after and self.reads > 1:
            raise RuntimeError("injected active-object verification failure")
        return []


class FakeApp:
    def __init__(self, objects, *, fail_presentation_after=False):
        self.objects = objects
        self.closed = False
        self.tree = FakeTree(objects, fail_presentation_after)
        self.camera = SimpleNamespace(
            FocalPoint="focal", ViewVector="view", UpVector="up", SceneWidth="width", SceneHeight="height"
        )

    def execute_script(self, script):
        units = SimpleNamespace(
            Quantity=Quantity,
            UnitsManager=SimpleNamespace(
                GetQuantityUnitForUnitSystem=lambda _system, name: {
                    "Time": "s", "Length": "m", "Force": "N", "Frequency": "Hz"
                }[name],
                ToComputationalUnitForUnitSystem=lambda unit, system, basic: (
                    "m" if unit == "mm" else "K" if unit == "C" else unit
                ) if system == "SI" and basic is False else None,
            ),
        )
        namespace = {
            "Tree": self.tree,
            "Graphics": SimpleNamespace(Camera=self.camera),
            "ExtAPI": SimpleNamespace(Application=SimpleNamespace(ActiveUnitSystem="StandardNMM")),
            "Model": SimpleNamespace(),
            "Ansys": SimpleNamespace(
                Core=SimpleNamespace(Units=units),
                Mechanical=SimpleNamespace(
                    DataModel=SimpleNamespace(
                        Enums=SimpleNamespace(SetDriverStyle=SimpleNamespace(ResultSet="ResultSet"))
                    )
                ),
            ),
        }
        exec(compile(script, "<mechanical-result-script>", "exec"), namespace)
        return namespace["_corex_receipt"]

    run_python_script = execute_script

    def close(self):
        self.closed = True


def extract(tmp_path: Path, objects, *, source, family, table="", component="all", units="source", sets=()):
    backend = MechanicalOwnerBackend()
    backend.work_root = tmp_path.resolve()
    backend.app = FakeApp(objects)
    result = backend.definition_tables(
        {
            "sources": [source],
            "family": family,
            "table": table,
            "table_selector": None,
            "component": component,
            "units": units,
            "sets": list(sets),
            "native_output_path": str(tmp_path / "native-definitions-result.json"),
        }
    )
    return backend, result


def source(obj):
    return {"kind": "object", "object_id": obj.ObjectId, "object_path": f"Analysis/{obj.Name}", "property_key": ""}


def rows(table):
    return table.to_pandas().to_dict(orient="records")


def test_native_itable_uses_keys_get_item_and_preserves_relationships_and_modal_frequency(tmp_path):
    analysis = Analysis(tuple(range(1, 7)))
    table = ITable(
        {
            "Mode": Column([1, 2, 3, 4, 5, 6]),
            "Frequency": Column([0.0, 0.0, 0.0, 0.018843238420758836, 0.02413251515891185, 0.0351399916628191], "Hz", "Frequency"),
        },
        dependents=("Mode", "Frequency"),
    )
    result_obj = Native(
        ObjectId=90, Name="COREX modal deformation", Parent=analysis,
        api_type="Ansys.ACT.Automation.Mechanical.Results.DeformationResults.TotalDeformation",
        TabularData=table, VisibleProperties=[],
    )
    _backend, result = extract(
        tmp_path, [analysis, result_obj], source=source(result_obj),
        family="result_history_summary", table="Native table", component="Frequency", sets=(2, 6),
    )
    value = result["definition_tables"]["tables"][0]
    assert value.column_names == ("Mode", "Frequency [Hz]")
    assert rows(value) == [
        {"Mode": 2, "Frequency [Hz]": 0.0},
        {"Mode": 6, "Frequency [Hz]": pytest.approx(0.0351399916628191)},
    ]
    definitions = rows(result["definition_tables"]["definitions"])
    assert [item["definition_kind"] for item in definitions] == ["itable_dependent", "itable_dependent"]
    assert table.requested == ["Mode", "Frequency"]


def test_native_itable_component_keeps_one_row_independent_column(tmp_path):
    analysis = Analysis((1.0,))
    table = ITable(
        {"Time": Column([1.0], "s", "Time"), "Value": Column([5.0], "mm", "Length")},
        independents=("Time",), dependents=("Value",),
    )
    result_obj = Native(
        ObjectId=91, Name="One row", Parent=analysis,
        api_type="Ansys.ACT.Automation.Mechanical.Results.DeformationResults.TotalDeformation",
        TabularData=table, VisibleProperties=[],
    )
    _backend, result = extract(
        tmp_path, [analysis, result_obj], source=source(result_obj),
        family="result_history_summary", table="Native table", component="Value",
    )
    assert result["definition_tables"]["tables"][0].column_names == ("Time [s]", "Value [mm]")


def test_native_identifier_rejects_nonintegral_values_without_truncation(tmp_path):
    analysis = Analysis((1.0,))
    result_obj = Native(
        ObjectId=92, Name="Bad mode", Parent=analysis,
        api_type="Ansys.ACT.Automation.Mechanical.Results.DeformationResults.TotalDeformation",
        TabularData=ITable({"Mode": Column([1.5])}, dependents=("Mode",)), VisibleProperties=[],
    )
    with pytest.raises(ValueError, match="native identifier is not integral: Mode"):
        extract(
            tmp_path, [analysis, result_obj], source=source(result_obj),
            family="result_history_summary", table="Native table",
        )


def test_native_itable_unreadable_relationship_metadata_is_unsupported(tmp_path):
    class BrokenRelations:
        Keys = ["Value"]
        Dependents = []

        @property
        def Independents(self):
            raise RuntimeError("unreadable relations")

        def get_Item(self, key):
            return Column([1.0])

    analysis = Analysis((1.0,))
    result_obj = Native(
        ObjectId=93, Name="Broken relations", Parent=analysis,
        api_type="Ansys.ACT.Automation.Mechanical.Results.DeformationResults.TotalDeformation",
        TabularData=BrokenRelations(), VisibleProperties=[],
    )
    with pytest.raises(ValueError, match="native ITable Independents metadata is unavailable"):
        extract(
            tmp_path, [analysis, result_obj], source=source(result_obj),
            family="result_history_summary", table="Native table",
        )


def test_configured_summary_selected_sets_restores_active_state_and_reports_only_approved_zero_drift(tmp_path):
    analysis = Analysis()
    configured = ConfiguredResult(analysis)
    _backend, result = extract(
        tmp_path, [analysis, configured], source=source(configured),
        family="result_history_summary", table="Configured result summary", sets=(1, 3),
    )
    table = result["definition_tables"]["tables"][0]
    assert table.column_names == ("Result set", "Time [sec]", "Minimum [mm]", "Maximum [mm]", "Average [mm]")
    frame = table.to_pandas()
    assert frame["Result set"].tolist() == [1, 3]
    np.testing.assert_allclose(frame["Maximum [mm]"], [0.02318177359646269, 0.06772866955018697])
    assert configured.By == "Time"
    assert str(configured.DisplayTime) == "0 [sec]"
    assert configured.CalculateTimeHistory is True
    assert configured.SetNumber == 3
    assert result["warnings"] and "before=0; after=3" in result["warnings"][0]
    assert "before=0; after=3" in rows(result["definition_tables"]["definitions"])[0]["notes"]
    assert all(reader.disposed for reader in analysis.readers)


def test_configured_summary_si_uses_native_quantity_conversion_and_component_selection(tmp_path):
    analysis = Analysis()
    configured = ConfiguredResult(analysis, set_number=2, reject_zero=False)
    _backend, result = extract(
        tmp_path, [analysis, configured], source=source(configured),
        family="result_history_summary", table="Configured result summary",
        component="Maximum", units="si", sets=(1, 3),
    )
    table = result["definition_tables"]["tables"][0]
    assert table.column_names == ("Result set", "Time [s]", "Maximum [m]")
    np.testing.assert_allclose(
        table.to_pandas()["Maximum [m]"],
        [0.02318177359646269e-3, 0.06772866955018697e-3],
    )
    assert configured.SetNumber == 2


def test_si_uses_native_unit_driven_conversion_when_dimension_metadata_is_absent(tmp_path):
    class MissingDimensionResult(ConfiguredResult):
        def RetrieveResult(self):
            super().RetrieveResult()
            for value in (self.Minimum, self.Maximum, self.Average):
                value.QuantityName = ""

    analysis = Analysis()
    configured = MissingDimensionResult(analysis, set_number=2, reject_zero=False)
    _backend, result = extract(
        tmp_path, [analysis, configured], source=source(configured),
        family="result_history_summary", table="Configured result summary",
        units="si", sets=(1,),
    )
    table = result["definition_tables"]["tables"][0]
    assert table.column_names == ("Result set", "Time [s]", "Minimum [m]", "Maximum [m]", "Average [m]")
    assert table.to_pandas()["Maximum [m]"].tolist() == [0.02318177359646269 / 1000.0]
    assert (configured.Maximum.Value, configured.Maximum.Unit) == (0.02318177359646269, "mm")
    assert configured.SetNumber == 2


def test_si_rejects_ambiguous_temperature_without_quantity_metadata(tmp_path):
    analysis = Analysis((1.0,))
    table = ITable({"Temperature": Column([20.0], "C", "")}, dependents=("Temperature",))
    result_obj = Native(
        ObjectId=94, Name="Temperature", Parent=analysis,
        api_type="Ansys.ACT.Automation.Mechanical.Results.ThermalResults.Temperature",
        TabularData=table, VisibleProperties=[],
    )
    with pytest.raises(ValueError, match="affine unit column Temperature"):
        extract(
            tmp_path, [analysis, result_obj], source=source(result_obj),
            family="result_history_summary", table="Native table", units="si",
        )


def test_si_raw_itable_scalar_uses_numeric_quantity_constructor_without_precision_loss(tmp_path):
    value = 0.02318177359646269
    analysis = Analysis((1.0,))
    table = ITable({"Value": Column([value], "mm", "")}, dependents=("Value",))
    result_obj = Native(
        ObjectId=95, Name="Raw scalar", Parent=analysis,
        api_type="Ansys.ACT.Automation.Mechanical.Results.DeformationResults.TotalDeformation",
        TabularData=table, VisibleProperties=[],
    )
    _backend, result = extract(
        tmp_path, [analysis, result_obj], source=source(result_obj),
        family="result_history_summary", table="Native table", units="si",
    )
    assert result["definition_tables"]["tables"][0].to_pandas()["Value [m]"].tolist() == [value / 1000.0]


def test_missing_solved_result_data_fails_before_retrieval(tmp_path):
    class UnsolvedAnalysis(Analysis):
        def GetResultsData(self):
            return None

    analysis = UnsolvedAnalysis()
    configured = ConfiguredResult(analysis, set_number=2, reject_zero=False)
    with pytest.raises(ValueError, match="mechanical.results_missing: solved result data is unavailable"):
        extract(
            tmp_path, [analysis, configured], source=source(configured),
            family="result_history_summary", table="Configured result summary",
        )
    assert configured.calls == []


@pytest.mark.parametrize("failure", ["injected retrieval failure", "cancelled"])
def test_configured_summary_retrieval_error_and_cancellation_restore_every_setting(tmp_path, failure):
    analysis = Analysis()
    configured = ConfiguredResult(
        analysis, set_number=2, reject_zero=False, fail_on=3, fail_message=failure
    )
    with pytest.raises(ValueError, match=failure):
        extract(
            tmp_path, [analysis, configured], source=source(configured),
            family="result_history_summary", table="Configured result summary",
        )
    assert (configured.By, str(configured.DisplayTime), configured.CalculateTimeHistory, configured.SetNumber) == (
        "Time", "0 [sec]", True, 2
    )


def test_unapproved_restore_failure_retires_native_session(tmp_path):
    analysis = Analysis()
    configured = ConfiguredResult(analysis, set_number=2, reject_zero=False, fail_restore=True)
    backend = MechanicalOwnerBackend()
    backend.work_root = tmp_path.resolve()
    app = FakeApp([analysis, configured])
    backend.app = app
    with pytest.raises(ValueError, match="mechanical.restore_failed"):
        backend.definition_tables(
            {
                "sources": [source(configured)], "family": "result_history_summary",
                "table": "Configured result summary", "table_selector": None,
                "component": "all", "units": "source", "sets": [1, 3],
                "native_output_path": str(tmp_path / "native-definitions-restore.json"),
            }
        )
    assert app.closed is True
    assert backend.app is None


def test_restore_verification_getter_failure_is_stable_and_retires_native_session(tmp_path):
    analysis = Analysis()
    configured = ConfiguredResult(
        analysis, set_number=2, reject_zero=False, fail_by_verify=True
    )
    backend = MechanicalOwnerBackend()
    backend.work_root = tmp_path.resolve()
    app = FakeApp([analysis, configured])
    backend.app = app
    with pytest.raises(ValueError, match="mechanical.restore_failed:.*verification.*By verification failure"):
        backend.definition_tables(
            {
                "sources": [source(configured)], "family": "result_history_summary",
                "table": "Configured result summary", "table_selector": None,
                "component": "all", "units": "source", "sets": [1, 3],
                "native_output_path": str(tmp_path / "native-definitions-verification.json"),
            }
        )
    assert app.closed is True
    assert backend.app is None


def test_post_operation_presentation_read_failure_retires_native_session(tmp_path):
    analysis = Analysis()
    configured = ConfiguredResult(analysis, set_number=2, reject_zero=False)
    backend = MechanicalOwnerBackend()
    backend.work_root = tmp_path.resolve()
    app = FakeApp([analysis, configured], fail_presentation_after=True)
    backend.app = app
    with pytest.raises(ValueError, match="mechanical.restore_failed: tree/graphics state could not be verified"):
        backend.definition_tables(
            {
                "sources": [source(configured)], "family": "result_history_summary",
                "table": "Configured result summary", "table_selector": None,
                "component": "all", "units": "source", "sets": [1],
                "native_output_path": str(tmp_path / "native-definitions-presentation.json"),
            }
        )
    assert app.closed is True
    assert backend.app is None


def test_spatial_tables_are_per_set_keep_entity_identity_units_and_plot_directly(tmp_path):
    analysis = Analysis()
    configured = ConfiguredResult(analysis)
    _backend, result = extract(
        tmp_path, [analysis, configured], source=source(configured),
        family="spatial_samples", sets=(1, 3),
    )
    first, third = result["definition_tables"]["tables"]
    assert first.column_names == ("Body", "Node", "Values [mm]")
    assert rows(first)[0]["Body"] == 14 and rows(first)[0]["Node"] == 1
    assert rows(third)[0]["Values [mm]"] == pytest.approx(3 * 1.63170693668e-6)
    definitions = rows(result["definition_tables"]["definitions"])
    assert {item["result_set"] for item in definitions} == {1, 3}
    assert [item["location"] for item in definitions[:3]] == ["Body", "Node", ""]
    before = [np.array(column.to_numpy(), copy=True) for column in third.columns]
    image, _warnings = render_signal_plot({"values": third, "x_column": 1, "y_columns": [2], "marker_shapes": [0]})
    assert isinstance(image, ImageValue)
    for saved, column in zip(before, third.columns, strict=True):
        np.testing.assert_array_equal(saved, column.to_numpy())


def test_spatial_rejects_unqualified_plotdata_without_body_node_values(tmp_path):
    class MissingIdentityResult(ConfiguredResult):
        def RetrieveResult(self):
            super().RetrieveResult()
            self.PlotData = ITable({"Node": Column([1]), "Values": Column([0.1], "mm", "Length")})

    analysis = Analysis()
    configured = MissingIdentityResult(analysis, set_number=2, reject_zero=False)
    with pytest.raises(ValueError, match="qualified Body/Node/Values"):
        extract(
            tmp_path, [analysis, configured], source=source(configured),
            family="spatial_samples", sets=(1,),
        )
    assert configured.SetNumber == 2


def test_force_reaction_never_assigns_by_and_preserves_scope_coordinate_and_totals(tmp_path):
    analysis = Analysis()
    probe = ForceReaction(analysis)
    _backend, result = extract(
        tmp_path, [analysis, probe], source=source(probe),
        family="result_history_summary", sets=(1, 2, 3),
    )
    table = result["definition_tables"]["tables"][0]
    assert probe.by_assignments == 0
    assert probe.calls == [1, 2, 3]
    assert str(probe.DisplayTime) == "0 [sec]"
    np.testing.assert_allclose(table.to_pandas()["Total [N]"], [103.07763992961392, 201.55644254189457, 301.0398622027837])
    definitions = rows(result["definition_tables"]["definitions"])
    assert {item["location"] for item in definitions} == {"COREX fixed end"}
    assert {item["coordinate_system"] for item in definitions} == {"Solution Coordinate System"}


def test_force_reaction_rejects_native_time_clamp_and_restores_display_time(tmp_path):
    analysis = Analysis()
    probe = ForceReaction(analysis, clamp=True)
    with pytest.raises(ValueError, match="did not evaluate the requested stored time"):
        extract(
            tmp_path, [analysis, probe], source=source(probe),
            family="result_history_summary", sets=(2,),
        )
    assert str(probe.DisplayTime) == "0 [sec]"


def test_force_reaction_preserves_high_precision_stored_time(tmp_path):
    expected = 0.123456789012345

    class PreciseForceReaction(ForceReaction):
        def RetrieveResult(self):
            self.calls.append(self.DisplayTime.Value)
            self.XAxis = Quantity(1, "N", "Force")
            self.YAxis = Quantity(2, "N", "Force")
            self.ZAxis = Quantity(3, "N", "Force")
            self.Total = Quantity(4, "N", "Force")

    analysis = Analysis()
    probe = PreciseForceReaction(analysis, times=(expected,))
    _backend, result = extract(
        tmp_path, [analysis, probe], source=source(probe),
        family="result_history_summary", sets=(1,),
    )
    assert probe.calls == [expected]
    assert result["definition_tables"]["tables"][0].to_pandas()["Time [sec]"].tolist() == [expected]


def test_force_reaction_restore_verification_failure_retires_native_session(tmp_path):
    analysis = Analysis()
    probe = ForceReaction(analysis, fail_by_verify=True)
    backend = MechanicalOwnerBackend()
    backend.work_root = tmp_path.resolve()
    app = FakeApp([analysis, probe])
    backend.app = app
    with pytest.raises(ValueError, match="mechanical.restore_failed:.*probe By verification failure"):
        backend.definition_tables(
            {
                "sources": [source(probe)], "family": "result_history_summary",
                "table": "", "table_selector": None, "component": "all",
                "units": "source", "sets": [1],
                "native_output_path": str(tmp_path / "native-definitions-probe-verify.json"),
            }
        )
    assert app.closed is True
    assert backend.app is None


@pytest.mark.parametrize("times,by,message", [((1.0, 1.0), "Time", "ambiguous"), ((1.0, 2.0), "ResultSet", "By=Time")])
def test_force_reaction_rejects_ambiguous_times_and_other_modes(tmp_path, times, by, message):
    analysis = Analysis()
    probe = ForceReaction(analysis, times=times, by=by)
    with pytest.raises(ValueError, match=message):
        extract(tmp_path, [analysis, probe], source=source(probe), family="result_history_summary")
    assert probe.by_assignments == 0
    assert probe.calls == []


def test_result_payload_contract_rejects_unequal_columns_without_padding():
    from ea_node_editor.addons.mechanical.tables import build_definition_tables

    payload = {
        "schema_version": 1,
        "records": [{
            "kind": "table", "table_key": "1:tabular_data", "object_path": "Analysis/Result",
            "property_key": "TabularData",
            "result_set": None,
            "columns": [
                {"key": "Time", "label": "Time", "unit": "s", "quantity_name": "Time", "definition_kind": "itable_independent", "formula": "", "values": [1.0], "location": "", "coordinate_system": "", "notes": ""},
                {"key": "Value", "label": "Value", "unit": "mm", "quantity_name": "Length", "definition_kind": "itable_dependent", "formula": "", "values": [1.0, 2.0], "location": "", "coordinate_system": "", "notes": ""},
            ],
        }],
    }
    with pytest.raises(ValueError, match="inconsistent populated column lengths.*no rows were padded"):
        build_definition_tables(payload)


def test_definitions_schema_remains_the_shared_contract(tmp_path):
    analysis = Analysis()
    configured = ConfiguredResult(analysis)
    _backend, result = extract(
        tmp_path, [analysis, configured], source=source(configured),
        family="spatial_samples", sets=(2,),
    )
    assert result["definition_tables"]["definitions"].column_names == DEFINITIONS_COLUMNS
    assert not list(tmp_path.glob("native-definitions-*.json"))


def test_generated_native_table_script_remains_ironpython_string_compatible():
    from ea_node_editor.addons.mechanical.tables import DEFINITION_SCRIPT_BODY

    assert ".casefold(" not in DEFINITION_SCRIPT_BODY


def _registered_model():
    return model_handle(
        handle_id="model",
        owner_scope="run",
        worker_generation=1,
        metadata={
            "workspace_id": "workspace", "run_id": "run", "session_id": "session",
            "document_id": "document", "source_key": "sha256:source",
            "system_key": "standalone", "model_revision": 0, "connection_generation": 0,
            "release_code": 261,
            "backend_mode": "background", "catalogue_id": "35ac84bc-7cd6-4b7c-8c4e-43db19709f51",
            "producer_node_id": "open", "producer_port": "info", "producer_path": [0],
            "producer_iteration": 0,
        },
    )


def _registered_result_source():
    return object_value(
        {
            "run_id": "run", "session_id": "session", "document_id": "document",
            "source_key": "sha256:source", "system_key": "standalone", "model_revision": 0,
            "object_id": 45, "parent_id": 20, "object_path": "Analysis/COREX total deformation",
            "display_name": "COREX total deformation",
            "api_type": "Ansys.ACT.Automation.Mechanical.Results.DeformationResults.TotalDeformation",
            "category": "TotalDeformation", "analysis_id": 20,
            "selector_code": encode_selector(
                "object", document_id="document", system_key="standalone",
                object_path="Analysis/COREX total deformation", native_id=45,
            ),
        }
    )


def _registered_definition_source():
    value = dict(_registered_result_source().payload)
    value.update(
        object_id=12,
        parent_id=20,
        object_path="Analysis/Force",
        display_name="Force",
        api_type="Ansys.ACT.Automation.Mechanical.BoundaryConditions.Force",
        category="Force",
        selector_code=encode_selector(
            "object", document_id="document", system_key="standalone",
            object_path="Analysis/Force", native_id=12,
        ),
    )
    return object_value(value)


class RegisteredSessions:
    def __init__(self):
        self.operated = None

    def admit_model(self, value, **kwargs):
        return SimpleNamespace(work_root=Path.cwd())

    def operate(self, session, **kwargs):
        self.operated = kwargs
        payload = {
            "schema_version": 1,
            "records": [{
                "kind": "table", "table_key": "45:plot_data:set:3",
                "object_path": "Analysis/COREX total deformation", "property_key": "PlotData",
                "result_set": 3,
                "columns": [
                    {"key": "Body", "label": "Body", "unit": "", "quantity_name": "", "definition_kind": "spatial_entity_id", "formula": "", "values": [14, 14], "location": "Body", "coordinate_system": "", "notes": ""},
                    {"key": "Node", "label": "Node", "unit": "", "quantity_name": "", "definition_kind": "spatial_entity_id", "formula": "", "values": [1, 2], "location": "Node", "coordinate_system": "", "notes": ""},
                    {"key": "Values", "label": "Values", "unit": "mm", "quantity_name": "Length", "definition_kind": "spatial_value", "formula": "", "values": [0.1, 0.2], "location": "", "coordinate_system": "", "notes": ""},
                ],
            }],
        }
        from ea_node_editor.addons.mechanical.tables import build_definition_tables

        return {"definition_tables": build_definition_tables(payload), "warnings": []}


def test_rows_sets_is_not_read_or_passed_for_inactive_definition_family():
    sessions = RegisteredSessions()
    context = SimpleNamespace(
        run_id="run", workspace_id="workspace",
        inputs={"family": "model_definition", "sets": "stale invalid local value"},
        properties={"table": "", "component": "all", "units": "source"},
        mechanical_sessions=sessions,
    )
    result = execute_fea_table(
        context, _registered_model(), [_registered_definition_source()]
    )
    assert isinstance(result["tables"][0], TableValue)
    assert "sets" not in sessions.operated["args"]


def test_actual_registered_adapter_and_worker_runtime_execute_t08_settings():
    declarations = discover_plugin_declarations(
        SOURCE, filename="mechanical_nodes.py", allow_reserved_ids=True,
        owner_id="mechanical.corex", allow_internal_metadata=True,
    )
    declaration = next(item for item in declarations if item.spec.type_id == "mechanical.fea_table")
    namespace = {}
    exec(SOURCE, namespace)
    sessions = RegisteredSessions()
    context = ExecutionContext(
        run_id="run", node_id="fea-table", workspace_id="workspace",
        inputs={
            "model": _registered_model(), "source": [_registered_result_source()],
            "family": "spatial_samples", "sets": [3],
        },
        properties={"table": "", "component": "all", "units": "source"},
        emit_log=lambda *_: None,
        worker_services=SimpleNamespace(mechanical_session_service=sessions),
    )
    outputs = PythonFunctionAdapter(declaration.spec, namespace["fea_table"]).execute(context).outputs
    assert isinstance(outputs["tables"][0], TableValue)
    assert sessions.operated["args"]["sets"] == [3]

    registry = build_default_registry(
        include_public_plugins=False, addon_runtime_config=(("mechanical.corex", True),)
    )
    fingerprint, revisions = catalog_agreement(registry.data_types)
    plugin_digest = registry.plugin_fingerprint()
    command = StartRunCommand(
        run_id="run", workspace_id="workspace", runtime_snapshot=None,
        catalog_fingerprint=fingerprint, catalog_revisions=revisions,
        plugin_bundles=registry.plugin_bundle_refs(), plugin_fingerprint=plugin_digest,
        runtime_registry_fingerprint=runtime_registry_fingerprint(fingerprint, plugin_digest),
        registry_contract_fingerprint=registry.contract_fingerprint(),
        addon_runtime_config=registry.addon_runtime_config(),
    )
    runtime = WorkerPluginRuntime()
    prepared = runtime.prepare_registry(command, registry)
    ref = prepared.python_function_ref_or_none("mechanical.fea_table")
    assert ref is not None
    assert runtime.create_adapter(ref, prepared.get_spec("mechanical.fea_table"))
    runtime.clear()
