from __future__ import annotations

from ea_node_editor.nodes.builtins.icon_catalog import builtin_node_type_spec
import json
import os
from pathlib import Path
import tempfile

from ea_node_editor.graph.boundary_adapters import register_node_type_size_resolver
from ea_node_editor.nodes.builtins.integrations_common import (
    pick_folder_path,
    pick_optional_path,
    pick_path,
    require_existing_file,
    require_existing_folder,
)
from ea_node_editor.nodes.decorators import plugin_descriptor
from ea_node_editor.nodes.output_artifacts import write_managed_output
from ea_node_editor.nodes.execution_context import NodeResult
from ea_node_editor.nodes.file_dialog_filters import ALL_FILES_FILTER
from ea_node_editor.nodes.node_specs import NodeTypeSpec, PortSpec, PropertySpec
from ea_node_editor.platform_paths import default_user_desktop_path
from ea_node_editor.runtime_contracts.data_tree import resolve_single_run_inputs
from ea_node_editor.runtime_contracts import IMAGE_VALUE_MAX_ENCODED_BYTES, ImageValue


def _write_file_payload(
    path: Path, *, inputs: dict[str, object], as_json: bool
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if as_json:
        payload = inputs["data"] if "data" in inputs else inputs.get("text", "")
        try:
            serialized = json.dumps(
                payload, indent=2, sort_keys=True, ensure_ascii=True, allow_nan=False
            )
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"File Write could not serialize payload as JSON: {exc}"
            ) from exc
        path.write_text(serialized, encoding="utf-8")
        return

    payload = inputs.get("text", inputs.get("data", ""))
    path.write_text("" if payload is None else str(payload), encoding="utf-8")


def execute_file_read(ctx) -> NodeResult:  # noqa: ANN001
    path = pick_path(ctx, input_key="path", property_key="path", node_name="File Read")
    require_existing_file(path, node_name="File Read")
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise RuntimeError(f"File Read failed for '{path}': {exc}") from exc
    return NodeResult(outputs={"text": text})


def execute_file_write(ctx) -> NodeResult:  # noqa: ANN001
    ctx.inputs = resolve_single_run_inputs(ctx.inputs, node_name="File Write")
    as_json = bool(ctx.properties.get("as_json", False))
    path = pick_optional_path(ctx, input_key="path", property_key="path")
    if path is None:
        write_result = write_managed_output(
            ctx,
            output_key="written_path",
            default_suffix=".json" if as_json else ".txt",
            write_payload=lambda output_path: _write_file_payload(
                output_path,
                inputs=ctx.inputs,
                as_json=as_json,
            ),
        )
        return NodeResult(outputs={"written_path": write_result.artifact_ref})

    if path.exists() and path.is_dir():
        raise ValueError(f"File Write path must be a file, not a directory: {path}")

    _write_file_payload(path, inputs=ctx.inputs, as_json=as_json)
    return NodeResult(outputs={"written_path": str(path)})


