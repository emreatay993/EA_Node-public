# Purpose: Create, validate, summarize, and atomically save novice function-plugin drafts.
# Map: subsystems/nodes_registry_builtins.md
# Tests: tests/test_plugin_authoring.py

from __future__ import annotations

import keyword
import os
import re
import secrets
import stat
import tempfile
import threading
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from ea_node_editor.common.path_safety import is_reparse_point
from ea_node_editor.nodes.function_plugin import INTERNAL_BUILTIN_FUNCTION_OWNER_ID
from ea_node_editor.nodes.function_bundle import registry_plugin_fingerprint
from ea_node_editor.nodes.plugin_declaration import PluginDeclarationError
from ea_node_editor.nodes.package_schema import (
    PLUGIN_SOURCE_LIMIT,
    validate_plugin_regular_file,
    validated_plugin_member_path,
)
from ea_node_editor.nodes.plugin_loader import discover_static_plugin_candidate
from ea_node_editor.nodes.registry import NodeRegistry
from ea_node_editor.settings import plugins_dir

_SLUG_TOKEN = re.compile(r"[^a-z0-9]+")
_SLUG_LIMIT = 48
# ponytail: one authoring lock; split by path only if concurrent saves become useful.
_SAVE_LOCK = threading.Lock()


@dataclass(frozen=True, slots=True)
class PluginIdentity:
    visible_name: str
    slug: str
    filename: str
    function_name: str
    node_id: str


@dataclass(frozen=True, slots=True)
class PluginAuthoringDiagnostic:
    filename: str
    line: int
    column: int
    severity: Literal["error", "warning", "info"]
    message: str
    node_id: str = ""
    digest: str = ""
    unavailable_reason: str = ""


@dataclass(frozen=True, slots=True)
class PluginAuthoringSummary:
    bundle_count: int
    node_count: int
    plugin_digest: str
    unavailable_node_count: int


@dataclass(frozen=True, slots=True)
class PluginValidationReport:
    success: bool
    diagnostics: tuple[PluginAuthoringDiagnostic, ...]
    summary: PluginAuthoringSummary


_EMPTY_SUMMARY = PluginAuthoringSummary(0, 0, "", 0)


def _visible_name(value: object) -> str:
    if not isinstance(value, str):
        raise TypeError("Plugin name must be a string")
    return value.strip() or "New Plugin"


def _slug(value: str) -> str:
    ascii_name = (
        unicodedata.normalize("NFKD", value)
        .encode("ascii", errors="ignore")
        .decode("ascii")
        .lower()
    )
    slug = _SLUG_TOKEN.sub("_", ascii_name).strip("_")[:_SLUG_LIMIT].rstrip("_")
    slug = slug or "plugin"
    if slug[0].isdigit():
        slug = f"node_{slug}"
    if keyword.iskeyword(slug):
        slug = f"{slug}_node"
    try:
        validated_plugin_member_path(f"{slug}.py", root_python=True)
    except ValueError:
        slug = f"{slug}_node"
    return slug


def new_plugin_identity(name: object) -> PluginIdentity:
    visible_name = _visible_name(name)
    slug = _slug(visible_name)
    return PluginIdentity(
        visible_name=visible_name,
        slug=slug,
        filename=f"{slug}.py",
        function_name=slug,
        node_id=f"custom.{slug}.{secrets.token_hex(4)}",
    )


def suggest_plugin_filename(name: object) -> str:
    return f"{_slug(_visible_name(name))}.py"


def render_plugin_template(
    identity: PluginIdentity,
    *,
    visible_name: object | None = None,
) -> str:
    if not isinstance(identity, PluginIdentity):
        raise TypeError("identity must be a PluginIdentity")
    name = identity.visible_name if visible_name is None else _visible_name(visible_name)
    return f'''import corex


@corex.node(
    id={identity.node_id!r},
    name={name!r},
    category=("Custom",),
)
@corex.input("value", value_type=float, required=True, label="Value")
@corex.output("result", value_type=float, label="Result")
def {identity.function_name}(ctx, value):
    return {{"result": value}}
'''


def _encoded_source(source: object) -> bytes:
    if not isinstance(source, str):
        raise TypeError("Plugin source must be a string")
    try:
        payload = source.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ValueError("Plugin source must be valid UTF-8") from exc
    if len(payload) > PLUGIN_SOURCE_LIMIT:
        raise ValueError("Plugin source is too large")
    return payload


