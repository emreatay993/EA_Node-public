from __future__ import annotations

import pytest

from ea_node_editor.nodes.internalized_values import decode_internalized_data_tree
from ea_node_editor.runtime_contracts import DataTree


def test_internalized_data_tree_decodes_exact_payload() -> None:
    payload = (
        b'{"Branches":[[1]],"Paths":['
        b'{"$type":"COREX.DataTree.Path","Indices":[0,2]}]}'
    )

    assert decode_internalized_data_tree(
        payload=payload,
        path_type="COREX.DataTree.Path",
        decode_leaf=lambda value: value,
        error_message="invalid tree",
    ) == DataTree((((0, 2), (1,)),))


@pytest.mark.parametrize(
    "payload",
    (
        b'{"Branches":[[1]],"Branches":[[2]],"Paths":[]}',
        b'{"Branches":[[1]],"Paths":[{"$type":"Other","Indices":[0]}]}',
        b'{"Branches":[[NaN]],"Paths":[{"$type":"COREX.DataTree.Path","Indices":[0]}]}',
    ),
)
def test_internalized_data_tree_rejects_unsafe_or_mismatched_payload(
    payload: bytes,
) -> None:
    with pytest.raises(ValueError, match="invalid tree"):
        decode_internalized_data_tree(
            payload=payload,
            path_type="COREX.DataTree.Path",
            decode_leaf=lambda value: value,
            error_message="invalid tree",
        )
