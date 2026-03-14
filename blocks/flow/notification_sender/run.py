"""Notification Sender — send notifications via webhook, desktop, or log channels."""

import json
import os
import platform
import socket
import subprocess
import urllib.request
import urllib.error
from datetime import datetime, timezone

from backend.block_sdk.exceptions import BlockTimeoutError


def _format_message(template, trigger_data, message_data, severity):
    """Format a notification message by substituting placeholders."""
    replacements = {
        "status": "completed",
        "severity": severity,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    if isinstance(trigger_data, dict):
        for key, value in trigger_data.items():
            if isinstance(value, (str, int, float, bool)):
                replacements[key] = str(value)
        replacements["status"] = trigger_data.get("status", "triggered")

    if isinstance(message_data, dict):
        for key, value in message_data.items():
            if isinstance(value, (str, int, float, bool)):
                replacements[key] = str(value)

    message = template
    for key, value in replacements.items():
        message = message.replace("{" + key + "}", str(value))

    return message


def _extract_metrics_summary(trigger_data, message_data):
    """Extract numeric metrics from trigger and message data for inclusion."""
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


def _send_webhook(url, payload, ctx, extra_headers=None, timeout=30):
    """Send a JSON payload to a webhook URL via POST."""
    json_data = json.dumps(payload, default=str, ensure_ascii=False).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Blueprint-NotificationSender/1.0",
    }
    if extra_headers:
        headers.update(extra_headers)
    req = urllib.request.Request(
        url,
        data=json_data,
        headers=headers,
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            status_code = response.status
            body = response.read().decode("utf-8", errors="replace")[:500]
            ctx.log_message(f"Webhook response: {status_code}")
            return {"delivered": True, "status_code": status_code, "response_body": body}
    except urllib.error.HTTPError as e:
        ctx.log_message(f"Webhook HTTP error: {e.code} {e.reason}")
        return {"delivered": False, "error": f"HTTP {e.code}: {e.reason}", "status_code": e.code}
    except urllib.error.URLError as e:
        if isinstance(e.reason, (socket.timeout, TimeoutError)):
            raise BlockTimeoutError(timeout, f"Webhook request timed out after {timeout}s")
        ctx.log_message(f"Webhook URL error: {e.reason}")
        return {"delivered": False, "error": f"URL error: {e.reason}"}
    except BlockTimeoutError:
        raise
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
            raise BlockTimeoutError(timeout, f"Desktop notification timed out after {timeout}s")
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
            raise BlockTimeoutError(timeout, f"Desktop notification timed out after {timeout}s")
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
    channel = ctx.config.get("channel", "log").lower().strip()
    webhook_url = ctx.config.get("webhook_url", "").strip()
    message_template = ctx.config.get("message_template", "Pipeline notification: {status}")
    include_metrics = ctx.config.get("include_metrics", True)
    severity = ctx.config.get("severity", "info").lower().strip()
    webhook_headers = ctx.config.get("webhook_headers", "").strip()
    notification_title = ctx.config.get("notification_title", "").strip()
    send_condition = ctx.config.get("send_condition", "always").lower().strip()
    timeout = int(ctx.config.get("timeout", 30))

    ctx.log_message(f"Notification Sender starting (channel={channel}, severity={severity})")
    ctx.report_progress(0, 4)

    valid_channels = {"webhook", "desktop", "log"}
    if channel not in valid_channels:
        raise ValueError(f"Unsupported channel '{channel}'. Supported: {', '.join(sorted(valid_channels))}")

    # ---- Step 1: Load trigger data ----
    ctx.report_progress(1, 4)
    raw_trigger = ctx.resolve_as_dict("trigger")
    if not raw_trigger:
        raise ValueError("No trigger data provided. Connect a 'trigger' input to this block.")
    trigger_data = raw_trigger
    ctx.log_message("Trigger data loaded")

    # Evaluate send_condition: skip sending if condition not met
    if send_condition != "always" and isinstance(trigger_data, dict):
        status_val = str(trigger_data.get("status", "")).lower()
        gate_passed = trigger_data.get("gate_passed")
        delivered = trigger_data.get("delivered")
        has_error = trigger_data.get("error") is not None

        is_failure = (status_val in ("failed", "rejected", "error")
                      or gate_passed is False or delivered is False or has_error)
        is_success = not is_failure

        if send_condition == "on_failure" and is_success:
            ctx.log_message("send_condition=on_failure but status indicates success — skipping notification")
            ctx.save_output("status", {"skipped": True, "reason": "send_condition not met", "channel": channel})
            ctx.save_output("pass_through", trigger_data)
            ctx.log_metric("notification_delivered", 0.0)
            ctx.report_progress(4, 4)
            return
        elif send_condition == "on_success" and is_failure:
            ctx.log_message("send_condition=on_success but status indicates failure — skipping notification")
            ctx.save_output("status", {"skipped": True, "reason": "send_condition not met", "channel": channel})
            ctx.save_output("pass_through", trigger_data)
            ctx.log_metric("notification_delivered", 0.0)
            ctx.report_progress(4, 4)
            return

    # ---- Step 2: Load optional message data ----
    ctx.report_progress(2, 4)
    message_data = None
    if ctx.inputs.get("message_data"):
        raw_msg = ctx.resolve_as_dict("message_data")
        message_data = raw_msg
        ctx.log_message("Additional message data loaded")

    # ---- Step 3: Build and send notification ----
    ctx.report_progress(3, 4)
    message = _format_message(message_template, trigger_data, message_data, severity)
    ctx.log_message(f"Notification message: {message[:200]}")

    metrics_summary = {}
    if include_metrics:
        metrics_summary = _extract_metrics_summary(trigger_data, message_data)
        if metrics_summary:
            ctx.log_message(f"Including {len(metrics_summary)} metrics in notification")

    delivery_result = {}
    # Parse custom webhook headers
    custom_headers = _parse_headers(webhook_headers) if webhook_headers else None

    if channel == "webhook":
        if not webhook_url:
            raise ValueError("webhook_url is required when channel is 'webhook'")
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
        _send_log(message, severity, metrics_summary, ctx.run_dir, ctx)

    elif channel == "log":
        delivery_result = _send_log(message, severity, metrics_summary, ctx.run_dir, ctx)

    # ---- Step 4: Save outputs ----
    ctx.report_progress(4, 4)
    status_record = {
        "channel": channel,
        "severity": severity,
        "message": message,
        "delivered": delivery_result.get("delivered", False),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "details": delivery_result,
    }
    if include_metrics and metrics_summary:
        status_record["metrics_included"] = metrics_summary

    status_path = os.path.join(ctx.run_dir, "notification_status.json")
    with open(status_path, "w", encoding="utf-8") as f:
        json.dump(status_record, f, indent=2, default=str, ensure_ascii=False)

    ctx.save_output("status", status_record)
    ctx.save_output("pass_through", trigger_data)
    ctx.save_artifact("notification_status", status_path)
    ctx.log_metric("notification_delivered", 1.0 if delivery_result.get("delivered") else 0.0)

    if delivery_result.get("delivered"):
        ctx.log_message(f"Notification delivered via {channel}")
    else:
        ctx.log_message(f"Notification delivery failed: {delivery_result.get('error', 'unknown')}")

    ctx.log_message("Notification Sender complete.")
