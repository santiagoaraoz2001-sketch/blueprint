"""API Data Fetcher — fetch data from a REST API endpoint with auth, pagination, retry, and rate limiting."""

import base64
import json
import os
import time
import urllib.request
import urllib.error


def _resolve_response_path(data, path):
    """Traverse nested dict using dot-notation path (e.g. 'data.items')."""
    if not path:
        return data
    keys = path.split(".")
    current = data
    for key in keys:
        if isinstance(current, dict) and key in current:
            current = current[key]
        elif isinstance(current, list):
            try:
                current = current[int(key)]
            except (ValueError, IndexError):
                return data
        else:
            return data
    return current


def _build_auth_header(auth_type, auth_token, api_key_header="X-API-Key"):
    """Build Authorization header based on auth type."""
    if auth_type == "bearer" and auth_token:
        return {"Authorization": f"Bearer {auth_token}"}
    elif auth_type == "basic" and auth_token:
        # Expect token as "username:password"
        encoded = base64.b64encode(auth_token.encode("utf-8")).decode("utf-8")
        return {"Authorization": f"Basic {encoded}"}
    elif auth_type == "api_key" and auth_token:
        header_name = api_key_header.strip() if api_key_header.strip() else "X-API-Key"
        return {header_name: auth_token}
    return {}


def _parse_xml_response(raw):
    """Parse XML response into a list of dicts."""
    import xml.etree.ElementTree as ET
    try:
        root = ET.fromstring(raw)
        rows = []
        # Try to find repeated child elements
        children = list(root)
        if children:
            for child in children:
                row = {}
                for elem in child:
                    row[elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag] = elem.text or ""
                if row:
                    rows.append(row)
        if not rows:
            # Flat XML: extract all leaf elements
            row = {}
            for elem in root.iter():
                if elem.text and elem.text.strip():
                    tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
                    row[tag] = elem.text.strip()
            if row:
                rows = [row]
        return rows
    except ET.ParseError:
        return None


def _parse_csv_response(raw):
    """Parse CSV response into a list of dicts."""
    import csv
    import io
    try:
        reader = csv.DictReader(io.StringIO(raw))
        return list(reader)
    except Exception:
        return None


