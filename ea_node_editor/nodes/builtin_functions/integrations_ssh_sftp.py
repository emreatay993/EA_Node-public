# Purpose: Hold inert decorated source for SSH/SFTP built-ins.
# Map: feature_routes/ssh_sftp_nodes.md
# Tests: tests/test_ssh_sftp_node_contracts.py

SOURCE = r'''import corex

from ea_node_editor.nodes.builtins.ssh_sftp_values import compute_host, compute_secret


DATA_PROTECTION_SCOPES = ("Current user", "All users on this machine")
SCRIPT_INTERPRETERS = ("Bash", "sh", "Python 3", "Python 2", "Perl", "Custom")
HOST_TYPE = "SSH_SFTP_Connector.Nodes.Control.SSH_SFTP.SshSftpHostData"
SECRET_TYPE = "SSH_SFTP_Connector.Nodes.Control.SSH_SFTP.SecretData"


def _outputs(ctx, result):
    for warning in result.warnings:
        ctx.warn(warning, code="ssh_sftp_runtime")
    return result.outputs


@corex.node(
    id="ssh_sftp.secret",
    name="Secret",
    category=("Control", "SSH/SFTP"),
    icon="ssh_sftp/lock.svg",
    description="Store strings securely as secrets using Windows Data Protection API. Decryption can be limited to the current user or all users on this machine.",
    keywords=("Secure", "Encrypted", "Password", "Credentials"),
)
@corex.output(
    "secret_value",
    value_type=SECRET_TYPE,
    label="Secret value",
    description="Holds the encrypted value in a SecretData type.",
)
@corex.text(
    "protected_value",
    default="",
    label="Value",
    description="Write-only secret value protected by Windows Data Protection API.",
    _property_type="json",
    _property_default={},
    _inline_editor="secret",
    _inspector_editor="secret",
    _persistence_type=None,
    _sensitive=True,
    _sensitive_scope_key="data_protection_scope",
)
@corex.dropdown(
    "data_protection_scope",
    default="Current user",
    options=DATA_PROTECTION_SCOPES,
    label="Data Protection Scope",
    description="Choose who on this Windows machine can decrypt the secret.",
    _inspector_editor="enum",
)
def secret(ctx, settings):
    return _outputs(ctx, compute_secret(ctx))


@corex.node(
    id="ssh_sftp.host",
    name="SSH/SFTP Host",
    category=("Control", "SSH/SFTP"),
    icon="ssh_sftp/server.svg",
    description="Representing a SSH Host to be used with the SSH/SFTP/SCP-Command nodes.",
    keywords=("FTP", "SCP", "Linux", "Unix", "Authentication", "Upload", "Download", "HPC"),
)
@corex.input(
    "address",
    value_type=str,
    required=True,
    label="Address",
    description="Hostname or IP address of the host.",
)
@corex.number(
    "port",
    default=22,
    label="Port",
    port=True,
    _inline_editor="",
    _inspector_editor="",
    _port_required=False,
    _port_description="Port for SSH, defaults to 22.",
)
@corex.input(
    "username",
    value_type=str,
    required=True,
    label="Username",
    description="Username of the user you want to authenticate with.",
)
@corex.input(
    "password",
    value_type=SECRET_TYPE,
    required=False,
    label="Password",
    description='Optional password, SSH keys are preferred. It is recommended to use the "Secret" node to pass in the password.',
)
@corex.input(
    "private_key_path",
    value_type=str,
    required=False,
    label="Private key path",
    description="Path to SSH private key file.",
    _accepted_data_types=("COREX.DataTypes.Path",),
)
@corex.input(
    "private_key_passphrase",
    value_type=SECRET_TYPE,
    required=False,
    label="Private key passphrase",
    description='Optional passphrase, if the private key is encrypted. It is recommended to use the "Secret" node to pass in the passphrase.',
)
@corex.switch(
    "use_openssh_agent",
    default=False,
    label="Use OpenSSH Agent",
    port=True,
    _inline_editor="",
    _inspector_editor="",
    _port_required=False,
    _port_description="If enabled, tries to authenticate using keys from the OpenSSH agent (ssh-agent).",
)
@corex.switch(
    "use_pageant",
    default=False,
    label="Use Pageant",
    port=True,
    _inline_editor="",
    _inspector_editor="",
    _port_required=False,
    _port_description="If enabled, tries to authenticate using keys from PuTTY's Pageant agent.",
)
@corex.output(
    "host",
    value_type=HOST_TYPE,
    label="SSH/SFTP Host",
    description="SSH/SFTP Host for use in related SSH/SFTP nodes.",
)
def ssh_sftp_host(
    ctx,
    address,
    username,
    password,
    private_key_path,
    private_key_passphrase,
    settings,
):
    return _outputs(ctx, compute_host(ctx))


@corex.node(
    id="ssh_sftp.run_command",
    name="Run SSH Command",
    category=("Control", "SSH/SFTP"),
    icon="ssh_sftp/terminal.svg",
    description="Run commands via SSH on a remote host.",
    keywords=("Linux", "Unix", "Execute", "Remote", "Shell", "Bash", "HPC"),
)
@corex.input(
    "target_host",
    value_type=HOST_TYPE,
    required=True,
    label="Target Host",
    description="Target host to run command on.",
)
@corex.input(
    "command",
    value_type=str,
    required=True,
    label="Command",
    description="Run a command on the target remote machine via SSH.",
)
@corex.output(
    "successful",
    value_type=bool,
    label="Successful",
    description="'True' if the command exited with exit code 0.",
)
@corex.output(
    "exit_code",
    value_type=int,
    label="Exit code",
    description="Exit or return code of the remote shell.",
)
@corex.output(
    "output",
    value_type=str,
    label="Output",
    description="Text output from the command to the shell is delivered to the stdout (standard out) stream",
)
@corex.output(
    "error",
    value_type=str,
    label="Error",
    description="Error messages from the command are sent to the stderr (standard error) stream.",
)
def run_ssh_command(ctx, target_host, command):
    from ea_node_editor.nodes.builtins.ssh_sftp_runtime import run_ssh_command

    return _outputs(ctx, run_ssh_command(ctx))


@corex.node(
    id="ssh_sftp.run_script",
    name="Run SSH Script",
    category=("Control", "SSH/SFTP"),
    icon="ssh_sftp/code.svg",
    description="Run a script via SSH on a remote host.",
    keywords=("Linux", "Unix", "Commands", "Execute", "Remote", "Shell", "Bash", "sh", "HPC"),
)
@corex.input(
    "target_host",
    value_type=HOST_TYPE,
    required=True,
    label="Target Host",
    description="Target host to run command on.",
)
@corex.input(
    "script",
    value_type=str,
    required=True,
    label="Script",
    description="The script to execute. This could be either a script as plain text or a file path to a script on the machine executing the workflow.",
)
@corex.output(
    "successful",
    value_type=bool,
    label="Successful",
    description="'True' if the script exited with exit code 0.",
)
@corex.output(
    "exit_code",
    value_type=int,
    label="Exit code",
    description="Exit or return code of the remote shell.",
)
@corex.output(
    "output",
    value_type=str,
    label="Output",
    description="Text output from the script to the shell is delivered to the stdout (standard out) stream",
)
@corex.output(
    "error",
    value_type=str,
    label="Error",
    description="Error messages from the script are sent to the stderr (standard error) stream.",
)
@corex.dropdown(
    "interpreter",
    default="Bash",
    options=SCRIPT_INTERPRETERS,
    label="Interpreter",
    description="Interpreter available on the target host; Custom uses the script shebang.",
    _inline_editor="",
    _inspector_editor="enum",
)
def run_ssh_script(ctx, target_host, script, settings):
    from ea_node_editor.nodes.builtins.ssh_sftp_runtime import run_ssh_script

    return _outputs(ctx, run_ssh_script(ctx))


@corex.node(
    id="ssh_sftp.upload",
    name="SFTP Upload",
    category=("Control", "SSH/SFTP"),
    icon="ssh_sftp/cloud_upload.svg",
    description="Upload files or directories to a remote machine via SFTP.",
    keywords=("Linux", "Unix", "SSH", "FTP", "SCP", "Put", "HPC", "Transfer"),
)
@corex.input(
    "target_host",
    value_type=HOST_TYPE,
    required=True,
    label="Target Host",
    description="Target SSH/SFTP Host to upload to.",
)
@corex.input(
    "sources",
    value_type=str,
    structure="list",
    required=True,
    label="Sources",
    description="Source files or directories to upload.",
)
@corex.input(
    "destination",
    value_type=str,
    required=True,
    label="Destination",
    description="Destination file or directory to upload to. You can use . as the destination to upload to the home directory of the user.",
)
@corex.switch(
    "overwrite",
    default=False,
    label="Overwrite existing files",
    port=True,
    _inline_editor="",
    _inspector_editor="",
    _port_required=False,
    _port_description="Allow overwriting if the source files already exists in the destination.",
)
@corex.output(
    "successful",
    value_type=bool,
    label="Successful",
    description="'True' if the upload was successful.",
)
@corex.output(
    "uploaded_bytes",
    value_type=int,
    label="Uploaded bytes",
    description="Amount of bytes uploaded.",
)
@corex.output(
    "uploaded_files",
    value_type=int,
    label="Uploaded files",
    description="Amount of files uploaded.",
)
def sftp_upload(ctx, target_host, sources, destination, settings):
    from ea_node_editor.nodes.builtins.ssh_sftp_runtime import sftp_upload

    return _outputs(ctx, sftp_upload(ctx))


@corex.node(
    id="ssh_sftp.download",
    name="SFTP Download",
    category=("Control", "SSH/SFTP"),
    icon="ssh_sftp/cloud_download.svg",
    description="Download files or directories from a remote machine via SFTP.",
    keywords=("Linux", "Unix", "SSH", "FTP", "SCP", "Get", "HPC", "Transfer"),
)
@corex.input(
    "target_host",
    value_type=HOST_TYPE,
    required=True,
    label="Target Host",
    description="Target SSH/SFTP Host to download from.",
)
@corex.input(
    "sources",
    value_type=str,
    structure="list",
    required=True,
    label="Sources",
    description="Source files or directories to download.",
)
@corex.input(
    "destination",
    value_type=str,
    required=True,
    label="Destination",
    description="Destination file or directory to download to. You can use . as the destination to download to the current working directory.",
)
@corex.switch(
    "overwrite",
    default=False,
    label="Overwrite existing files",
    port=True,
    _inline_editor="",
    _inspector_editor="",
    _port_required=False,
    _port_description="Allow overwriting if the source already exists in the destination.",
)
@corex.output(
    "successful",
    value_type=bool,
    label="Successful",
    description="'True' if the download was successful.",
)
@corex.output(
    "downloaded_bytes",
    value_type=int,
    label="Downloaded bytes",
    description="Amount of bytes Downloaded.",
)
@corex.output(
    "downloaded_files",
    value_type=int,
    label="Downloaded files",
    description="Amount of files Downloaded.",
)
def sftp_download(ctx, target_host, sources, destination, settings):
    from ea_node_editor.nodes.builtins.ssh_sftp_runtime import sftp_download

    return _outputs(ctx, sftp_download(ctx))
'''

__all__ = ["SOURCE"]
