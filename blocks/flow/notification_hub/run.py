"""Notification Hub — send notifications via Telegram, Slack, email, webhook, desktop, or log."""

import json
import os
import platform
import smtplib
import subprocess
import urllib.request
import urllib.error
from datetime import datetime, timezone
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

try:
    from backend.block_sdk.exceptions import (
        BlockConfigError, BlockInputError, BlockDataError,
        BlockDependencyError, BlockExecutionError,
    )
except ImportError:
    class BlockConfigError(ValueError):
        def __init__(self, field, message, **kw): super().__init__(message)
    class BlockInputError(ValueError):
        def __init__(self, message, **kw): super().__init__(message)
    class BlockDataError(ValueError):
        pass
    class BlockDependencyError(ImportError):
        def __init__(self, dep, message="", **kw): super().__init__(message or dep)
    class BlockExecutionError(RuntimeError):
        def __init__(self, message, **kw): super().__init__(message)


def _format_message(template, data, message_data=None, severity="info"):
    """Format a message template with data fields."""
    replacements = {
        "status": "completed",
        "severity": severity,
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    }
    if isinstance(data, dict):
        for key, value in data.items():
            if isinstance(value, (str, int, float, bool)):
                replacements[key] = str(value)
        replacements["status"] = data.get("status", "triggered")
    if isinstance(message_data, dict):
        for key, value in message_data.items():
            if isinstance(value, (str, int, float, bool)):
                replacements[key] = str(value)

    message = template
    for key, value in replacements.items():
        message = message.replace("{" + key + "}", str(value))
    return message


def _extract_metrics_summary(trigger_data, message_data=None):
    """Extract numeric metrics from trigger and message data."""
    metrics = {}
    for source in [trigger_data, message_data]:
        if isinstance(source, dict):
            for key, value in source.items():
                if isinstance(value, (int, float)):
                    metrics[key] = value
                elif isinstance(value, dict):
                    for sub_key, sub_value in value.items():
                        if isinstance(sub_value, (int, float)):
                            metrics[f"{key}.{sub_key}"] = sub_value
    return metrics


def _parse_headers(headers_text):
    """Parse custom headers from text (one per line: Key: Value)."""
    custom = {}
    if not headers_text:
        return custom
    for line in headers_text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" in line:
            key, value = line.split(":", 1)
            custom[key.strip()] = value.strip()
    return custom


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


def _send_webhook(url, payload, ctx, extra_headers=None, timeout=30):
    """Send a JSON payload to a webhook URL via POST."""
    json_data = json.dumps(payload, default=str, ensure_ascii=False).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Blueprint-NotificationHub/1.1",
    }
    if extra_headers:
        headers.update(extra_headers)
    req = urllib.request.Request(url, data=json_data, headers=headers, method="POST")

    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            status_code = response.status
            body = response.read().decode("utf-8", errors="replace")[:500]
            ctx.log_message(f"Webhook response: {status_code}")
            return {"delivered": True, "status_code": status_code, "response_body": body}
    except urllib.error.HTTPError as e:
        ctx.log_message(f"Webhook HTTP error: {e.code} {e.reason}")
        return {"delivered": False, "error": f"HTTP {e.code}: {e.reason}", "status_code": e.code}
    except Exception as e:
        ctx.log_message(f"Webhook error: {e}")
        return {"delivered": False, "error": str(e)}


def _send_desktop(title, message, ctx, timeout=10):
    """Send a desktop notification. Supports macOS (osascript) and Linux (notify-send)."""
    system = platform.system()

    if system == "Darwin":
        script = f'display notification "{message}" with title "{title}"'
        try:
            subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=timeout)
            ctx.log_message("Desktop notification sent via osascript (macOS)")
            return {"delivered": True, "method": "osascript"}
        except FileNotFoundError:
            return {"delivered": False, "error": "osascript not found"}
        except subprocess.TimeoutExpired:
            return {"delivered": False, "error": f"Desktop notification timed out after {timeout}s"}
        except Exception as e:
            return {"delivered": False, "error": str(e)}

    elif system == "Linux":
        try:
            subprocess.run(["notify-send", title, message], capture_output=True, text=True, timeout=timeout)
            ctx.log_message("Desktop notification sent via notify-send (Linux)")
            return {"delivered": True, "method": "notify-send"}
        except FileNotFoundError:
            return {"delivered": False, "error": "notify-send not found (install libnotify-bin)"}
        except subprocess.TimeoutExpired:
            return {"delivered": False, "error": f"Desktop notification timed out after {timeout}s"}
        except Exception as e:
            return {"delivered": False, "error": str(e)}

    else:
        return {"delivered": False, "error": f"Unsupported platform: {system}"}


