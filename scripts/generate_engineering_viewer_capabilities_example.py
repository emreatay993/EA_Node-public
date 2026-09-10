from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
import pyvista as pv

from ea_node_editor.common.payload_tools import artifact_content_integrity
from ea_node_editor.common.scene_protocol import empty_engineering_selection_set
from ea_node_editor.nodes.bootstrap import build_default_registry
from ea_node_editor.persistence.artifact_store import ProjectArtifactStore
from ea_node_editor.persistence.serializer import JsonProjectSerializer
from ea_node_editor.runtime_contracts import PATH_DATA_TYPE_ID, RuntimeArtifactRef
from ea_node_editor.settings import SCHEMA_VERSION


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_ROOT = ROOT / "examples" / "engineering_viewer"
PROJECT_PATH = EXAMPLE_ROOT / "engineering_viewer_capabilities.cxproj"

WORKSPACE_ID = "ws_engineering_viewer_capabilities"
VIEW_ID = "view_engineering_viewer_capabilities"
CAD_POINTER_ID = "node_cad_source"
FE_POINTER_ID = "node_fe_source"
CAD_IMPORT_ID = "node_cad_import"
FE_IMPORT_ID = "node_fe_import"
VIEWER_ID = "node_engineering_viewer"
CAD_ARTIFACT_ID = "engineering_viewer.cad_source"
FE_ARTIFACT_ID = "engineering_viewer.fe_source"


def _node(
    node_id: str,
    type_id: str,
    title: str,
    x: float,
    y: float,
    *,
    properties: dict[str, object] | None = None,
    exposed_ports: dict[str, bool] | None = None,
    width: float | None = None,
    height: float | None = None,
) -> dict[str, object]:
    return {
        "node_id": node_id,
        "type_id": type_id,
        "title": title,
        "x": x,
        "y": y,
        "collapsed": False,
        "properties": dict(properties or {}),
        "exposed_ports": dict(exposed_ports or {}),
        "port_labels": {},
        "visual_style": {},
        "parent_node_id": None,
        "custom_width": width,
        "custom_height": height,
    }


def _edge(
    edge_id: str,
    source_node_id: str,
    source_port_key: str,
    target_node_id: str,
    target_port_key: str,
) -> dict[str, object]:
    return {
        "edge_id": edge_id,
        "source_node_id": source_node_id,
        "source_port_key": source_port_key,
        "target_node_id": target_node_id,
        "target_port_key": target_port_key,
        "enabled": True,
        "input_order": 0,
        "label": "",
        "visual_style": {},
    }


