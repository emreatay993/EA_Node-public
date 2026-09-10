from __future__ import annotations

from pathlib import Path

from ea_node_editor.nodes.execution_context import ExecutionContext, NodeInputNotReadyError


def pick_optional_path(ctx: ExecutionContext, *, input_key: str, property_key: str) -> Path | None:
    candidate = (
        ctx.inputs[input_key]
        if input_key in ctx.inputs
        else ctx.properties.get(property_key)
    )
    if candidate is None:
        return None
    text = str(candidate).strip()
    if (
        isinstance(candidate, str)
        and len(text) >= 2
        and text[0] == text[-1]
        and text[0] in "\"'"
    ):
        text = text[1:-1].strip()
    if not text:
        return None
    resolved_path = ctx.resolve_path_value(text if isinstance(candidate, str) else candidate)
    return resolved_path if resolved_path is not None else Path(text)


def pick_path(ctx: ExecutionContext, *, input_key: str, property_key: str, node_name: str) -> Path:
    path = pick_optional_path(ctx, input_key=input_key, property_key=property_key)
    if path is not None:
        return path
    raise NodeInputNotReadyError(f"{node_name} requires a non-empty file path.")


def pick_folder_path(ctx: ExecutionContext, *, input_key: str, property_key: str, node_name: str) -> Path:
    path = pick_optional_path(ctx, input_key=input_key, property_key=property_key)
    if path is not None:
        return path
    raise NodeInputNotReadyError(f"{node_name} requires a non-empty folder path.")


def require_existing_file(path: Path, *, node_name: str) -> None:
    if not path.exists():
        raise FileNotFoundError(f"{node_name} path does not exist: {path}")
    if not path.is_file():
        raise ValueError(f"{node_name} path must point to a file: {path}")


def require_existing_folder(path: Path, *, node_name: str) -> None:
    if not path.exists():
        raise FileNotFoundError(f"{node_name} path does not exist: {path}")
    if not path.is_dir():
        raise ValueError(f"{node_name} path must point to a folder: {path}")
