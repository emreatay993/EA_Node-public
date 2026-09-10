# Purpose: Declare Paramiko-free SSH/SFTP data-type contracts.
# Map: feature_routes/ssh_sftp_nodes.md
# Tests: tests/test_ssh_sftp_node_contracts.py

from __future__ import annotations

from ea_node_editor.nodes.builtins.ssh_sftp_values import (
    _coerce_host,
    _coerce_secret,
)
from ea_node_editor.nodes.core_data_types import GRAPH_DATA_TYPE_ID
from ea_node_editor.runtime_contracts import DataTypeFamilySpec, DataTypeSpec


SSH_SFTP_HOST_DATA_TYPE_ID = (
    "SSH_SFTP_Connector.Nodes.Control.SSH_SFTP.SshSftpHostData"
)
SSH_SFTP_SECRET_DATA_TYPE_ID = "SSH_SFTP_Connector.Nodes.Control.SSH_SFTP.SecretData"
SSH_SFTP_DATA_TYPE_OWNER_ID = "corex.ssh_sftp"


def _is_secret_data(value: object) -> bool:
    try:
        return _coerce_secret(value, input_name="Secret") is not None
    except (TypeError, ValueError):
        return False


def _is_host_data(value: object) -> bool:
    try:
        _coerce_host(value)
    except (TypeError, ValueError):
        return False
    return True


SSH_SFTP_DATA_TYPE_FAMILIES = (
    DataTypeFamilySpec("ssh_sftp", "SSH/SFTP", "data.integration", "network"),
)
SSH_SFTP_DATA_TYPES = (
    DataTypeSpec(
        SSH_SFTP_SECRET_DATA_TYPE_ID,
        "Secret",
        "ssh_sftp",
        _is_secret_data,
        parents=(GRAPH_DATA_TYPE_ID,),
        persistence="never",
        sensitivity="secret",
    ),
    DataTypeSpec(
        SSH_SFTP_HOST_DATA_TYPE_ID,
        "SSH/SFTP Host",
        "ssh_sftp",
        _is_host_data,
        parents=(GRAPH_DATA_TYPE_ID,),
        persistence="never",
        sensitivity="sensitive",
    ),
)


__all__ = [
    "SSH_SFTP_DATA_TYPE_FAMILIES",
    "SSH_SFTP_DATA_TYPE_OWNER_ID",
    "SSH_SFTP_DATA_TYPES",
    "SSH_SFTP_HOST_DATA_TYPE_ID",
    "SSH_SFTP_SECRET_DATA_TYPE_ID",
]
