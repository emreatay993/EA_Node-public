from __future__ import annotations

import smtplib
from email.message import EmailMessage

from ea_node_editor.nodes.execution_context import NodeResult
from ea_node_editor.runtime_contracts.data_tree import resolve_single_run_inputs


def split_recipients(value: str) -> list[str]:
    normalized = value.replace(";", ",")
    return [item.strip() for item in normalized.split(",") if item.strip()]


def execute_email_send(ctx) -> NodeResult:  # noqa: ANN001
    inputs = resolve_single_run_inputs(ctx.inputs, node_name="Email Send")
    smtp_host = str(ctx.properties.get("smtp_host", "localhost")).strip()
    smtp_port = int(ctx.properties.get("smtp_port", 25))
    username = str(ctx.properties.get("username", ""))
    password = str(ctx.properties.get("password", ""))
    sender = str(ctx.properties.get("sender", "")).strip()
    recipient = str(ctx.properties.get("to", ""))
    subject = str(inputs.get("subject", ctx.properties.get("subject", "")))
    body = str(inputs.get("body", ctx.properties.get("body", "")))
    recipients = split_recipients(recipient)
    if smtp_port <= 0:
        raise ValueError(
            f"Email Send SMTP port must be a positive integer. Received: {smtp_port}"
        )

    message = EmailMessage()
    message["From"] = sender
    message["To"] = ", ".join(recipients)
    message["Subject"] = subject
    message.set_content(body)

    try:
        with smtplib.SMTP(host=smtp_host, port=smtp_port, timeout=10) as smtp:
            if bool(ctx.properties.get("use_tls", False)):
                smtp.starttls()
            if username:
                smtp.login(username, password)
            smtp.send_message(message)
    except smtplib.SMTPException as exc:
        raise RuntimeError(
            f"Email Send SMTP error ({smtp_host}:{smtp_port}): {exc}"
        ) from exc
    except OSError as exc:
        raise RuntimeError(
            f"Email Send could not connect to SMTP server {smtp_host}:{smtp_port}: {exc}"
        ) from exc
    return NodeResult(outputs={"sent": True})