def _visible_python_filename(filename: object) -> str:
    try:
        value = validated_plugin_member_path(filename, root_python=True)
    except ValueError as exc:
        raise ValueError("Plugin filename must be a safe direct-child .py name") from exc
    if value.startswith((".", "_")):
        raise ValueError("Plugin filename must be a visible direct-child .py name")
    return value


def _error_report(
    filename: object,
    error: BaseException,
) -> PluginValidationReport:
    if isinstance(error, PluginDeclarationError):
        reported_filename = error.filename
        line = error.line
        column = error.column
        message = error.message
    else:
        reported_filename = filename if isinstance(filename, str) else "plugin.py"
        line = 1
        column = 1
        message = (
            "Plugin draft could not be validated"
            if isinstance(error, OSError)
            else str(error) or "Plugin draft is invalid"
        )
    return PluginValidationReport(
        success=False,
        diagnostics=(
            PluginAuthoringDiagnostic(
                filename=reported_filename,
                line=line,
                column=column,
                severity="error",
                message=message,
            ),
        ),
        summary=_EMPTY_SUMMARY,
    )


def summarize_plugin_registry(registry: NodeRegistry) -> PluginValidationReport:
    if not isinstance(registry, NodeRegistry):
        raise TypeError("registry must be a NodeRegistry")
    diagnostics: list[PluginAuthoringDiagnostic] = []
    unavailable_count = 0
    for spec in sorted(registry.all_specs(), key=lambda item: item.type_id):
        function_ref = registry.python_function_ref_or_none(spec.type_id)
        if (
            function_ref is None
            or function_ref.bundle_id == INTERNAL_BUILTIN_FUNCTION_OWNER_ID
        ):
            continue
        unavailable_reason = registry.unavailable_reason(spec.type_id)
        if unavailable_reason:
            unavailable_count += 1
        diagnostics.append(
            PluginAuthoringDiagnostic(
                filename=function_ref.module_relative_path,
                line=1,
                column=1,
                severity="warning" if unavailable_reason else "info",
                message=unavailable_reason or "Node declaration is valid.",
                node_id=spec.type_id,
                digest=function_ref.source_digest,
                unavailable_reason=unavailable_reason,
            )
        )
    external_bundles = tuple(
        bundle
        for bundle in registry.plugin_bundle_refs()
        if bundle.owner_id != INTERNAL_BUILTIN_FUNCTION_OWNER_ID
    )
    return PluginValidationReport(
        success=True,
        diagnostics=tuple(diagnostics),
        summary=PluginAuthoringSummary(
            bundle_count=len(external_bundles),
            node_count=len(diagnostics),
            plugin_digest=registry_plugin_fingerprint(registry, external_bundles),
            unavailable_node_count=unavailable_count,
        ),
    )


def validate_plugin_draft(
    source: object,
    filename: object,
    base_registry: NodeRegistry,
) -> PluginValidationReport:
    try:
        payload = _encoded_source(source)
        safe_filename = _visible_python_filename(filename)
        if not isinstance(base_registry, NodeRegistry):
            raise TypeError("base_registry must be a NodeRegistry")
        with tempfile.TemporaryDirectory(prefix="corex-plugin-draft-") as temporary:
            temporary_root = Path(temporary)
            draft_root = temporary_root / "draft"
            draft_root.mkdir()
            (draft_root / safe_filename).write_bytes(payload)
            candidate = base_registry.trusted_runtime_copy()
            result = discover_static_plugin_candidate(
                candidate,
                roots=(draft_root,),
                generation_root=temporary_root / "generations",
            )
            if not result.type_ids:
                raise ValueError("Plugin draft must declare at least one node")
            candidate.freeze()
            return summarize_plugin_registry(candidate)
    except (OSError, TypeError, ValueError, PluginDeclarationError) as exc:
        return _error_report(filename, exc)


def _direct_plugin_path(path: object, root: Path) -> Path:
    try:
        candidate = Path(path)  # type: ignore[arg-type]
    except TypeError:
        raise ValueError("Saved plugin draft path is invalid") from None
    if not candidate.is_absolute() and len(candidate.parts) != 1:
        raise ValueError("Saved plugin draft must be a direct installed file")
    target_root = root.absolute()
    target = candidate.absolute() if candidate.is_absolute() else target_root / candidate
    if target.parent != target_root:
        raise ValueError("Saved plugin draft must be a direct installed file")
    _visible_python_filename(target.name)
    return target


