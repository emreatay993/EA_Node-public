# Purpose: Evaluate declarative node prerequisites without invoking node plugins.
# Map: subsystems/nodes_registry_builtins.md
# Tests: tests/test_registry_validation.py

from __future__ import annotations

from collections.abc import Collection, Mapping
from dataclasses import dataclass

from .node_specs import NodeTypeSpec, ReadinessRequirementSpec


@dataclass(slots=True, frozen=True)
class ReadinessIssue:
    code: str
    target_keys: tuple[str, ...]
    target_labels: tuple[str, ...]
    message: str


def readiness_value_is_present(value: object, *, allow_empty_string: bool = False) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        if allow_empty_string and value == "":
            return True
        return bool(value.strip())
    if isinstance(value, (bytes, bytearray, memoryview)):
        return bool(value)
    if isinstance(value, Collection):
        return bool(value)
    return True


def evaluate_node_readiness(
    spec: NodeTypeSpec,
    *,
    port_has_value: Mapping[str, bool],
    overridden_port_keys: Collection[str],
    properties: Mapping[str, object],
) -> tuple[ReadinessIssue, ...]:
    ports_by_key = {port.key: port for port in spec.ports}
    properties_by_key = {prop.key: prop for prop in spec.properties}
    overridden = set(overridden_port_keys)

    def port_is_present(key: str) -> bool:
        if port_has_value.get(key, False):
            return True
        port = ports_by_key[key]
        return (
            port.uses_property_default
            and key not in overridden
            and readiness_value_is_present(
                properties.get(key), allow_empty_string=port.allow_empty_string
            )
        )

    issues: list[ReadinessIssue] = []
    for port in spec.ports:
        if port.required is True and not port_is_present(port.key):
            issues.append(
                _readiness_issue(
                    port_keys=(port.key,),
                    property_keys=(),
                    ports_by_key=ports_by_key,
                    properties_by_key=properties_by_key,
                )
            )

    for requirement in spec.readiness_requirements:
        if not _requirement_is_active(requirement, port_has_value, properties):
            continue
        if any(port_is_present(key) for key in requirement.any_of_ports):
            continue
        if any(readiness_value_is_present(properties.get(key)) for key in requirement.any_of_properties):
            continue
        issues.append(
            _readiness_issue(
                port_keys=requirement.any_of_ports,
                property_keys=requirement.any_of_properties,
                ports_by_key=ports_by_key,
                properties_by_key=properties_by_key,
            )
        )
    return tuple(issues)


def _requirement_is_active(
    requirement: ReadinessRequirementSpec,
    port_has_value: Mapping[str, bool],
    properties: Mapping[str, object],
) -> bool:
    if not all(port_has_value.get(key, False) for key in requirement.when_ports_present):
        return False
    for condition in requirement.when_properties:
        value = properties.get(condition.property_key)
        if condition.values:
            if not any(value == candidate for candidate in condition.values):
                return False
        elif not readiness_value_is_present(value):
            return False
    return True


def _readiness_issue(
    *,
    port_keys: tuple[str, ...],
    property_keys: tuple[str, ...],
    ports_by_key: Mapping[str, object],
    properties_by_key: Mapping[str, object],
) -> ReadinessIssue:
    target_keys = port_keys + property_keys
    port_labels = tuple(_label(ports_by_key[key]) for key in port_keys)
    property_labels = tuple(_label(properties_by_key[key]) for key in property_keys)
    target_labels = port_labels + property_labels

    if len(port_keys) == 1 and not property_keys:
        message = (
            f"The node has not been computed because the {port_labels[0]} input did not receive any "
            "data yet. Please provide data for all mandatory inputs and check your upstream workflow "
            "for errors or missing wires."
        )
    elif not port_keys:
        if len(property_labels) == 1:
            message = (
                f"The node has not been computed because the {property_labels[0]} setting is empty. "
                "Please provide a value for this mandatory setting."
            )
        else:
            message = (
                "The node has not been computed because the required settings are empty. "
                f"Please provide at least one of: {', '.join(property_labels)}."
            )
    else:
        message = (
            "The node has not been computed because none of the required alternatives received data. "
            f"Please provide at least one of: {', '.join(target_labels)}."
        )
    return ReadinessIssue(
        code="required_input_waiting",
        target_keys=target_keys,
        target_labels=target_labels,
        message=message,
    )


def _label(spec: object) -> str:
    label = str(getattr(spec, "label", "")).strip()
    if label:
        return label
    return str(getattr(spec, "key")).replace("_", " ").title()


__all__ = [
    "ReadinessIssue",
    "evaluate_node_readiness",
    "readiness_value_is_present",
]
