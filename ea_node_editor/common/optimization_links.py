from __future__ import annotations

OPTIMIZATION_PARAMETER_SETUP_TYPE_ID = "optimization.parameter_setup"
OPTIMIZATION_PARAMETER_POOL_TYPE_ID = "optimization.parameter_pool"
OPTIMIZATION_RESPONSE_POOL_TYPE_ID = "optimization.response_pool"

PARAMETER_POOL_ROLE = "parameter"
RESPONSE_POOL_ROLE = "response"

PARAMETER_SETUP_PARAMETER_POOL_LINK_ID = (
    "optimization.parameter_setup.parameter_pool"
)
PARAMETER_SETUP_RESPONSE_POOL_LINK_ID = (
    "optimization.parameter_setup.response_pool"
)

PARAMETER_SETUP_PARAMETER_POOL_LINK_TITLE = "Parameter Pool"
PARAMETER_SETUP_RESPONSE_POOL_LINK_TITLE = "Response Pool"


def optimization_pool_role(node_type_id: object) -> str:
    normalized = str(node_type_id or "").strip()
    if normalized == OPTIMIZATION_PARAMETER_POOL_TYPE_ID:
        return PARAMETER_POOL_ROLE
    if normalized == OPTIMIZATION_RESPONSE_POOL_TYPE_ID:
        return RESPONSE_POOL_ROLE
    return ""


def parameter_setup_pool_link_facts(pool_role: object) -> tuple[str, str] | None:
    normalized = str(pool_role or "").strip().lower()
    if normalized == PARAMETER_POOL_ROLE:
        return (
            PARAMETER_SETUP_PARAMETER_POOL_LINK_ID,
            PARAMETER_SETUP_PARAMETER_POOL_LINK_TITLE,
        )
    if normalized == RESPONSE_POOL_ROLE:
        return (
            PARAMETER_SETUP_RESPONSE_POOL_LINK_ID,
            PARAMETER_SETUP_RESPONSE_POOL_LINK_TITLE,
        )
    return None


__all__ = [
    "OPTIMIZATION_PARAMETER_POOL_TYPE_ID",
    "OPTIMIZATION_PARAMETER_SETUP_TYPE_ID",
    "OPTIMIZATION_RESPONSE_POOL_TYPE_ID",
    "PARAMETER_POOL_ROLE",
    "PARAMETER_SETUP_PARAMETER_POOL_LINK_ID",
    "PARAMETER_SETUP_PARAMETER_POOL_LINK_TITLE",
    "PARAMETER_SETUP_RESPONSE_POOL_LINK_ID",
    "PARAMETER_SETUP_RESPONSE_POOL_LINK_TITLE",
    "RESPONSE_POOL_ROLE",
    "optimization_pool_role",
    "parameter_setup_pool_link_facts",
]