def _write_xcaf_step(path: Path) -> None:
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
    from OCP.Quantity import Quantity_Color, Quantity_TOC_RGB
    from OCP.STEPCAFControl import STEPCAFControl_Writer
    from OCP.TCollection import TCollection_ExtendedString
    from OCP.TDataStd import TDataStd_Name
    from OCP.TDocStd import TDocStd_Document
    from OCP.TopAbs import TopAbs_FACE
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopLoc import TopLoc_Location
    from OCP.TopoDS import TopoDS
    from OCP.XCAFDoc import XCAFDoc_ColorType, XCAFDoc_DocumentTool
    from OCP.gp import gp_Trsf, gp_Vec

    document = TDocStd_Document(TCollection_ExtendedString("XmlXCAF"))
    shape_tool = XCAFDoc_DocumentTool.ShapeTool_s(document.Main())
    color_tool = XCAFDoc_DocumentTool.ColorTool_s(document.Main())
    layer_tool = XCAFDoc_DocumentTool.LayerTool_s(document.Main())

    part = BRepPrimAPI_MakeBox(36.0, 24.0, 18.0).Shape()
    part_label = shape_tool.AddShape(part, False)
    TDataStd_Name.Set_s(part_label, TCollection_ExtendedString("COREX Colored Housing"))
    color_tool.SetColor(
        part_label,
        Quantity_Color(0.12, 0.46, 0.82, Quantity_TOC_RGB),
        XCAFDoc_ColorType.XCAFDoc_ColorSurf,
    )
    face_explorer = TopExp_Explorer(part, TopAbs_FACE)
    face_label = shape_tool.AddSubShape(
        part_label, TopoDS.Face_s(face_explorer.Current())
    )
    color_tool.SetColor(
        face_label,
        Quantity_Color(0.95, 0.34, 0.16, Quantity_TOC_RGB),
        XCAFDoc_ColorType.XCAFDoc_ColorSurf,
    )
    layer_tool.SetLayer(part_label, TCollection_ExtendedString("Demo Housing"))

    assembly_label = shape_tool.NewShape()
    TDataStd_Name.Set_s(
        assembly_label, TCollection_ExtendedString("COREX Demo Assembly")
    )
    transform = gp_Trsf()
    transform.SetTranslation(gp_Vec(12.0, 0.0, 0.0))
    instance_label = shape_tool.AddComponent(
        assembly_label,
        part_label,
        TopLoc_Location(transform),
    )
    TDataStd_Name.Set_s(
        instance_label,
        TCollection_ExtendedString("Translated Housing Instance"),
    )
    shape_tool.UpdateAssemblies()

    path.parent.mkdir(parents=True, exist_ok=True)
    writer = STEPCAFControl_Writer()
    writer.SetColorMode(True)
    writer.SetLayerMode(True)
    writer.SetNameMode(True)
    if (
        writer.Transfer(document) is False
        or writer.Write(str(path)).name != "IFSelect_RetDone"
    ):
        raise RuntimeError("Could not generate the Model Viewer STEP example.")

    step_text = path.read_text(encoding="utf-8")
    normalized, replacements = re.subn(
        r"(FILE_NAME\s*\(\s*'[^']*'\s*,\s*)'[^']*'",
        r"\1'2026-07-14T00:00:00'",
        step_text,
        count=1,
    )
    if replacements != 1:
        raise RuntimeError("Could not normalize the generated STEP header timestamp.")
    normalized = "\n".join(line.rstrip() for line in normalized.splitlines()) + "\n"
    path.write_text(normalized, encoding="utf-8", newline="\n")


def _write_rgba_vtu(path: Path) -> None:
    center = np.asarray([40.0, 12.0, 9.0])
    mesh = (
        pv.Sphere(
            radius=17.0,
            center=center,
            theta_resolution=32,
            phi_resolution=24,
        )
        .triangulate()
        .cast_to_unstructured_grid()
    )
    points = np.asarray(mesh.points)
    normalized_z = np.clip((points[:, 2] - center[2] + 17.0) / 34.0, 0.0, 1.0)
    normalized_x = np.clip((points[:, 0] - center[0] + 17.0) / 34.0, 0.0, 1.0)
    mesh.point_data["RGBA"] = np.column_stack(
        (
            40.0 + (190.0 * normalized_z),
            55.0 + (170.0 * normalized_x),
            235.0 - (150.0 * normalized_z),
            np.full(mesh.n_points, 210.0),
        )
    ).astype(np.uint8)
    mesh.point_data["Temperature"] = (20.0 + points[:, 2] * 2.5).astype(np.float64)
    mesh.point_data["Displacement"] = np.column_stack(
        (
            np.sin(points[:, 1] / 8.0),
            np.cos(points[:, 0] / 10.0),
            np.zeros(mesh.n_points),
        )
    ).astype(np.float64)
    mesh.cell_data["MaterialId"] = (np.arange(mesh.n_cells, dtype=np.int32) % 3) + 1
    path.parent.mkdir(parents=True, exist_ok=True)
    mesh.save(path, binary=False)


def _asset_entry(
    store: ProjectArtifactStore,
    *,
    artifact_id: str,
    node_id: str,
    node_title: str,
    filename: str,
) -> tuple[str, dict[str, object], Path]:
    paths = store.node_artifact_paths(
        artifact_id=artifact_id,
        workspace_id=WORKSPACE_ID,
        workspace_name="Model Viewer Capabilities",
        node_id=node_id,
        node_title=node_title,
        node_type="Path Pointer",
        io_dir="in",
        subdirectory="engineering/source",
        filename=filename,
    )
    if store.layout is None:
        raise RuntimeError("The example project requires a project artifact layout.")
    entry = {
        "artifact_kind": "engineering_source",
        "relative_path": paths.managed_relative_path,
        **paths.metadata,
    }
    return (
        store.managed_ref(artifact_id),
        entry,
        store.layout.absolute_path_for_relative(paths.managed_relative_path),
    )