def _send_log(message, severity, metrics, run_dir, ctx):
    """Write notification to a log file in the run directory."""
    log_entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "severity": severity,
        "message": message,
        "metrics": metrics,
    }

    log_path = os.path.join(run_dir, "notification_log.jsonl")
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(log_entry, default=str, ensure_ascii=False) + "\n")

    ctx.log_message(f"Notification logged to {log_path}")
    return {"delivered": True, "method": "log_file", "path": log_path}


def run(ctx):
    channel = ctx.config.get("channel", "telegram").lower().strip()
    api_token = ctx.config.get("api_token", "").strip()
    recipient = ctx.config.get("recipient", "").strip()
    template = ctx.config.get("template",
                              ctx.config.get("message_template", "Pipeline update: {status}"))
    severity = ctx.config.get("severity", "info").lower().strip()
    retry_count = int(ctx.config.get("retry_count", 0))
    include_data_summary = ctx.config.get("include_data_summary", False)
    include_metrics = ctx.config.get("include_metrics", True)
    min_severity = ctx.config.get("min_severity", "info").lower().strip()
    send_condition = ctx.config.get("send_condition", "always").lower().strip()
    timeout = int(ctx.config.get("timeout", 30))

    # Channel-specific config
    webhook_url = ctx.config.get("webhook_url", "").strip()
    webhook_headers = ctx.config.get("webhook_headers", "").strip()
    notification_title = ctx.config.get("notification_title", "").strip()
    smtp_host = ctx.config.get("smtp_host", "smtp.gmail.com").strip()
    smtp_port = int(ctx.config.get("smtp_port", 587))
    smtp_user = ctx.config.get("smtp_user", "").strip()
    smtp_pass = ctx.config.get("smtp_pass", "").strip()
    email_subject = ctx.config.get("email_subject", "Blueprint Pipeline Notification").strip()

    ctx.log_message(f"Notification Hub starting (channel={channel}, severity={severity})")
    ctx.report_progress(0, 4)

    valid_channels = {"telegram", "slack", "email", "webhook", "desktop", "log"}
    if channel not in valid_channels:
        raise BlockConfigError("channel", f"Unsupported channel '{channel}'. Supported: {', '.join(sorted(valid_channels))}")

    # ---- Step 1: Load trigger data ----
    ctx.report_progress(1, 4)
    raw_data = ctx.resolve_as_data("data")
    if not raw_data:
        raise BlockInputError("No trigger data provided. Connect a 'data' input.", recoverable=False)
    data = raw_data
    ctx.log_message("Trigger data loaded")

    # Load optional message data
    message_data = None
    try:
        msg = ctx.load_input("message_data")
        if msg:
            message_data = msg
            ctx.log_message("Additional message data loaded")
    except (ValueError, Exception):
        pass

    # ---- Step 2: Evaluate send condition ----
    ctx.report_progress(2, 4)
    if send_condition != "always" and isinstance(data, dict):
        status_val = str(data.get("status", "")).lower()
        gate_passed = data.get("gate_passed")
        delivered = data.get("delivered")
        has_error = data.get("error") is not None

        is_failure = (status_val in ("failed", "rejected", "error")
                      or gate_passed is False or delivered is False or has_error)
        is_success = not is_failure

        if send_condition == "on_failure" and is_success:
            ctx.log_message("send_condition=on_failure but status indicates success — skipping")
            ctx.save_output("status", {"skipped": True, "reason": "send_condition not met", "channel": channel})
            ctx.save_output("pass_through", data)
            ctx.log_metric("delivered", 0.0)
            ctx.report_progress(4, 4)
            return
        elif send_condition == "on_success" and is_failure:
            ctx.log_message("send_condition=on_success but status indicates failure — skipping")
            ctx.save_output("status", {"skipped": True, "reason": "send_condition not met", "channel": channel})
            ctx.save_output("pass_through", data)
            ctx.log_metric("delivered", 0.0)
            ctx.report_progress(4, 4)
            return

    # Check min_severity gate
    severity_levels = {"info": 0, "warning": 1, "error": 2, "critical": 3}
    if severity_levels.get(severity, 0) < severity_levels.get(min_severity, 0):
        ctx.log_message(f"Severity '{severity}' is below min_severity '{min_severity}' — skipping")
        ctx.save_output("status", {"skipped": True, "reason": f"severity below min_severity ({severity} < {min_severity})", "channel": channel})
        ctx.save_output("pass_through", data)
        ctx.log_metric("delivered", 0.0)
        ctx.report_progress(4, 4)
        return

    # ---- Step 3: Format and send ----
    ctx.report_progress(3, 4)
    message = _format_message(template, data, message_data, severity)
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

    # Extract metrics for webhook payload
    metrics_summary = {}
    if include_metrics:
        metrics_summary = _extract_metrics_summary(data, message_data)

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
            webhook = api_token if api_token.startswith("http") else ""
            if not webhook:
                raise BlockConfigError(
                    "api_token",
                    "For Slack, set 'API Token' to your Slack incoming webhook URL "
                    "(e.g., https://hooks.slack.com/services/...)"
                )
            delivery_result = _send_slack(webhook, message, ctx)

        elif channel == "email":
            delivery_result = _send_email(
                smtp_host, smtp_port, smtp_user, smtp_pass,
                smtp_user, recipient, email_subject, message, ctx
            )

        elif channel == "webhook":
            if not webhook_url:
                raise BlockConfigError("webhook_url", "webhook_url is required when channel is 'webhook'")
            custom_headers = _parse_headers(webhook_headers) if webhook_headers else None
            payload = {
                "message": message,
                "severity": severity,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "source": "blueprint_pipeline",
            }
            if include_metrics and metrics_summary:
                payload["metrics"] = metrics_summary
            delivery_result = _send_webhook(webhook_url, payload, ctx, extra_headers=custom_headers, timeout=timeout)

        elif channel == "desktop":
            title = notification_title if notification_title else f"Blueprint [{severity.upper()}]"
            delivery_result = _send_desktop(title, message, ctx, timeout=timeout)
            # Also log desktop notifications
            _send_log(message, severity, metrics_summary, ctx.run_dir, ctx)

        elif channel == "log":
            delivery_result = _send_log(message, severity, metrics_summary, ctx.run_dir, ctx)

        if delivery_result.get("delivered"):
            break
        elif attempt < total_attempts - 1:
            ctx.log_message(f"Delivery failed, will retry: {delivery_result.get('error', 'unknown')}")

    # ---- Step 4: Save outputs ----
    ctx.report_progress(4, 4)
    status_record = {
        "channel": channel,
        "severity": severity,
        "message": message,
        "delivered": delivery_result.get("delivered", False),
        "attempts": min(attempt + 1, total_attempts),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "details": delivery_result,
    }
    if include_metrics and metrics_summary:
        status_record["metrics_included"] = metrics_summary

    status_path = os.path.join(ctx.run_dir, "notification_hub_status.json")
    with open(status_path, "w", encoding="utf-8") as f:
        json.dump(status_record, f, indent=2, default=str, ensure_ascii=False)

    ctx.save_output("status", status_record)
    ctx.save_output("pass_through", data)
    ctx.save_artifact("notification_hub_status", status_path)
    ctx.log_metric("delivered", 1.0 if delivery_result.get("delivered") else 0.0)

    if delivery_result.get("delivered"):
        ctx.log_message(f"Notification delivered via {channel}")
    else:
        ctx.log_message(f"Delivery failed: {delivery_result.get('error', 'unknown')}")

    ctx.log_message("Notification Hub complete.")
