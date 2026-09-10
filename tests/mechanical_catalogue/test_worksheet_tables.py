# Purpose: Prove supported native Mechanical worksheet table adapters.
# Map: subsystems/addons.md
# Tests: tests/mechanical_catalogue/test_worksheet_tables.py

from __future__ import annotations

from types import SimpleNamespace

import pytest

from tests.mechanical_catalogue.test_result_tables import Native, extract, rows, source


class MeshWorksheet:
    RowCount = 2

    def __init__(self):
        self.named = [
            SimpleNamespace(Name="COREX loaded face", ObjectId=42),
            SimpleNamespace(Name="COREX body scope", ObjectId=43),
        ]

    def GetActiveState(self, index):
        return index == 0

    def GetNamedSelection(self, index):
        return self.named[index]

    def __getattr__(self, name):
        if name in {"GenerateMesh", "Solve"}:
            raise AssertionError(f"worksheet extraction must not call {name}")
        raise AttributeError(name)


class LayeredWorksheet:
    RowCount = 2

    def GetMaterial(self, index):
        return ("Structural Steel", "Aluminum Alloy")[index]

    def GetThickness(self, index):
        return (1.5, 0.75)[index]

    def GetAngle(self, index):
        return (45.0, -30.0)[index]


def test_mesh_control_worksheet_preserves_native_row_order_text_and_active_unit_context(tmp_path):
    mesh = Native(
        ObjectId=14,
        Name="Mesh",
        Parent=None,
        api_type="Ansys.ACT.Automation.Mechanical.MeshControls.Mesh",
        Worksheet=MeshWorksheet(),
        VisibleProperties=[],
    )
    _backend, result = extract(
        tmp_path,
        [mesh],
        source={**source(mesh), "object_path": "Mesh"},
        family="supported_worksheet",
    )
    table = result["definition_tables"]["tables"][0]
    assert table.column_names == ("Row", "Active", "Named selection", "Named selection ID", "Unit system")
    assert rows(table) == [
        {"Row": 1, "Active": True, "Named selection": "COREX loaded face", "Named selection ID": 42, "Unit system": "StandardNMM"},
        {"Row": 2, "Active": False, "Named selection": "COREX body scope", "Named selection ID": 43, "Unit system": "StandardNMM"},
    ]
    assert {item["notes"] for item in rows(result["definition_tables"]["definitions"])} == {
        "active unit system: StandardNMM"
    }


def test_layered_section_worksheet_keeps_mixed_scalars_and_does_not_invent_units(tmp_path):
    layered = Native(
        ObjectId=50,
        Name="COREX layered section",
        Parent=None,
        api_type="Ansys.ACT.Automation.Mechanical.LayeredSection",
        Layers=LayeredWorksheet(),
        VisibleProperties=[],
    )
    _backend, result = extract(
        tmp_path,
        [layered],
        source={**source(layered), "object_path": "COREX layered section"},
        family="supported_worksheet",
    )
    table = result["definition_tables"]["tables"][0]
    assert table.column_names == ("Row", "Material", "Thickness", "Angle", "Unit system")
    assert rows(table)[0] == {
        "Row": 1,
        "Material": "Structural Steel",
        "Thickness": 1.5,
        "Angle": 45.0,
        "Unit system": "StandardNMM",
    }
    definitions = rows(result["definition_tables"]["definitions"])
    assert all(item["unit"] == "" for item in definitions)
    assert all("no Quantity metadata" in item["notes"] for item in definitions)


@pytest.mark.parametrize("kind", ["mesh", "layered"])
def test_worksheet_si_rejects_unqualified_native_scalars(tmp_path, kind):
    if kind == "mesh":
        obj = Native(ObjectId=14, Name="Mesh", Parent=None, api_type="Ansys.ACT.Automation.Mechanical.MeshControls.Mesh", Worksheet=MeshWorksheet(), VisibleProperties=[])
    else:
        obj = Native(ObjectId=50, Name="Layered", Parent=None, api_type="Ansys.ACT.Automation.Mechanical.LayeredSection", Layers=LayeredWorksheet(), VisibleProperties=[])
    with pytest.raises(ValueError, match="no native Quantity metadata for SI conversion"):
        extract(
            tmp_path,
            [obj],
            source={**source(obj), "object_path": obj.Name},
            family="supported_worksheet",
            units="si",
        )


def test_unsupported_worksheet_type_fails_without_false_empty_success(tmp_path):
    unsupported = Native(
        ObjectId=60,
        Name="Extension worksheet",
        Parent=None,
        api_type="Example.ACT.ExtensionWorksheet",
        VisibleProperties=[],
    )
    with pytest.raises(ValueError, match="mechanical.table_unsupported: requested table family is unavailable"):
        extract(
            tmp_path,
            [unsupported],
            source={**source(unsupported), "object_path": unsupported.Name},
            family="supported_worksheet",
        )
