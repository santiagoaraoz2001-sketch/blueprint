"""Control Tower — send telemetry data to a local Control Tower instance."""

import json
import os
import urllib.request
import urllib.error


def run(ctx):
    host = ctx.config.get("host", "http://localhost")
    port = ctx.config.get("port", 4173)

    ctx.report_progress(0, 2)

    # Load telemetry input
    telemetry_data = ctx.load_input("telemetry")
    if telemetry_data is None:
        raise ValueError("No telemetry data received")

    # Normalize the data
    if isinstance(telemetry_data, str):
        if os.path.isfile(telemetry_data):
            with open(telemetry_data, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            try:
                payload = json.loads(content)
            except (json.JSONDecodeError, ValueError):
                payload = {"raw_text": content}
        else:
            try:
                payload = json.loads(telemetry_data)
            except (json.JSONDecodeError, ValueError):
                payload = {"raw_text": telemetry_data}
    elif isinstance(telemetry_data, (dict, list)):
        payload = telemetry_data
    else:
        payload = {"value": str(telemetry_data)}

    ctx.log_message(f"Sending telemetry to {host}:{port}")
    ctx.report_progress(1, 2)

    # POST telemetry to Control Tower
    url = f"{host}:{port}/api/telemetry"
    body = json.dumps(payload, default=str).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            status = resp.status
            resp_body = resp.read().decode("utf-8", errors="ignore")
        ctx.log_message(f"Control Tower responded: HTTP {status}")
    except urllib.error.URLError as e:
        ctx.log_message(f"Control Tower unreachable at {url}: {e.reason}")
        ctx.log_message("Data saved locally. Start Control Tower to receive telemetry.")
    except Exception as e:
        ctx.log_message(f"Failed to send telemetry: {e}")

    # Always save the payload locally
    out_path = os.path.join(ctx.run_dir, "telemetry_sent.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, default=str)

    ctx.save_output("telemetry", out_path)
    ctx.report_progress(2, 2)
