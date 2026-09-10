# Purpose: Define COREX's immutable, path-ordered runtime DataTree value.
# Map: docs/agent_maps/subsystems/supporting_runtime_assets.md
# Tests: tests/test_data_tree_contract.py

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal, TypeAlias

DataPath: TypeAlias = tuple[int, ...]
DataAccess = Literal["item", "list", "tree"]
DataTreeModifier = Literal["graft", "flatten", "simplify", "reverse", "clean"]

DATA_TREE_MODIFIER_ORDER: tuple[DataTreeModifier, ...] = (
    "graft",
    "flatten",
    "simplify",
    "reverse",
    "clean",
)

_BranchInput: TypeAlias = (
    Mapping[Iterable[int], Sequence[Any]]
    | Iterable[tuple[Iterable[int], Sequence[Any]]]
)


def _normalize_path(path: Iterable[int]) -> DataPath:
    try:
        normalized = tuple(path)
    except TypeError as exc:
        raise TypeError("DataTree paths must be iterable integer sequences") from exc
    if any(type(index) is not int for index in normalized):
        raise TypeError("DataTree path indexes must be integers")
    return normalized


def _normalize_items(items: Sequence[Any]) -> tuple[Any, ...]:
    if isinstance(items, (str, bytes, bytearray)) or not isinstance(items, Sequence):
        raise TypeError("DataTree branches must contain ordered item sequences")
    return tuple(items)


@dataclass(frozen=True, slots=True, init=False)
class DataTree(Mapping[DataPath, tuple[Any, ...]]):
    """Immutable tree topology with lexicographically ordered paths."""

    _branches: tuple[tuple[DataPath, tuple[Any, ...]], ...]
    __hash__ = None

    def __init__(self, branches: _BranchInput = ()) -> None:
        raw_branches = branches.items() if isinstance(branches, Mapping) else branches
        normalized: list[tuple[DataPath, tuple[Any, ...]]] = []
        seen_paths: set[DataPath] = set()
        for path, items in raw_branches:
            normalized_path = _normalize_path(path)
            if normalized_path in seen_paths:
                raise ValueError(f"DataTree contains duplicate path: {normalized_path!r}")
            seen_paths.add(normalized_path)
            normalized.append((normalized_path, _normalize_items(items)))
        object.__setattr__(self, "_branches", tuple(sorted(normalized, key=lambda branch: branch[0])))

    @classmethod
    def from_item(cls, value: Any, *, path: DataPath = (0,)) -> DataTree:
        return cls(((path, (value,)),))

    @classmethod
    def from_list(cls, values: Sequence[Any], *, path: DataPath = (0,)) -> DataTree:
        return cls(((path, values),))

    def __iter__(self) -> Iterator[DataPath]:
        return (path for path, _items in self._branches)

    def __len__(self) -> int:
        return len(self._branches)

    def __getitem__(self, path: DataPath) -> tuple[Any, ...]:
        normalized_path = _normalize_path(path)
        for candidate, items in self._branches:
            if candidate == normalized_path:
                return items
        raise KeyError(normalized_path)

    @property
    def branches(self) -> tuple[tuple[DataPath, tuple[Any, ...]], ...]:
        return self._branches

    @property
    def paths(self) -> tuple[DataPath, ...]:
        return tuple(path for path, _items in self._branches)

    @property
    def branch_count(self) -> int:
        return len(self._branches)

    @property
    def item_count(self) -> int:
        return sum(len(items) for _path, items in self._branches)

    def merge(self, *others: DataTree) -> DataTree:
        """Merge trees in argument order, concatenating items at equal paths."""

        merged: dict[DataPath, list[Any]] = {}
        for tree in (self, *others):
            if not isinstance(tree, DataTree):
                raise TypeError("DataTree.merge accepts only DataTree values")
            for path, items in tree._branches:
                merged.setdefault(path, []).extend(items)
        return DataTree(merged)

    def graft(self) -> DataTree:
        return DataTree(
            (path + (ordinal,), (item,))
            for path, items in self._branches
            for ordinal, item in enumerate(items)
        )

    def flatten(self) -> DataTree:
        return DataTree((((0,), tuple(item for _path, items in self._branches for item in items)),))

    def simplify(self) -> DataTree:
        if not self._branches:
            return self
        paths = self.paths
        removable = max(0, min(len(path) - 1 for path in paths))
        prefix_length = 0
        while prefix_length < removable:
            index = paths[0][prefix_length]
            if any(path[prefix_length] != index for path in paths[1:]):
                break
            prefix_length += 1
        if not prefix_length:
            return self
        return DataTree((path[prefix_length:], items) for path, items in self._branches)

    def reverse(self) -> DataTree:
        return DataTree((path, tuple(reversed(items))) for path, items in self._branches)

    def clean(self) -> DataTree:
        cleaned = (
            (path, tuple(item for item in items if item is not None))
            for path, items in self._branches
        )
        return DataTree((path, items) for path, items in cleaned if items)

    def apply_modifiers(self, modifiers: Iterable[DataTreeModifier]) -> DataTree:
        selected = set(modifiers)
        unsupported = selected.difference(DATA_TREE_MODIFIER_ORDER)
        if unsupported:
            values = ", ".join(sorted(repr(value) for value in unsupported))
            raise ValueError(f"Unsupported DataTree modifier: {values}")
        result = self
        for modifier in DATA_TREE_MODIFIER_ORDER:
            if modifier in selected:
                result = getattr(result, modifier)()
        return result


def resolve_single_run_inputs(
    inputs: Mapping[str, Any],
    *,
    node_name: str,
    list_ports: Iterable[str] = (),
) -> dict[str, Any]:
    """Unwrap Tree-access inputs for a plugin that must execute only once."""

    list_port_keys = frozenset(list_ports)
    resolved = dict(inputs)
    for port_key, value in inputs.items():
        if not isinstance(value, DataTree):
            continue
        items = tuple(item for _path, branch in value.branches for item in branch)
        if port_key in list_port_keys:
            resolved[port_key] = list(items)
            continue
        if len(items) != 1:
            raise ValueError(
                f"{node_name} input '{port_key}' requires exactly one item across its "
                f"DataTree; received {value.branch_count} branches and {len(items)} items."
            )
        resolved[port_key] = items[0]
    return resolved


__all__ = [
    "DATA_TREE_MODIFIER_ORDER",
    "DataAccess",
    "DataPath",
    "DataTree",
    "DataTreeModifier",
    "resolve_single_run_inputs",
]
