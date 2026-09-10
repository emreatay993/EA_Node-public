from __future__ import annotations

from ea_node_editor.execution.worker_services import WorkerServices
from ea_node_editor.nodes.core_data_types import (
    CORE_DATA_CONVERSIONS,
    CORE_DATA_TYPE_FAMILIES,
    CORE_DATA_TYPE_OWNER_ID,
    CORE_DATA_TYPE_OWNER_VERSION,
    CORE_DATA_TYPES,
)
from ea_node_editor.runtime_contracts import DataTypeCatalog


def core_data_type_catalog() -> DataTypeCatalog:
    catalog = DataTypeCatalog()
    catalog.register_many(
        families=CORE_DATA_TYPE_FAMILIES,
        types=CORE_DATA_TYPES,
        conversions=CORE_DATA_CONVERSIONS,
        owner_id=CORE_DATA_TYPE_OWNER_ID,
        owner_version=CORE_DATA_TYPE_OWNER_VERSION,
    )
    catalog.freeze()
    return catalog


def core_worker_services() -> WorkerServices:
    services = WorkerServices()
    services.bind_data_types(core_data_type_catalog())
    return services


__all__ = [
    "core_data_type_catalog",
    "core_worker_services",
]
