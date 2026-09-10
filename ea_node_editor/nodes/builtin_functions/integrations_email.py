# Purpose: Hold inert decorated source for the Email Send integration.
# Map: feature_routes/core_integrations_file_process_email_spreadsheet.md
# Tests: tests/test_integrations_track_f.py

SOURCE = r"""import corex

from ea_node_editor.nodes.builtins.integrations_email import execute_email_send


@corex.node(
    id="io.email_send",
    name="Email Send",
    category=("Input / Output",),
    icon="integrations/mail.svg",
    description="Sends a plaintext email through a configured SMTP server.",
    keywords=("email", "smtp", "notification"),
    _readiness_requirements=(
        {"any_of_properties": ("smtp_host",)},
        {"any_of_properties": ("sender",)},
        {"any_of_properties": ("to",)},
        {
            "any_of_properties": ("password",),
            "when_properties": ({"property_key": "username"},),
        },
    ),
)
@corex.text(
    "smtp_host",
    default="localhost",
    label="SMTP Host",
    _inline_editor="",
)
@corex.number(
    "smtp_port",
    default=25,
    label="SMTP Port",
    _inline_editor="",
)
@corex.text(
    "username",
    default="",
    label="Username",
    _inline_editor="",
)
@corex.text(
    "password",
    default="",
    label="Password",
    _inline_editor="",
)
@corex.text(
    "sender",
    default="",
    label="Sender",
    _inline_editor="",
)
@corex.text(
    "to",
    default="",
    label="To",
    _inline_editor="",
)
@corex.text(
    "subject",
    default="COREX Node Editor Notification",
    label="Subject",
    port=True,
    _inline_editor="",
    _port_description="Email subject; overrides the configured Subject property when connected.",
    _port_label="",
    _port_required=False,
    _port_structure="tree",
    _port_value_type="COREX.DataTypes.String",
)
@corex.text(
    "body",
    default="Workflow run completed.",
    label="Body",
    port=True,
    _inline_editor="",
    _port_description="Plaintext email body; overrides the configured Body property when connected.",
    _port_label="",
    _port_required=False,
    _port_structure="tree",
    _port_value_type="COREX.DataTypes.String",
)
@corex.switch(
    "use_tls",
    default=False,
    label="Use TLS",
    _inline_editor="",
)
@corex.output(
    "sent",
    value_type=bool,
    label="",
    description="True after the SMTP server accepts the message.",
)
def email_send(ctx, settings):
    result = execute_email_send(ctx)
    for warning in result.warnings:
        ctx.warn(warning, code="email_send")
    return dict(result.outputs)
"""

__all__ = ["SOURCE"]
