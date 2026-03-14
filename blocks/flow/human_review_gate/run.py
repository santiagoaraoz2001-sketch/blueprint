"""Human Review Gate — pause pipeline for human review and approval before continuing."""

import json
import os
import time
from datetime import datetime, timezone


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


def _generate_data_summary(data):
    """Generate a human-readable summary of the data for review."""
    summary = {}
    if isinstance(data, dict):
        summary["type"] = "dict"
        summary["keys"] = list(data.keys())[:50]
        summary["key_count"] = len(data)
    elif isinstance(data, list):
        summary["type"] = "list"
        summary["length"] = len(data)
        if data and isinstance(data[0], dict):
            summary["sample_keys"] = list(data[0].keys())
            summary["sample_record"] = {
                k: str(v)[:200] for k, v in list(data[0].items())[:10]
            }
    elif isinstance(data, str):
        summary["type"] = "string"
        summary["length"] = len(data)
        summary["preview"] = data[:500]
    else:
        summary["type"] = type(data).__name__
        summary["preview"] = str(data)[:500]
    return summary


def run(ctx):
    review_prompt = ctx.config.get("review_prompt", "Review the data and approve to continue")
    auto_approve_after_s = int(ctx.config.get("auto_approve_after_s", 0))
    require_comment = ctx.config.get("require_comment", False)
    poll_interval_s = int(ctx.config.get("poll_interval_s", 5))
    reviewer_name = ctx.config.get("reviewer_name", "").strip()
    urgency = ctx.config.get("urgency", "normal").lower().strip()
    auto_action = ctx.config.get("auto_action", "approve").lower().strip()
    display_fields = ctx.config.get("display_fields", "").strip()
    include_data_in_notes = ctx.config.get("include_data_in_notes", True)

    ctx.log_message("Human Review Gate activated")
    ctx.report_progress(0, 4)

    # ---- Step 1: Load data to review ----
    ctx.report_progress(1, 4)
    raw_data = ctx.load_input("data")
    if raw_data is None:
        raise ValueError("No data provided for review. Connect a 'data' input to this block.")

    data = _resolve_input(raw_data)

    # Filter data summary to display_fields if configured
    if display_fields and isinstance(data, list) and data and isinstance(data[0], dict):
        allowed = [f.strip() for f in display_fields.split(",") if f.strip()]
        filtered = [{k: row.get(k) for k in allowed if k in row} for row in data]
        data_summary = _generate_data_summary(filtered)
        data_summary["display_fields"] = allowed
    elif display_fields and isinstance(data, dict):
        allowed = [f.strip() for f in display_fields.split(",") if f.strip()]
        filtered = {k: data[k] for k in allowed if k in data}
        data_summary = _generate_data_summary(filtered)
        data_summary["display_fields"] = allowed
    else:
        data_summary = _generate_data_summary(data)
    ctx.log_message(f"Data loaded for review: type={data_summary.get('type')}")

    # ---- Step 2: Create review request ----
    ctx.report_progress(2, 4)
    now = datetime.now(timezone.utc)
    review_id = f"review_{now.strftime('%Y%m%d_%H%M%S')}"

    review_request = {
        "review_id": review_id,
        "status": "pending",
        "created_at": now.isoformat(),
        "prompt": review_prompt,
        "require_comment": require_comment,
        "auto_approve_after_s": auto_approve_after_s,
        "reviewer_name": reviewer_name or None,
        "urgency": urgency,
        "data_summary": data_summary,
    }

    # Write review request file
    request_path = os.path.join(ctx.run_dir, "review_request.json")
    with open(request_path, "w", encoding="utf-8") as f:
        json.dump(review_request, f, indent=2, default=str, ensure_ascii=False)

    # Write the full data for reviewer inspection
    review_data_path = os.path.join(ctx.run_dir, "review_data.json")
    with open(review_data_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str, ensure_ascii=False)

    # Write status file (pending)
    status_path = os.path.join(ctx.run_dir, "review_status.json")
    status_record = {
        "review_id": review_id,
        "status": "pending",
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
        "approved": None,
        "reviewer": None,
        "comment": None,
    }
    with open(status_path, "w", encoding="utf-8") as f:
        json.dump(status_record, f, indent=2, default=str, ensure_ascii=False)

    # Define the approval file path
    approval_path = os.path.join(ctx.run_dir, "review_approval.json")

    ctx.log_message(f"Review request created: {review_id}")
    ctx.log_message(f"Urgency: {urgency.upper()}")
    if reviewer_name:
        ctx.log_message(f"Assigned reviewer: {reviewer_name}")
    ctx.log_message(f"Review prompt: {review_prompt}")
    ctx.log_message(f"Data saved for inspection at: {review_data_path}")
    ctx.log_message("")
    ctx.log_message("=" * 60)
    ctx.log_message("WAITING FOR HUMAN REVIEW")
    ctx.log_message("=" * 60)
    ctx.log_message(f"To APPROVE: create {approval_path}")
    ctx.log_message('  Contents: {"approved": true, "comment": "Looks good"}')
    ctx.log_message(f"To REJECT:  create {approval_path}")
    ctx.log_message('  Contents: {"approved": false, "comment": "Reason..."}')
    if auto_approve_after_s > 0:
        ctx.log_message(f"Timeout: {auto_approve_after_s}s → auto-{auto_action}")
    else:
        ctx.log_message("No timeout set — will wait indefinitely.")
    ctx.log_message("=" * 60)

    # ---- Step 3: Poll for approval ----
    ctx.report_progress(3, 4)
    approved = None
    reviewer_comment = None
    start_time = time.time()

    while approved is None:
        # Check for approval file
        if os.path.isfile(approval_path):
            try:
                with open(approval_path, "r", encoding="utf-8") as f:
                    decision = json.load(f)
                approved = bool(decision.get("approved", False))
                reviewer_comment = decision.get("comment", "")
                reviewer = decision.get("reviewer", "unknown")

                if require_comment and not reviewer_comment:
                    ctx.log_message("Comment required but not provided — waiting for comment...")
                    approved = None
                    time.sleep(poll_interval_s)
                    continue

                ctx.log_message(f"Review decision received: {'APPROVED' if approved else 'REJECTED'}")
                if reviewer_comment:
                    ctx.log_message(f"Reviewer comment: {reviewer_comment}")
                break
            except (json.JSONDecodeError, ValueError):
                ctx.log_message("WARNING: review_approval.json is malformed, waiting...")

        # Check timeout — auto_action determines approve or reject
        elapsed = time.time() - start_time
        if auto_approve_after_s > 0 and elapsed >= auto_approve_after_s:
            if auto_action == "reject":
                approved = False
                reviewer_comment = f"Auto-rejected after {auto_approve_after_s}s timeout (no reviewer responded)"
                ctx.log_message(f"Auto-REJECTED: timeout of {auto_approve_after_s}s reached")
            else:
                approved = True
                reviewer_comment = f"Auto-approved after {auto_approve_after_s}s timeout (no reviewer responded)"
                ctx.log_message(f"Auto-approved: timeout of {auto_approve_after_s}s reached")
            break

        time.sleep(poll_interval_s)

    # ---- Step 4: Produce outputs ----
    ctx.report_progress(4, 4)

    decision_time = datetime.now(timezone.utc)
    status_record["status"] = "approved" if approved else "rejected"
    status_record["approved"] = approved
    status_record["updated_at"] = decision_time.isoformat()
    status_record["comment"] = reviewer_comment
    with open(status_path, "w", encoding="utf-8") as f:
        json.dump(status_record, f, indent=2, default=str, ensure_ascii=False)

    review_notes = {
        "review_id": review_id,
        "approved": approved,
        "review_prompt": review_prompt,
        "require_comment": require_comment,
        "reviewer_comment": reviewer_comment,
        "assigned_reviewer": reviewer_name or None,
        "urgency": urgency,
        "created_at": now.isoformat(),
        "decided_at": decision_time.isoformat(),
    }
    if include_data_in_notes:
        review_notes["data_summary"] = data_summary

    notes_path = os.path.join(ctx.run_dir, "review_notes.json")
    with open(notes_path, "w", encoding="utf-8") as f:
        json.dump(review_notes, f, indent=2, default=str, ensure_ascii=False)

    if approved:
        # Branch: data approved
        ctx.save_output("approved", data)
        # Branch: data approved
        ctx.save_output("rejected", None)
        ctx.log_message("GATE PASSED: data approved and forwarded downstream")
    else:
        # Branch: data rejected
        ctx.save_output("approved", None)
        # Branch: data rejected
        ctx.save_output("rejected", data)
        ctx.log_message("GATE BLOCKED: data was rejected")

    ctx.save_output("review_notes", review_notes)
    ctx.save_artifact("review_request", request_path)
    ctx.save_artifact("review_notes", notes_path)
    ctx.log_metric("gate_approved", 1.0 if approved else 0.0)
    ctx.log_message("Human Review Gate complete.")
