"""API Publisher — push pipeline results to an external REST API endpoint."""

import json
import os
import time
import base64
import urllib.request
import urllib.error

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


def _normalize_rows(data):
    """Ensure data is a list."""
    if data is None:
        return []
    if isinstance(data, dict):
        if "data" in data and isinstance(data["data"], list):
            return data["data"]
        return [data]
    if isinstance(data, list):
        return data
    return [{"value": data}]


def run(ctx):
    url = ctx.config.get("url", "").strip()
    method = ctx.config.get("method", "POST").upper()
    headers_str = ctx.config.get("headers", "{}")
    auth_type = ctx.config.get("auth_type", "none")
    auth_token = ctx.config.get("auth_token", "")
    auth_username = ctx.config.get("auth_username", "")
    api_key_header = ctx.config.get("api_key_header", "X-API-Key")
    batch_size = int(ctx.config.get("batch_size", 100))
    retry_count = int(ctx.config.get("retry_count", 3))
    timeout = int(ctx.config.get("timeout", 30))
    payload_template = ctx.config.get("payload_template", "").strip()
    content_type = ctx.config.get("content_type", "application/json")
    rate_limit = float(ctx.config.get("rate_limit", 0))
    on_error = ctx.config.get("on_error", "skip").lower().strip()

    if not url:
        raise BlockInputError(
            "Target URL is required. Set the 'Target URL' config.",
            recoverable=True,
        )

    ctx.log_message(f"API Publisher starting ({method} {url})")
    ctx.report_progress(0, 4)

    # ---- Step 1: Load data ----
    ctx.report_progress(1, 4)
    raw_data = ctx.resolve_as_data("data")
    if not raw_data:
        raise BlockInputError(
            "No input data provided. Connect a 'data' input.",
            recoverable=False,
        )

    rows = _normalize_rows(raw_data)
    ctx.log_message(f"Loaded {len(rows)} records to publish")

    # Load optional auth config
    try:
        auth_config = ctx.resolve_as_dict("config")
        if isinstance(auth_config, dict):
            auth_type = auth_config.get("auth_type", auth_type)
            auth_token = auth_config.get("auth_token", auth_token) or auth_config.get("token", auth_token)
            url = auth_config.get("url", url) or url
    except Exception:
        pass

    # ---- Step 2: Build headers ----
    ctx.report_progress(2, 4)

    try:
        custom_headers = json.loads(headers_str) if headers_str else {}
    except json.JSONDecodeError:
        ctx.log_message("WARNING: Invalid headers JSON, using empty headers")
        custom_headers = {}

    request_headers = {"Content-Type": content_type}
    request_headers.update(custom_headers)

    # Apply auth
    if auth_type == "bearer" and auth_token:
        request_headers["Authorization"] = f"Bearer {auth_token}"
    elif auth_type == "basic" and auth_username:
        creds = base64.b64encode(f"{auth_username}:{auth_token}".encode()).decode()
        request_headers["Authorization"] = f"Basic {creds}"
    elif auth_type == "api_key" and auth_token:
        request_headers[api_key_header] = auth_token

    # ---- Step 3: Send requests ----
    ctx.report_progress(3, 4)

    # Split into batches
    if batch_size <= 0 or batch_size >= len(rows):
        batches = [rows]
    else:
        batches = [rows[i:i + batch_size] for i in range(0, len(rows), batch_size)]

    total_sent = 0
    total_failed = 0
    responses = []
    effective_retries = max(retry_count, 1)

    for batch_idx, batch in enumerate(batches):
        # Build payload
        if payload_template:
            try:
                payload_str = payload_template.replace("{data}", json.dumps(batch, default=str))
                payload = json.loads(payload_str)
            except (json.JSONDecodeError, ValueError):
                payload = batch
        else:
            payload = batch

        body = json.dumps(payload, default=str, ensure_ascii=False).encode("utf-8")

        # Send with retry
        last_error = None
        for attempt in range(effective_retries):
            try:
                req = urllib.request.Request(url, data=body, headers=request_headers, method=method)
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    resp.read()
                    status_code = resp.status

                total_sent += len(batch)
                responses.append({"batch": batch_idx, "status": status_code, "records": len(batch)})
                ctx.log_message(f"Batch {batch_idx + 1}/{len(batches)}: {status_code} ({len(batch)} records)")
                last_error = None
                break

            except urllib.error.HTTPError as e:
                last_error = f"HTTP {e.code}: {e.reason}"
                if e.code < 500 and e.code != 429:
                    break
                if attempt < effective_retries - 1:
                    wait = 2 ** attempt
                    ctx.log_message(f"Retry {attempt + 1}/{effective_retries} after {wait}s ({last_error})")
                    time.sleep(wait)

            except Exception as e:
                last_error = str(e)
                if attempt < effective_retries - 1:
                    wait = 2 ** attempt
                    ctx.log_message(f"Retry {attempt + 1}/{effective_retries} after {wait}s ({last_error})")
                    time.sleep(wait)

        if last_error:
            total_failed += len(batch)
            responses.append({"batch": batch_idx, "error": last_error, "records": len(batch)})
            ctx.log_message(f"Batch {batch_idx + 1} FAILED: {last_error}")
            if on_error == "fail":
                raise BlockExecutionError(
                    f"Batch {batch_idx + 1} failed: {last_error}",
                    recoverable=False,
                )

        # Rate limiting between batches
        if rate_limit > 0 and batch_idx < len(batches) - 1:
            delay = 1.0 / rate_limit
            time.sleep(delay)

    # ---- Step 4: Finalize ----
    ctx.report_progress(4, 4)

    status_msg = f"Published {total_sent}/{len(rows)} records"
    if total_failed > 0:
        status_msg += f" ({total_failed} failed)"
    ctx.log_message(status_msg)

    ctx.save_output("status", status_msg)
    ctx.save_output("summary", {
        "records_sent": total_sent,
        "records_failed": total_failed,
        "batches": len(batches),
        "url": url,
        "method": method,
    })
    ctx.save_output("results", responses)
    ctx.log_metric("records_sent", float(total_sent))
    ctx.log_metric("records_failed", float(total_failed))

    if total_failed > 0 and total_sent == 0:
        raise BlockExecutionError(
            f"All requests failed. Last error: {last_error}",
            recoverable=False,
        )

    ctx.log_message("API Publisher complete.")