def read_saved_plugin_draft(
    path: object,
    *,
    root: Path | None = None,
) -> str:
    target_root = Path(root) if root is not None else plugins_dir()
    if is_reparse_point(target_root) or not target_root.is_dir():
        raise ValueError("Plugin folder must be a regular directory")
    target = _direct_plugin_path(path, target_root)
    if is_reparse_point(target) or not target.is_file():
        raise ValueError("Saved plugin draft is unavailable")
    try:
        before = validate_plugin_regular_file(target)
        if before.st_size > PLUGIN_SOURCE_LIMIT:
            raise ValueError("Saved plugin draft is too large")
        with target.open("rb") as stream:
            opened = os.fstat(stream.fileno())
            payload = stream.read(PLUGIN_SOURCE_LIMIT + 1)
        after = validate_plugin_regular_file(target)
    except OSError:
        raise ValueError("Saved plugin draft could not be read") from None
    if (
        not stat.S_ISREG(opened.st_mode)
        or opened.st_nlink != 1
        or (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino)
        or (after.st_dev, after.st_ino) != (opened.st_dev, opened.st_ino)
        or is_reparse_point(target)
    ):
        raise ValueError("Saved plugin draft changed while it was read")
    if len(payload) > PLUGIN_SOURCE_LIMIT:
        raise ValueError("Saved plugin draft is too large")
    try:
        return payload.decode("utf-8")
    except UnicodeDecodeError:
        raise ValueError("Saved plugin draft must be UTF-8") from None


def save_plugin_draft(
    source: object,
    filename: object,
    expected_source: object | None = None,
    *,
    root: Path | None = None,
) -> Path:
    payload = _encoded_source(source)
    safe_filename = _visible_python_filename(filename)
    expected_payload = (
        None if expected_source is None else _encoded_source(expected_source)
    )
    target_root = Path(root) if root is not None else plugins_dir()
    with _SAVE_LOCK:
        try:
            target_root.mkdir(parents=True, exist_ok=True)
        except OSError:
            raise ValueError("Plugin folder is unavailable") from None
        if is_reparse_point(target_root) or not target_root.is_dir():
            raise ValueError("Plugin folder must be a regular directory")

        destination = target_root / safe_filename
        if is_reparse_point(destination):
            raise ValueError("Plugin draft target must not be a path alias")
        if expected_payload is None and destination.exists():
            validate_plugin_regular_file(destination)
            raise ValueError("Plugin draft already exists")
        if expected_payload is not None:
            try:
                current_source = read_saved_plugin_draft(destination, root=target_root)
            except ValueError:
                raise ValueError("Plugin draft changed since it was opened") from None
            if current_source.encode("utf-8") != expected_payload:
                raise ValueError("Plugin draft changed since it was opened")

        temporary_path: Path | None = None
        descriptor = -1
        try:
            descriptor, temporary = tempfile.mkstemp(
                prefix=f".{safe_filename}.",
                suffix=".tmp",
                dir=target_root,
            )
            temporary_path = Path(temporary)
            with os.fdopen(descriptor, "wb") as stream:
                descriptor = -1
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            validate_plugin_regular_file(temporary_path)
            if expected_payload is None:
                os.link(temporary_path, destination)
            else:
                current_source = read_saved_plugin_draft(destination, root=target_root)
                if current_source.encode("utf-8") != expected_payload:
                    raise ValueError("Plugin draft changed since it was opened")
                os.replace(temporary_path, destination)
        except FileExistsError:
            raise ValueError("Plugin draft already exists") from None
        except OSError:
            raise ValueError("Plugin draft could not be saved") from None
        finally:
            if descriptor >= 0:
                os.close(descriptor)
            if temporary_path is not None:
                try:
                    temporary_path.unlink(missing_ok=True)
                except OSError:
                    pass
        return destination


__all__ = [
    "PluginAuthoringDiagnostic",
    "PluginAuthoringSummary",
    "PluginIdentity",
    "PluginValidationReport",
    "new_plugin_identity",
    "read_saved_plugin_draft",
    "render_plugin_template",
    "save_plugin_draft",
    "summarize_plugin_registry",
    "suggest_plugin_filename",
    "validate_plugin_draft",
]
