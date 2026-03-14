"""Notification Hub — send notifications via Telegram, Slack, or email using user API keys."""

import json
import os
import smtplib
import urllib.request
import urllib.error
from datetime import datetime, timezone
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart


def _resolve_input(raw):
    """Resolve an input value that might be a file path or directory to a Python object."""
    if raw is None:
        return None
    if isinstance(raw, str):
        if os.path.isfile(raw):
            with open(raw, "r", encoding="utf-8") as f:
                try:
                    return json.load(f)
                except (json.JSONDecodeError, ValueError):
                    return raw
        if os.path.isdir(raw):
            data_file = os.path.join(raw, "data.json")
            if os.path.isfile(data_file):
                with open(data_file, "r", encoding="utf-8") as f:
                    return json.load(f)
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return raw
    return raw


def _format_message(template, data):
    """Format a message template with data fields."""
    replacements = {
        "status": "completed",
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    }
    if isinstance(data, dict):
        for key, value in data.items():
            if isinstance(value, (str, int, float, bool)):
                replacements[key] = str(value)
        replacements["status"] = data.get("status", "triggered")

    message = template
    for key, value in replacements.items():
        message = message.replace("{" + key + "}", str(value))
    return message


def _send_telegram(api_token, chat_id, message, ctx):
    """Send a message via Telegram Bot API."""
    if not api_token:
        return {"delivered": False, "error": "Telegram API token is required"}
    if not chat_id:
        return {"delivered": False, "error": "Telegram chat_id / recipient is required"}

    url = f"https://api.telegram.org/bot{api_token}/sendMessage"
    payload = json.dumps({
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "Markdown",
    }).encode("utf-8")

    req = urllib.request.Request(
        url, data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            body = json.loads(response.read().decode("utf-8"))
            if body.get("ok"):
                ctx.log_message("Telegram message sent successfully")
                return {"delivered": True, "message_id": body.get("result", {}).get("message_id")}
            else:
                return {"delivered": False, "error": body.get("description", "Unknown Telegram error")}
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")[:500]
        return {"delivered": False, "error": f"HTTP {e.code}: {error_body}"}
    except Exception as e:
        return {"delivered": False, "error": str(e)}


def _send_slack(webhook_url, message, ctx):
    """Send a message to Slack via incoming webhook."""
    if not webhook_url:
        return {"delivered": False, "error": "Slack webhook URL is required"}

    payload = json.dumps({"text": message}).encode("utf-8")
    req = urllib.request.Request(
        webhook_url, data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            body = response.read().decode("utf-8", errors="replace")
            if body == "ok" or response.status == 200:
                ctx.log_message("Slack message sent successfully")
                return {"delivered": True}
            else:
                return {"delivered": False, "error": f"Slack returned: {body[:200]}"}
    except urllib.error.HTTPError as e:
        return {"delivered": False, "error": f"HTTP {e.code}: {e.reason}"}
    except Exception as e:
        return {"delivered": False, "error": str(e)}


def _send_email(smtp_host, smtp_port, smtp_user, smtp_pass, from_addr, to_addr, subject, body_text, ctx):
    """Send an email via SMTP."""
    if not to_addr:
        return {"delivered": False, "error": "Recipient email address is required"}

    msg = MIMEMultipart()
    msg["From"] = from_addr or smtp_user or "blueprint@pipeline.local"
    msg["To"] = to_addr
    msg["Subject"] = subject or "Blueprint Pipeline Notification"
    msg.attach(MIMEText(body_text, "plain", "utf-8"))

    try:
        if smtp_port == 465:
            server = smtplib.SMTP_SSL(smtp_host or "smtp.gmail.com", smtp_port, timeout=30)
        else:
            server = smtplib.SMTP(smtp_host or "smtp.gmail.com", smtp_port or 587, timeout=30)
            server.starttls()

        if smtp_user and smtp_pass:
            server.login(smtp_user, smtp_pass)

        server.sendmail(msg["From"], [to_addr], msg.as_string())
        server.quit()
        ctx.log_message(f"Email sent to {to_addr}")
        return {"delivered": True, "to": to_addr}
    except Exception as e:
        return {"delivered": False, "error": str(e)}


def run(ctx):
    channel = ctx.config.get("channel", "telegram").lower().strip()
    api_token = ctx.config.get("api_token", "").strip()
    recipient = ctx.config.get("recipient", "").strip()
    template = ctx.config.get("template", "Pipeline update: {status}")
    severity = ctx.config.get("severity", "info").lower().strip()
    retry_count = int(ctx.config.get("retry_count", 0))
    include_data_summary = ctx.config.get("include_data_summary", False)
    min_severity = ctx.config.get("min_severity", "info").lower().strip()

    # Email-specific config
    smtp_host = ctx.config.get("smtp_host", "smtp.gmail.com").strip()
    smtp_port = int(ctx.config.get("smtp_port", 587))
    smtp_user = ctx.config.get("smtp_user", "").strip()
    smtp_pass = ctx.config.get("smtp_pass", "").strip()
    email_subject = ctx.config.get("email_subject", "Blueprint Pipeline Notification").strip()

    ctx.log_message(f"Notification Hub starting (channel={channel}, severity={severity})")
    ctx.report_progress(0, 3)

    valid_channels = {"telegram", "slack", "email"}
    if channel not in valid_channels:
        raise ValueError(f"Unsupported channel '{channel}'. Supported: {', '.join(sorted(valid_channels))}")

    # ---- Step 1: Load trigger data ----
    ctx.report_progress(1, 3)
    raw_data = ctx.load_input("data")
    if raw_data is None:
        raise ValueError("No trigger data provided. Connect a 'data' input.")
    data = _resolve_input(raw_data)
    ctx.log_message("Trigger data loaded")

    # Check min_severity gate
    severity_levels = {"info": 0, "warning": 1, "error": 2, "critical": 3}
    if severity_levels.get(severity, 0) < severity_levels.get(min_severity, 0):
        ctx.log_message(f"Severity '{severity}' is below min_severity '{min_severity}' — skipping notification")
        # Branch: severity below threshold — skip notification
        ctx.save_output("status", {"skipped": True, "reason": f"severity below min_severity ({severity} < {min_severity})", "channel": channel})
        # Branch: severity below threshold — skip notification
        ctx.save_output("pass_through", data)
        ctx.log_metric("delivered", 0.0)
        ctx.report_progress(3, 3)
        return

    # ---- Step 2: Format and send ----
    ctx.report_progress(2, 3)
    message = _format_message(template, data)
    # Prepend severity tag if not info
    if severity != "info":
        message = f"[{severity.upper()}] {message}"
    # Append data summary if requested
    if include_data_summary and isinstance(data, dict):
        summary_lines = []
        for k, v in list(data.items())[:10]:
            summary_lines.append(f"  {k}: {str(v)[:100]}")
        if summary_lines:
            message += "\n\nData summary:\n" + "\n".join(summary_lines)
    elif include_data_summary and isinstance(data, list):
        message += f"\n\nData summary: {len(data)} items"
        if data and isinstance(data[0], dict):
            message += f" (columns: {', '.join(list(data[0].keys())[:10])})"
    ctx.log_message(f"Message: {message[:200]}")

    delivery_result = {}
    total_attempts = retry_count + 1

    for attempt in range(total_attempts):
        if attempt > 0:
            import time
            ctx.log_message(f"Retry {attempt}/{retry_count}...")
            time.sleep(min(2 ** attempt, 10))

        if channel == "telegram":
            delivery_result = _send_telegram(api_token, recipient, message, ctx)

        elif channel == "slack":
            # For Slack, api_token is used as the webhook URL
            webhook_url = api_token if api_token.startswith("http") else ""
            if not webhook_url:
                raise ValueError(
                    "For Slack, set 'API Token' to your Slack incoming webhook URL "
                    "(e.g., https://hooks.slack.com/services/...)"
                )
            delivery_result = _send_slack(webhook_url, message, ctx)

        elif channel == "email":
            delivery_result = _send_email(
                smtp_host, smtp_port, smtp_user, smtp_pass,
                smtp_user, recipient, email_subject, message, ctx
            )

        if delivery_result.get("delivered"):
            break
        elif attempt < total_attempts - 1:
            ctx.log_message(f"Delivery failed, will retry: {delivery_result.get('error', 'unknown')}")

    # ---- Step 3: Save outputs ----
    ctx.report_progress(3, 3)
    status_record = {
        "channel": channel,
        "severity": severity,
        "message": message,
        "delivered": delivery_result.get("delivered", False),
        "attempts": min(attempt + 1, total_attempts),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "details": delivery_result,
    }

    status_path = os.path.join(ctx.run_dir, "notification_hub_status.json")
    with open(status_path, "w", encoding="utf-8") as f:
        json.dump(status_record, f, indent=2, default=str, ensure_ascii=False)

    # Branch: notification sent
    ctx.save_output("status", status_record)
    # Branch: notification sent
    ctx.save_output("pass_through", data)
    ctx.save_artifact("notification_hub_status", status_path)
    ctx.log_metric("delivered", 1.0 if delivery_result.get("delivered") else 0.0)

    if delivery_result.get("delivered"):
        ctx.log_message(f"Notification delivered via {channel}")
    else:
        ctx.log_message(f"Delivery failed: {delivery_result.get('error', 'unknown')}")

    ctx.log_message("Notification Hub complete.")
