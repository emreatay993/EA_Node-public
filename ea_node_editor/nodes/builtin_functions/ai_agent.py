# Purpose: Hold inert decorated source for offline AI agent configuration.
# Map: subsystems/nodes_registry_builtins.md
# Tests: tests/test_rich_values.py

SOURCE = r"""import corex

from ea_node_editor.nodes.builtins.rich_value_nodes import make_agent_model_value


@corex.node(
    id="ai.large_language_model",
    name="Large Language Model",
    category=("AI", "Agent"),
    icon="smart_toy",
    description="Builds offline provider and model configuration for an agent.",
    keywords=("AI", "Agent", "LLM", "Model", "Provider", "Configuration"),
)
@corex.output(
    "model",
    value_type="COREX.DataTypes.MultiAgentSystem.AgentModel",
    label="Agent Model",
    description="Validated provider and model configuration.",
)
@corex.text(
    "provider_id",
    default="corex-server",
    label="Provider ID",
    description="Offline provider identifier; no credentials or client are stored.",
    _inline_editor="",
)
@corex.text(
    "model_id",
    default="",
    label="Model ID",
    description="Model identifier emitted as configuration only.",
    _inline_editor="",
)
def large_language_model(ctx, settings):
    del ctx
    return {"model": make_agent_model_value(settings.provider_id, settings.model_id)}
"""

__all__ = ["SOURCE"]
