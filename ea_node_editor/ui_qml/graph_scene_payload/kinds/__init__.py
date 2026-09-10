from __future__ import annotations

"""Per-kind payload contributor registry.

THE insertion point for kind-specific node-payload behavior. Dispatch is
keyed exactly like ``surface_contracts.py``: a type-id override (excalidraw),
then surface family / (family, variant) checks. Resolution is cached per
``(type_id, family, variant)`` so the per-node build loop never re-derives
the contributor list (hot path during full scene rebuilds).

Contracts:
- ``contribute(payload, ctx)`` mutates the assembled payload dict in place;
  ``ctx`` is the frozen ``factory.PayloadBuildContext``. Contributors run in
  REGISTRATION ORDER, which preserves the historical tail order of
  ``build_node_payload`` (excalidraw, viewer, web page, plot). Do not
  reorder.
- ``normalize_properties(properties, *, node, spec, boundary_adapters)``
  returns the (possibly replaced) properties dict used for the payload node;
  normalizers run in registration order.

Adding a payload field for a node kind = edit that kind's module here plus
the consuming surface QML. Nothing else in the pipeline should need edits.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable

from ea_node_editor.nodes.builtins.excalidraw import EXCALIDRAW_BOARD_TYPE_ID
from ea_node_editor.ui_qml.graph_scene_payload.kinds import (
    group_backdrop,  # noqa: F401  (registered insertion point, no hooks yet)
    excalidraw,
    jupyter,
    plot,
    viewer,
    web_page,
)
from ea_node_editor.ui_qml.graph_scene_payload.normalize import (
    _is_web_page_surface_spec,
)

if TYPE_CHECKING:
    from ea_node_editor.nodes.node_specs import NodeTypeSpec
    from ea_node_editor.ui_qml.graph_scene_payload.factory import PayloadBuildContext

PayloadContributor = Callable[[dict[str, Any], "PayloadBuildContext"], None]
PropertyNormalizer = Callable[..., dict[str, Any]]


@dataclass(frozen=True, slots=True)
class KindDispatch:
    contributors: tuple[PayloadContributor, ...]
    property_normalizers: tuple[PropertyNormalizer, ...]


_DISPATCH_CACHE: dict[tuple[str, str, str], KindDispatch] = {}


def kind_dispatch_for_spec(*, type_id: object, spec: "NodeTypeSpec") -> KindDispatch:
    normalized_type_id = str(type_id or "").strip()
    family = str(getattr(spec, "surface_family", "") or "").strip()
    variant = str(getattr(spec, "surface_variant", "") or "").strip()
    key = (normalized_type_id, family, variant)
    cached = _DISPATCH_CACHE.get(key)
    if cached is not None:
        return cached

    contributors: list[PayloadContributor] = []
    property_normalizers: list[PropertyNormalizer] = []
    if normalized_type_id == EXCALIDRAW_BOARD_TYPE_ID:
        contributors.append(excalidraw.contribute)
    if family == "viewer":
        contributors.append(viewer.contribute)
    if _is_web_page_surface_spec(type_id=normalized_type_id, spec=spec):
        contributors.append(web_page.contribute)
        property_normalizers.append(web_page.normalize_properties)
    if family == "jupyter":
        contributors.append(jupyter.contribute)
        property_normalizers.append(jupyter.normalize_properties)
    if plot.plot_type_for_values(type_id=normalized_type_id, surface_variant=variant):
        contributors.append(plot.contribute)
    dispatch = KindDispatch(tuple(contributors), tuple(property_normalizers))
    _DISPATCH_CACHE[key] = dispatch
    return dispatch


__all__ = [
    "KindDispatch",
    "PayloadContributor",
    "PropertyNormalizer",
    "kind_dispatch_for_spec",
]