def run(ctx):
    url = ctx.config.get("url", "")
    method = ctx.config.get("method", "GET").upper()
    headers_str = ctx.config.get("headers", "{}")
    body = ctx.config.get("body", "")
    auth_type = ctx.config.get("auth_type", "none")
    auth_token = ctx.config.get("auth_token", "")
    response_path = ctx.config.get("response_path", "")
    pagination = ctx.config.get("pagination", False)
    pagination_key = ctx.config.get("pagination_key", "")
    max_pages = int(ctx.config.get("max_pages", 10))
    timeout = int(ctx.config.get("timeout", 30))
    retry_count = int(ctx.config.get("retry_count", 3))
    rate_limit_ms = int(ctx.config.get("rate_limit_ms", 0))
    response_format = ctx.config.get("response_format", "auto")
    api_key_header = ctx.config.get("api_key_header", "X-API-Key")

    # Normalize booleans
    if isinstance(pagination, str):
        pagination = pagination.lower() in ("true", "1", "yes")

    if not url:
        raise ValueError("url is required — provide an API endpoint URL")

    # Merge with incoming config input if connected
    try:
        config_input = ctx.load_input("config")
        if config_input:
            config_path = config_input
            if isinstance(config_path, str) and os.path.isfile(config_path):
                with open(config_path, "r") as f:
                    extra_config = json.load(f)
            elif isinstance(config_path, dict):
                extra_config = config_path
            else:
                extra_config = {}

            if isinstance(extra_config, dict):
                # Merge extra headers
                if "headers" in extra_config:
                    try:
                        base_headers = json.loads(headers_str) if headers_str.strip() else {}
                        base_headers.update(extra_config["headers"])
                        headers_str = json.dumps(base_headers)
                    except json.JSONDecodeError:
                        pass
                # Override URL if provided
                if "url" in extra_config and extra_config["url"]:
                    url = extra_config["url"]
                # Override body if provided
                if "body" in extra_config:
                    body = json.dumps(extra_config["body"]) if isinstance(extra_config["body"], dict) else str(extra_config["body"])
                ctx.log_message("Merged incoming config with request settings")
    except (ValueError, KeyError):
        pass  # No config input connected

    ctx.log_message(f"Fetching data from: {url}")
    ctx.log_message(f"Method: {method}, Auth: {auth_type}, Timeout: {timeout}s")

    # Parse custom headers
    try:
        custom_headers = json.loads(headers_str) if headers_str.strip() else {}
    except json.JSONDecodeError:
        custom_headers = {}
        ctx.log_message("WARNING: Could not parse headers JSON, using empty headers")

    # Build auth headers
    auth_headers = _build_auth_header(auth_type, auth_token, api_key_header)

    all_rows = []
    current_url = url
    effective_max_pages = max_pages if pagination else 1

    for page in range(effective_max_pages):
        ctx.log_message(f"Fetching page {page + 1}/{effective_max_pages}: {current_url}")

        req_headers = {"Accept": "application/json", "User-Agent": "Blueprint/1.0"}
        req_headers.update(custom_headers)
        req_headers.update(auth_headers)

        data_bytes = body.encode("utf-8") if body and method in ("POST", "PUT", "PATCH") else None
        if data_bytes:
            req_headers.setdefault("Content-Type", "application/json")

        req = urllib.request.Request(current_url, data=data_bytes, headers=req_headers, method=method)

        # Retry loop
        raw = None
        for attempt in range(max(retry_count, 1)):
            try:
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    raw = resp.read().decode("utf-8")
                break  # Success
            except urllib.error.HTTPError as e:
                if e.code >= 500 and attempt < retry_count - 1:
                    wait = 2 ** attempt
                    ctx.log_message(f"HTTP {e.code} — retrying in {wait}s (attempt {attempt + 1}/{retry_count})")
                    time.sleep(wait)
                    continue
                ctx.log_message(f"HTTP Error {e.code}: {e.reason}")
                break
            except Exception as e:
                if attempt < retry_count - 1:
                    wait = 2 ** attempt
                    ctx.log_message(f"Request failed: {e} — retrying in {wait}s (attempt {attempt + 1}/{retry_count})")
                    time.sleep(wait)
                    continue
                ctx.log_message(f"Request failed after {retry_count} attempts: {e}")
                break

        if raw is None:
            break

        # Parse response based on response_format
        content_type = ""
        fmt = response_format
        if fmt == "auto":
            # Auto-detect from content — try JSON first, then XML, then CSV
            try:
                parsed = json.loads(raw)
                fmt = "json"
            except (json.JSONDecodeError, ValueError):
                if raw.strip().startswith("<"):
                    xml_result = _parse_xml_response(raw)
                    if xml_result is not None:
                        parsed = xml_result
                        fmt = "xml"
                        ctx.log_message("Auto-detected XML response")
                    else:
                        parsed = [{"text": raw}]
                elif "," in raw.split("\n")[0] and "\n" in raw:
                    csv_result = _parse_csv_response(raw)
                    if csv_result:
                        parsed = csv_result
                        fmt = "csv"
                        ctx.log_message("Auto-detected CSV response")
                    else:
                        parsed = [{"text": raw}]
                else:
                    parsed = [{"text": raw}]
        elif fmt == "json":
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                parsed = [{"text": raw}]
                ctx.log_message("WARNING: Expected JSON but failed to parse")
        elif fmt == "xml":
            xml_result = _parse_xml_response(raw)
            parsed = xml_result if xml_result is not None else [{"text": raw}]
            if xml_result is None:
                ctx.log_message("WARNING: Expected XML but failed to parse")
        elif fmt == "csv":
            csv_result = _parse_csv_response(raw)
            parsed = csv_result if csv_result else [{"text": raw}]
            if not csv_result:
                ctx.log_message("WARNING: Expected CSV but failed to parse")
        else:
            # raw_text
            parsed = [{"text": raw}]

        # Apply response_path to extract nested data
        if response_path and isinstance(parsed, dict):
            extracted = _resolve_response_path(parsed, response_path)
            if extracted is not parsed:
                ctx.log_message(f"Extracted data from path: {response_path}")
                parsed_for_rows = extracted
            else:
                parsed_for_rows = parsed
        else:
            parsed_for_rows = parsed

        # Normalize to list of dicts
        if isinstance(parsed_for_rows, list):
            rows = parsed_for_rows
        elif isinstance(parsed_for_rows, dict):
            # Try to find an array in common response patterns
            for key in ("data", "results", "items", "rows", "records", "entries"):
                if key in parsed_for_rows and isinstance(parsed_for_rows[key], list):
                    rows = parsed_for_rows[key]
                    break
            else:
                rows = [parsed_for_rows]
        else:
            rows = [{"value": parsed_for_rows}]

        all_rows.extend(rows)
        ctx.log_message(f"Page {page + 1}: fetched {len(rows)} rows (total: {len(all_rows)})")
        ctx.report_progress(page + 1, effective_max_pages)

        # Handle pagination
        if pagination and pagination_key and isinstance(parsed, dict):
            next_url = parsed.get(pagination_key, "")
            if next_url and isinstance(next_url, str):
                current_url = next_url
            else:
                ctx.log_message("No more pages (pagination key empty or missing)")
                break
        elif not pagination:
            break
        else:
            break

        # Rate limiting between pages
        if rate_limit_ms > 0 and page < effective_max_pages - 1:
            time.sleep(rate_limit_ms / 1000.0)

    if not all_rows:
        ctx.log_message("No data fetched. Saving empty dataset.")

    # Save as dataset
    out_dir = os.path.join(ctx.run_dir, "dataset")
    os.makedirs(out_dir, exist_ok=True)
    out_file = os.path.join(out_dir, "data.json")
    with open(out_file, "w") as f:
        json.dump(all_rows, f, indent=2, default=str)

    ctx.save_output("dataset", out_dir)
    _pages_fetched = min(page + 1, effective_max_pages) if all_rows else 0
    ctx.log_metric("total_rows", len(all_rows))
    ctx.log_metric("pages_fetched", _pages_fetched)
    ctx.log_message(f"Fetched {len(all_rows)} rows total.")
    ctx.report_progress(1, 1)

    # Save metrics output
    _col_names = list(all_rows[0].keys()) if all_rows else []
    _metrics = {"total_rows": len(all_rows), "pages_fetched": _pages_fetched, "column_count": len(_col_names), "columns": _col_names, "response_format": response_format}
    _mp = os.path.join(ctx.run_dir, "metrics.json")
    with open(_mp, "w") as f:
        json.dump(_metrics, f, indent=2)
    ctx.save_output("metrics", _mp)
