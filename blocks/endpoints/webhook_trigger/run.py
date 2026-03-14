"""Webhook Trigger — fire a webhook with pipeline results."""

import json
import os
import time
from datetime import datetime, timezone


def run(ctx):
    webhook_url = ctx.config.get("webhook_url", "").strip()
    method = ctx.config.get("method", "POST").upper()
    headers_str = ctx.config.get("headers", "{}")
    payload_template = ctx.config.get("payload_template", "").strip()
    include_metrics = ctx.config.get("include_metrics", True)
    retry_on_failure = ctx.config.get("retry_on_failure", True)
    max_retries = int(ctx.config.get("max_retries", 3))
    timeout = int(ctx.config.get("timeout", 30))
    secret_header = ctx.config.get("secret_header", "").strip()
    secret_value = ctx.config.get("secret_value", "").strip()
    on_failure_url = ctx.config.get("on_failure_url", "").strip()
    include_run_id = ctx.config.get("include_run_id", False)

    if not webhook_url:
        raise ValueError("Webhook URL is required. Set the 'Webhook URL' config.")

    ctx.log_message(f"Webhook Trigger starting ({method} {webhook_url})")
    ctx.report_progress(0, 3)

    # ---- Step 1: Build payload ----
    ctx.report_progress(1, 3)
    raw_data = ctx.resolve_as_data("data")
    if not raw_data:
        raise ValueError("No input data provided. Connect a 'data' input.")

    data = raw_data

    metrics_data = None
    if include_metrics:
        try:
            metrics_data = ctx.resolve_as_dict("metrics")
        except Exception:
            pass

    # Build payload
    if payload_template:
        try:
            data_json = json.dumps(data, default=str)
            metrics_json = json.dumps(metrics_data, default=str) if metrics_data else "{}"
            filled = payload_template.replace("{data}", data_json).replace("{metrics}", metrics_json)
            payload = json.loads(filled)
        except (json.JSONDecodeError, ValueError) as e:
            ctx.log_message(f"WARNING: Invalid payload template ({e}), sending data directly")
            payload = data
    else:
        payload = {
            "data": data,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source": "blueprint",
        }
        if metrics_data:
            payload["metrics"] = metrics_data
        if include_run_id:
            payload["run_id"] = getattr(ctx, "run_id", None) or os.path.basename(ctx.run_dir)

    # ---- Step 2: Build request ----
    ctx.report_progress(2, 3)
    import urllib.request
    import urllib.error

    try:
        custom_headers = json.loads(headers_str) if headers_str else {}
    except json.JSONDecodeError:
        custom_headers = {}

    request_headers = {"Content-Type": "application/json"}
    request_headers.update(custom_headers)

    if secret_header and secret_value:
        request_headers[secret_header] = secret_value

    body = json.dumps(payload, default=str, ensure_ascii=False).encode("utf-8")

    # ---- Step 3: Send webhook ----
    attempts = max_retries if retry_on_failure else 1
    last_error = None
    status_code = None
    response_body = ""

    for attempt in range(max(attempts, 1)):
        try:
            if method == "GET":
                # For GET, append data as query params (limited)
                req = urllib.request.Request(webhook_url, headers=request_headers, method="GET")
            else:
                req = urllib.request.Request(webhook_url, data=body, headers=request_headers, method=method)

            with urllib.request.urlopen(req, timeout=timeout) as resp:
                status_code = resp.status
                response_body = resp.read().decode("utf-8", errors="replace")[:500]

            ctx.log_message(f"Webhook fired successfully: HTTP {status_code}")
            last_error = None
            break

        except urllib.error.HTTPError as e:
            last_error = f"HTTP {e.code}: {e.reason}"
            status_code = e.code
            if e.code < 500 and e.code != 429:
                break  # Client error, don't retry
            if attempt < attempts - 1:
                wait = 2 ** attempt
                ctx.log_message(f"Retry {attempt + 1}/{attempts} after {wait}s ({last_error})")
                time.sleep(wait)

        except Exception as e:
            last_error = str(e)
            if attempt < attempts - 1:
                wait = 2 ** attempt
                ctx.log_message(f"Retry {attempt + 1}/{attempts} after {wait}s ({last_error})")
                time.sleep(wait)

    ctx.report_progress(3, 3)

    if last_error:
        status_msg = f"FAILED: {last_error}"
        ctx.log_message(f"Webhook failed: {last_error}")

        # Fire failure webhook if configured
        if on_failure_url:
            try:
                fail_payload = json.dumps({
                    "status": "failed",
                    "error": last_error,
                    "original_url": webhook_url,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "source": "blueprint",
                }, default=str).encode("utf-8")
                fail_req = urllib.request.Request(on_failure_url, data=fail_payload, headers={"Content-Type": "application/json"}, method="POST")
                urllib.request.urlopen(fail_req, timeout=10)
                ctx.log_message(f"Failure notification sent to {on_failure_url}")
            except Exception as e:
                ctx.log_message(f"WARNING: Could not send failure notification: {e}")

        ctx.save_output("status", status_msg)
        ctx.save_output("summary", {"status": "failed", "error": last_error, "status_code": status_code})
        ctx.log_metric("webhook_success", 0.0)
        raise RuntimeError(f"Webhook failed after {attempts} attempts: {last_error}")
    else:
        status_msg = f"OK ({status_code})"
        ctx.save_output("status", status_msg)
        ctx.save_output("summary", {
            "status": "success",
            "status_code": status_code,
            "url": webhook_url,
            "method": method,
            "payload_size_bytes": len(body),
        })
        ctx.save_output("response", response_body)
        ctx.log_metric("webhook_success", 1.0)
        ctx.log_metric("response_code", float(status_code or 0))

    ctx.log_message("Webhook Trigger complete.")
