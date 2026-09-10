from __future__ import annotations

from tests.graph_surface.inline_editor_suite import (
    GraphSurfaceInlineEditorContractTests,
    PassiveGraphSurfaceInlineEditorTests,
)
from tests.graph_surface.media_and_scope_suite import (
    GraphSurfaceMediaAndScopeContractTests,
    PassiveGraphSurfaceMediaAndScopeTests,
)
from tests.graph_surface.passive_host_boundary_suite import (
    GraphSurfaceBoundaryContractTests,
    PassiveGraphSurfaceHostBoundaryTests,
)
from tests.graph_surface.number_slider_suite import (
    NumberSliderSurfaceContractTests,
    PassiveNumberSliderSurfaceTests,
)
from tests.graph_surface.passive_host_interaction_suite import PassiveGraphSurfaceHostTests
from tests.graph_surface.pointer_and_modal_suite import GraphSurfaceInputContractTests
from tests.graph_surface.p03_input_contract_suite import (
    GraphSurfaceDefaultPropertyContractTests,
    GraphSurfaceFolderExplorerBridgeContractTests,
    GraphSurfaceWebBoardLoaderContractTests,
    GraphSurfaceWebPageLoaderContractTests,
)
from tests.graph_surface.p03_passive_host_entrypoint_suite import (
    ExcalidrawWebBoardPassiveGraphHostTests,
    LockedPlaceholderGraphHostTests,
)

__all__ = [
    "ExcalidrawWebBoardPassiveGraphHostTests",
    "GraphSurfaceBoundaryContractTests",
    "GraphSurfaceFolderExplorerBridgeContractTests",
    "GraphSurfaceInlineEditorContractTests",
    "GraphSurfaceInputContractTests",
    "GraphSurfaceDefaultPropertyContractTests",
    "GraphSurfaceMediaAndScopeContractTests",
    "GraphSurfaceWebBoardLoaderContractTests",
    "GraphSurfaceWebPageLoaderContractTests",
    "LockedPlaceholderGraphHostTests",
    "NumberSliderSurfaceContractTests",
    "PassiveGraphSurfaceHostBoundaryTests",
    "PassiveNumberSliderSurfaceTests",
    "PassiveGraphSurfaceHostTests",
    "PassiveGraphSurfaceInlineEditorTests",
    "PassiveGraphSurfaceMediaAndScopeTests",
]