def _camera_bookmarks() -> list[dict[str, object]]:
    return [
        {
            "name": "ISO Perspective",
            "created_at": "2026-07-14T00:00:00",
            "camera_state": {
                "position": [92.0, -72.0, 66.0],
                "focal_point": [32.0, 12.0, 9.0],
                "viewup": [0.0, 0.0, 1.0],
                "zoom": 1.0,
                "parallel_scale": 36.0,
                "view_angle": 30.0,
                "parallel_projection": False,
            },
        },
        {
            "name": "Front Orthographic",
            "created_at": "2026-07-14T00:00:00",
            "camera_state": {
                "position": [32.0, -92.0, 9.0],
                "focal_point": [32.0, 12.0, 9.0],
                "viewup": [0.0, 0.0, 1.0],
                "zoom": 1.0,
                "parallel_scale": 36.0,
                "view_angle": 30.0,
                "parallel_projection": True,
            },
        },
    ]


def _build_document(
    *,
    cad_ref: str,
    fe_ref: str,
    artifact_entries: dict[str, dict[str, object]],
) -> dict[str, object]:
    viewer_properties = {
        "show_mesh_edges": True,
        "representation": "surface_with_edges",
        "show_attribute_colors": True,
        "show_orientation_triad": True,
        "show_view_cube": True,
        "show_world_axes": True,
        "scene_input_ids": ["scene_1", "scene_2"],
        "scene_styles": {"scene_2": {"opacity": 0.32, "color": ""}},
        "clip_enabled": False,
        "clip_axis": "x",
        "clip_offset": 0.0,
        "parallel_projection": False,
        "viewer_background": "theme",
        "saved_selections": empty_engineering_selection_set(),
        "camera_bookmarks": _camera_bookmarks(),
    }
    nodes = [
        _node(
            "node_walkthrough",
            "passive.annotation.group_backdrop",
            "Model Viewer Capabilities",
            -1240.0,
            -260.0,
            properties={"title": "Model Viewer Capabilities"},
            width=2150.0,
            height=1040.0,
        ),
        _node(
            CAD_POINTER_ID,
            "io.path_pointer",
            "Colored XCAF STEP",
            -910.0,
            -30.0,
            properties={
                "mode": "file",
                "path": cad_ref,
                "must_exist": True,
                "show_full_path": False,
            },
            exposed_ports={"path": True, "exists": True},
            width=340.0,
        ),
        _node(
            FE_POINTER_ID,
            "io.path_pointer",
            "RGBA FE Mesh",
            -910.0,
            350.0,
            properties={
                "mode": "file",
                "path": fe_ref,
                "must_exist": True,
                "show_full_path": False,
            },
            exposed_ports={"path": True, "exists": True},
            width=340.0,
        ),
        _node(
            CAD_IMPORT_ID,
            "engineering.cad_import",
            "CAD Import",
            -500.0,
            20.0,
            properties={"path": cad_ref, "length_unit": "mm"},
            exposed_ports={"path": True, "scene": True},
            width=330.0,
        ),
        _node(
            FE_IMPORT_ID,
            "engineering.fe_import",
            "FE Import",
            -500.0,
            360.0,
            properties={"path": fe_ref, "length_unit": "mm"},
            exposed_ports={"path": True, "scene": True},
            width=330.0,
        ),
        _node(
            VIEWER_ID,
            "model.viewer",
            "Model Viewer",
            -70.0,
            20.0,
            properties=viewer_properties,
            exposed_ports={
                "scene_1": True,
                "scene_2": True,
                "session": True,
                "selections": True,
            },
            width=860.0,
            height=640.0,
        ),
    ]
    edges = [
        _edge("edge_cad_scene", CAD_IMPORT_ID, "scene", VIEWER_ID, "scene_1"),
        _edge("edge_fe_scene", FE_IMPORT_ID, "scene", VIEWER_ID, "scene_2"),
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "project_id": "proj_engineering_viewer_capabilities",
        "name": "Model Viewer Capabilities",
        "active_workspace_id": WORKSPACE_ID,
        "workspace_order": [WORKSPACE_ID],
        "workspaces": [
            {
                "workspace_id": WORKSPACE_ID,
                "name": "Model Viewer Capabilities",
                "dirty": False,
                "active_view_id": VIEW_ID,
                "views": [
                    {
                        "view_id": VIEW_ID,
                        "name": "Capabilities",
                        "zoom": 0.72,
                        "pan_x": 235.0,
                        "pan_y": 20.0,
                        "scope_path": [],
                        "hide_optional_ports": False,
                    }
                ],
                "nodes": nodes,
                "edges": edges,
            }
        ],
        "metadata": {
            "artifact_store": {"artifacts": artifact_entries, "staged": {}},
            "workflow_settings": {
                "general": {
                    "project_name": "Model Viewer Capabilities",
                    "description": (
                        "A self-contained colored CAD and RGBA FE multi-scene walkthrough for the "
                        "fullscreen and detached Model Viewer controls."
                    ),
                    "author": "",
                },
                "environment": {"python_path": "", "working_directory": ""},
                "logging": {"level": "info", "capture_console": True},
                "plugins": {"enabled": []},
                "solver_config": {
                    "thread_count": 8,
                    "memory_limit_gb": 12,
                    "enable_parallel": True,
                },
            },
            "ui": {
                "script_editor": {"visible": False, "floating": False, "width": 0.0},
                "passive_style_presets": {"node_presets": [], "edge_presets": []},
            },
            "custom_workflows": [],
            "workspace_order": [WORKSPACE_ID],
        },
    }


