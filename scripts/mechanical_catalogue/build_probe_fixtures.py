# Purpose: Build original disposable geometry for Mechanical capability qualification.
# Map: docs/agent_maps/subsystems/verification_testing_docs_hygiene.md
# Tests: tests/mechanical_catalogue/test_probe_contract.py
"""Fixture recipes only; never opens user models or solves on import."""
from __future__ import annotations

import argparse
from pathlib import Path


def create_geometry(path: Path) -> None:
    """Create a cylinder and separate witness block using the installed CAD kernel."""
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder
    from OCP.gp import gp_Pnt
    from OCP.IFSelect import IFSelect_RetDone
    from OCP.STEPControl import STEPControl_AsIs, STEPControl_Writer

    if path.exists():
        raise FileExistsError(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    writer = STEPControl_Writer()
    for shape in (BRepPrimAPI_MakeCylinder(5.0, 40.0).Shape(),
                  BRepPrimAPI_MakeBox(gp_Pnt(20., 0., 0.), 10., 10., 10.).Shape()):
        assert writer.Transfer(shape, STEPControl_AsIs) == IFSelect_RetDone
    assert writer.Write(str(path)) == IFSelect_RetDone


def create_surface_geometry(path: Path) -> None:
    """Create one planar surface body for native layered-section qualification."""
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace, BRepBuilderAPI_MakePolygon
    from OCP.gp import gp_Pnt
    from OCP.IFSelect import IFSelect_RetDone
    from OCP.STEPControl import STEPControl_AsIs, STEPControl_Writer

    if path.exists():
        raise FileExistsError(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    polygon = BRepBuilderAPI_MakePolygon()
    for point in (gp_Pnt(0, 0, 0), gp_Pnt(20, 0, 0), gp_Pnt(20, 10, 0), gp_Pnt(0, 10, 0)):
        polygon.Add(point)
    polygon.Close()
    writer = STEPControl_Writer()
    assert writer.Transfer(BRepBuilderAPI_MakeFace(polygon.Wire()).Face(), STEPControl_AsIs) == IFSelect_RetDone
    assert writer.Write(str(path)) == IFSelect_RetDone


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--geometry", type=Path)
    group.add_argument("--surface-geometry", type=Path)
    args = parser.parse_args()
    (create_surface_geometry if args.surface_geometry else create_geometry)(
        (args.surface_geometry or args.geometry).resolve())