def execute_image_export(ctx) -> NodeResult:  # noqa: ANN001
    ctx.inputs = resolve_single_run_inputs(ctx.inputs, node_name="Export Image")
    image = ctx.inputs.get("image")
    if type(image) is not ImageValue:
        raise ValueError("Export Image requires a COREX Image value")
    path = pick_path(
        ctx, input_key="path", property_key="path", node_name="Export Image"
    )
    if path.suffix.lower() != ".png":
        raise ValueError("Export Image destination must use the .png extension")
    if path.exists() and path.is_dir():
        raise ValueError(f"Export Image path must be a file, not a directory: {path}")
    overwrite = bool(ctx.inputs.get("overwrite", ctx.properties.get("overwrite", True)))
    if path.exists() and not overwrite:
        raise FileExistsError(f"Export Image destination already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary_path = Path(temporary)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(image.encoded_bytes)
            stream.flush()
            os.fsync(stream.fileno())
        if overwrite:
            os.replace(temporary_path, path)
        else:
            os.link(temporary_path, path)
            temporary_path.unlink()
    finally:
        temporary_path.unlink(missing_ok=True)
    return NodeResult(outputs={"written_path": str(path)})


def execute_image_import(ctx) -> NodeResult:  # noqa: ANN001
    ctx.inputs = resolve_single_run_inputs(ctx.inputs, node_name="Import Image")
    path = pick_path(
        ctx, input_key="path", property_key="path", node_name="Import Image"
    )
    require_existing_file(path, node_name="Import Image")
    if path.suffix.lower() != ".png":
        raise ValueError("Import Image source must use the .png extension")
    try:
        with path.open("rb") as stream:
            payload = stream.read(IMAGE_VALUE_MAX_ENCODED_BYTES + 1)
    except OSError as exc:
        raise RuntimeError(f"Import Image failed for '{path}': {exc}") from exc
    if len(payload) > IMAGE_VALUE_MAX_ENCODED_BYTES:
        raise ValueError("Import Image source exceeds the 64 MiB encoded-byte limit")
    image = ImageValue.from_png(payload)
    return NodeResult(outputs={"image": image})


class PathPointerNodePlugin:
    """Path Pointer — holds a file or folder path for reuse across nodes.

    Implements Variant B ("File / Folder Pointer") from the design mockup at
    ``~/.claude/plans/do-i-have-some-enchanted-spindle.html``. Decisions:
    ``mode`` is ``"file"`` or ``"folder"``; all properties live in a single
    ``"Source"`` inspector group.

    Acts as a passive data source: one editable path feeds many consumers, so a
    path referenced by several nodes has a single edit point.

    The ``show_full_path`` toggle expands the rendered node width just enough to
    show the full path string. When toggled off, the node reverts to its base
    size (the user's last drag-resize if any, otherwise the default). The width
    override is applied via ``_path_pointer_node_size`` below, registered with
    ``register_node_type_size_resolver`` at module-import time.
    """

    def spec(self) -> NodeTypeSpec:
        return builtin_node_type_spec(
            type_id="io.path_pointer",
            display_name="Path Pointer",
            category_path=("Input / Output",),
            description="Holds a file or folder path for reuse across nodes.",
            keywords=("path", "file", "folder"),
            runtime_behavior="passive",
            # Passive data-source: opt back into the title-bar icon. The
            # default passive suppression targets flowchart/planning/
            # annotation/media families that draw their own body art, which
            # this node does not. See ``NodeTypeSpec.show_title_icon``.
            show_title_icon=True,
            ports=(
                PortSpec(
                    "path",
                    "out",
                    "data",
                    "COREX.DataTypes.Path",
                    exposed=True,
                    description="Configured file or folder path.",
                ),
                PortSpec(
                    "exists",
                    "out",
                    "data",
                    "COREX.DataTypes.Bool",
                    exposed=True,
                    description="True when the configured path exists and matches the selected mode.",
                ),
            ),
            properties=(
                PropertySpec(
                    "mode",
                    "enum",
                    "file",
                    "Mode",
                    enum_values=("file", "folder"),
                    inline_editor="enum",
                    inspector_editor="enum",
                    group="Source",
                ),
                PropertySpec(
                    "path",
                    "path",
                    "",
                    "Path",
                    inline_editor="path",
                    inspector_editor="path",
                    group="Source",
                    file_filter=ALL_FILES_FILTER,
                ),
                PropertySpec(
                    "must_exist",
                    "bool",
                    True,
                    "Must Exist",
                    inspector_editor="toggle",
                    group="Source",
                ),
                PropertySpec(
                    "show_full_path",
                    "bool",
                    False,
                    "Show Full Path",
                    inline_editor="toggle",
                    inspector_editor="toggle",
                    group="Source",
                ),
            ),
        )

    def execute(self, ctx) -> NodeResult:  # noqa: ANN001
        mode = str(ctx.properties.get("mode", "file")).strip().lower()
        if mode not in ("file", "folder"):
            raise ValueError(
                f"Path Pointer mode must be 'file' or 'folder', got: {mode!r}"
            )
        must_exist = bool(ctx.properties.get("must_exist", True))

        path = pick_optional_path(ctx, input_key="path", property_key="path")
        if path is None:
            if must_exist:
                raise ValueError(
                    "Path Pointer requires a non-empty path when 'Must Exist' is enabled."
                )
            return NodeResult(outputs={"path": "", "exists": False})

        exists = path.exists()
        type_ok = (
            (path.is_file() if mode == "file" else path.is_dir()) if exists else False
        )

        if must_exist:
            if not exists:
                raise FileNotFoundError(f"Path Pointer path does not exist: {path}")
            if mode == "file" and not path.is_file():
                raise ValueError(
                    f"Path Pointer expected a file but got a directory: {path}"
                )
            if mode == "folder" and not path.is_dir():
                raise ValueError(
                    f"Path Pointer expected a folder but got a file: {path}"
                )

        return NodeResult(
            outputs={"path": str(path), "exists": bool(exists and type_ok)}
        )


class FolderExplorerNodePlugin:
    """Passive folder source for Explorer-style graph surfaces."""

    def spec(self) -> NodeTypeSpec:
        return builtin_node_type_spec(
            type_id="io.folder_explorer",
            display_name="Folder Explorer",
            category_path=("Input / Output",),
            description="Holds the current folder path for Explorer-style browsing.",
            keywords=("folder", "explorer", "browse"),
            runtime_behavior="passive",
            show_title_icon=True,
            ports=(
                PortSpec(
                    "current",
                    "out",
                    "data",
                    "COREX.DataTypes.Path",
                    exposed=True,
                    description="Current folder selected in the Explorer-style surface.",
                ),
            ),
            properties=(
                PropertySpec(
                    "current_path",
                    "path",
                    default_user_desktop_path(),
                    "Current Path",
                    inspector_editor="path",
                    group="Source",
                ),
            ),
        )

    def execute(self, ctx) -> NodeResult:  # noqa: ANN001
        raw_input = str(ctx.inputs.get("current_path", "") or "").strip()
        raw_property = str(ctx.properties.get("current_path", "") or "").strip()
        current_path = (
            Path(default_user_desktop_path())
            if not raw_input and not raw_property
            else pick_folder_path(
                ctx,
                input_key="current_path",
                property_key="current_path",
                node_name="Folder Explorer",
            )
        )
        require_existing_folder(current_path, node_name="Folder Explorer")
        return NodeResult(outputs={"current": str(current_path)})


# --- Dynamic width for io.path_pointer when "Show Full Path" is enabled -------
#
# Width heuristic: graph-row chrome + per-character estimate, capped to a sane
# maximum. The renderer uses real font metrics for the text itself; our job here
# is only to pick a node width that is "wide enough". The chrome estimate mirrors
# the inline Path row: body margins, row margins, the label column, path-field
# padding, the Browse button, row gaps, and a small safety pad.
_PATH_POINTER_BODY_HORIZONTAL_MARGINS_PX = 16.0
_PATH_POINTER_INLINE_ROW_HORIZONTAL_MARGINS_PX = 12.0
_PATH_POINTER_INLINE_LABEL_WIDTH_PX = 78.0
_PATH_POINTER_ROW_GAPS_PX = 18.0
_PATH_POINTER_FIELD_HORIZONTAL_PADDING_PX = 16.0
_PATH_POINTER_BROWSE_BUTTON_WIDTH_PX = 74.0
_PATH_POINTER_WIDTH_SAFETY_PAD_PX = 12.0
_PATH_POINTER_BASE_TEXT_FIT_PX = 96.0
_PATH_POINTER_WIDTH_CHROME_PX = (
    _PATH_POINTER_BODY_HORIZONTAL_MARGINS_PX
    + _PATH_POINTER_INLINE_ROW_HORIZONTAL_MARGINS_PX
    + _PATH_POINTER_INLINE_LABEL_WIDTH_PX
    + _PATH_POINTER_ROW_GAPS_PX
    + _PATH_POINTER_FIELD_HORIZONTAL_PADDING_PX
    + _PATH_POINTER_BROWSE_BUTTON_WIDTH_PX
    + _PATH_POINTER_WIDTH_SAFETY_PAD_PX
)
_PATH_POINTER_CHAR_WIDTH_PX = 7.6
_PATH_POINTER_MAX_WIDTH_PX = 1400.0
_FOLDER_EXPLORER_DEFAULT_WIDTH_PX = 620.0
_FOLDER_EXPLORER_DEFAULT_HEIGHT_PX = 420.0


def _path_pointer_node_size(
    node, _spec, *, base_width: float, base_height: float
) -> tuple[float, float]:
    """Width override for the ``io.path_pointer`` node.

    When ``show_full_path`` is ``True``, return a width large enough to show
    the full path text, but never smaller than ``base_width`` so that a user
    drag-resize wider than needed is still honored. When ``False``, defer to
    ``base_width`` unchanged — so toggling off restores the user's last
    custom width (or the default when they haven't resized).
    """
    properties = getattr(node, "properties", {}) or {}
    show_full = bool(properties.get("show_full_path", False))
    if not show_full:
        return base_width, base_height
    path_text = str(properties.get("path", "") or "")
    if not path_text:
        return base_width, base_height
    estimated_text_width = _PATH_POINTER_CHAR_WIDTH_PX * len(path_text)
    if estimated_text_width <= _PATH_POINTER_BASE_TEXT_FIT_PX:
        return base_width, base_height
    estimated = _PATH_POINTER_WIDTH_CHROME_PX + estimated_text_width
    capped = min(_PATH_POINTER_MAX_WIDTH_PX, estimated)
    return max(base_width, capped), base_height


register_node_type_size_resolver("io.path_pointer", _path_pointer_node_size)


def _folder_explorer_node_size(
    node, _spec, *, base_width: float, base_height: float
) -> tuple[float, float]:
    width = float(base_width)
    height = float(base_height)
    if getattr(node, "custom_width", None) is None:
        width = max(width, _FOLDER_EXPLORER_DEFAULT_WIDTH_PX)
    if getattr(node, "custom_height", None) is None:
        height = max(height, _FOLDER_EXPLORER_DEFAULT_HEIGHT_PX)
    return width, height


register_node_type_size_resolver("io.folder_explorer", _folder_explorer_node_size)


FILE_IO_NODE_DESCRIPTORS = (
    plugin_descriptor(PathPointerNodePlugin),
    plugin_descriptor(FolderExplorerNodePlugin),
)