def main() -> None:
    EXAMPLE_ROOT.mkdir(parents=True, exist_ok=True)
    store = ProjectArtifactStore(project_path=PROJECT_PATH, metadata=None)
    cad_ref, cad_entry, cad_path = _asset_entry(
        store,
        artifact_id=CAD_ARTIFACT_ID,
        node_id=CAD_POINTER_ID,
        node_title="Colored XCAF STEP",
        filename="colored_housing.step",
    )
    fe_ref, fe_entry, fe_path = _asset_entry(
        store,
        artifact_id=FE_ARTIFACT_ID,
        node_id=FE_POINTER_ID,
        node_title="RGBA FE Mesh",
        filename="rgba_overlay.vtu",
    )
    _write_xcaf_step(cad_path)
    _write_rgba_vtu(fe_path)
    for artifact_id, entry, path in (
        (CAD_ARTIFACT_ID, cad_entry, cad_path),
        (FE_ARTIFACT_ID, fe_entry, fe_path),
    ):
        size_bytes, sha256 = artifact_content_integrity(path.parent, path.name)
        entry["runtime_artifact"] = RuntimeArtifactRef.managed(
            artifact_id,
            data_type_id=PATH_DATA_TYPE_ID,
            schema_version=1,
            format=path.suffix.removeprefix(".").casefold(),
            size_bytes=size_bytes,
            sha256=sha256,
            provenance="corex.example.engineering_viewer",
        ).to_descriptor()

    required_types = {
        "io.path_pointer",
        "engineering.cad_import",
        "engineering.fe_import",
        "model.viewer",
        "passive.annotation.group_backdrop",
    }
    registry = build_default_registry()
    missing = sorted(
        type_id for type_id in required_types if registry.spec_or_none(type_id) is None
    )
    if missing:
        raise RuntimeError(
            f"Required node types are not registered: {', '.join(missing)}"
        )

    raw_document = _build_document(
        cad_ref=cad_ref,
        fe_ref=fe_ref,
        artifact_entries={CAD_ARTIFACT_ID: cad_entry, FE_ARTIFACT_ID: fe_entry},
    )
    serializer = JsonProjectSerializer(registry)
    project = serializer.from_document(json.loads(json.dumps(raw_document)))
    serializer.save_document(PROJECT_PATH, serializer.to_persistent_document(project))


if __name__ == "__main__":
    main()
