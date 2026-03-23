"""Human Review Gate — pause pipeline for human review with optional scoring rubric."""

import json
import os
import time
from datetime import datetime, timezone

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


def _parse_rubric(rubric_text):
    """Parse rubric text into structured criteria.

    Supported formats:
      - Simple: 'accuracy, fluency, relevance' (defaults to 1-5 scale)
      - Detailed: 'accuracy: 1-10\nfluency: 1-5\nrelevance: 1-5'
    """
    criteria = []
    if not rubric_text.strip():
        return [{"name": "overall", "min": 1, "max": 5}]

    for part in rubric_text.replace(",", "\n").splitlines():
        part = part.strip()
        if not part:
            continue
        if ":" in part:
            name, scale = part.split(":", 1)
            name = name.strip()
            scale = scale.strip()
            if "-" in scale:
                try:
                    lo, hi = scale.split("-", 1)
                    criteria.append({"name": name, "min": int(lo.strip()), "max": int(hi.strip())})
                except ValueError:
                    criteria.append({"name": name, "min": 1, "max": 5})
            else:
                criteria.append({"name": name, "min": 1, "max": 5})
        else:
            criteria.append({"name": part, "min": 1, "max": 5})
    return criteria if criteria else [{"name": "overall", "min": 1, "max": 5}]


def run(ctx):
    review_prompt = ctx.config.get("review_prompt",
                                    ctx.config.get("review_criteria", "Review the data and approve to continue"))
    auto_approve_after_s = int(ctx.config.get("auto_approve_after_s", 0))
    require_comment = ctx.config.get("require_comment", False)
    poll_interval_s = int(ctx.config.get("poll_interval_s", 5))
    reviewer_name = ctx.config.get("reviewer_name", "").strip()
    urgency = ctx.config.get("urgency",
                              ctx.config.get("priority", "normal")).lower().strip()
    auto_action = ctx.config.get("auto_action", "approve").lower().strip()
    display_fields = ctx.config.get("display_fields", "").strip()
    include_data_in_notes = ctx.config.get("include_data_in_notes", True)
    decision_options = ctx.config.get("decision_options", "").strip()

    # Scoring config
    enable_scoring = ctx.config.get("enable_scoring", False)
    scoring_rubric = ctx.config.get("scoring_rubric", "overall: 1-5")
    require_score = ctx.config.get("require_score", True)
    min_passing_score = float(ctx.config.get("min_passing_score", 0.0))
    review_type = ctx.config.get("review_type", "approve_reject").lower().strip()

    ctx.log_message("Human Review Gate activated")
    ctx.report_progress(0, 4)

    # ---- Step 1: Load data to review ----
    ctx.report_progress(1, 4)
    raw_data = ctx.resolve_as_data("data")
    if not raw_data:
        raise BlockInputError("No data provided for review. Connect a 'data' input to this block.", recoverable=False)

    data = raw_data

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

    # Parse rubric if scoring is enabled
    rubric = _parse_rubric(scoring_rubric) if enable_scoring else None

    # Parse custom decision options
    custom_decisions = []
    if decision_options:
        custom_decisions = [d.strip() for d in decision_options.split(",") if d.strip()]

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
    if enable_scoring:
        review_request["review_type"] = review_type
        review_request["rubric"] = rubric
        review_request["require_score"] = require_score
        review_request["min_passing_score"] = min_passing_score
    if custom_decisions:
        review_request["decision_options"] = custom_decisions

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
    if enable_scoring:
        ctx.log_message('  Contents: {"approved": true, "scores": {"accuracy": 4, "fluency": 5}, "comment": "Good"}')
        ctx.log_message(f"  Rubric: {rubric}")
    else:
        ctx.log_message('  Contents: {"approved": true, "comment": "Looks good"}')
    ctx.log_message(f"To REJECT:  create {approval_path}")
    ctx.log_message('  Contents: {"approved": false, "comment": "Reason..."}')
    if custom_decisions:
        ctx.log_message(f"Custom decision options: {custom_decisions}")
    if auto_approve_after_s > 0:
        ctx.log_message(f"Timeout: {auto_approve_after_s}s → auto-{auto_action}")
    else:
        ctx.log_message("No timeout set — will wait indefinitely.")
    ctx.log_message("=" * 60)

    # ---- Step 3: Poll for approval ----
    ctx.report_progress(3, 4)
    decision = None
    start_time = time.time()

    while decision is None:
        # Check for approval file
        if os.path.isfile(approval_path):
            try:
                with open(approval_path, "r", encoding="utf-8") as f:
                    decision = json.load(f)

                if require_comment and not decision.get("comment", ""):
                    ctx.log_message("Comment required but not provided — waiting for comment...")
                    decision = None
                    time.sleep(poll_interval_s)
                    continue

                ctx.log_message("Review decision received")
                break
            except (json.JSONDecodeError, ValueError):
                ctx.log_message("WARNING: review_approval.json is malformed, waiting...")
                decision = None

        # Check timeout
        elapsed = time.time() - start_time
        if auto_approve_after_s > 0 and elapsed >= auto_approve_after_s:
            auto_approved = auto_action != "reject"
            decision = {
                "approved": auto_approved,
                "comment": f"Auto-{auto_action}ed after {auto_approve_after_s}s timeout (no reviewer responded)",
            }
            if enable_scoring and auto_approved and rubric:
                decision["scores"] = {c["name"]: c["max"] for c in rubric}
            ctx.log_message(f"Auto-{auto_action}ed: timeout of {auto_approve_after_s}s reached")
            break

        time.sleep(poll_interval_s)

    # ---- Step 4: Process decision and route outputs ----
    ctx.report_progress(4, 4)

    approved = bool(decision.get("approved", False))
    reviewer_comment = decision.get("comment", decision.get("notes", ""))
    reviewer = decision.get("reviewer", "unknown")
    scores = decision.get("scores", {})
    chosen_decision = decision.get("decision", "")

    # Handle custom decision options
    if custom_decisions and chosen_decision:
        ctx.log_message(f"Custom decision: {chosen_decision}")

    # In scoring_only mode, approval is determined by score vs min_passing_score
    if enable_scoring and review_type == "scoring_only":
        approved = True  # default to pass; overridden below if score too low

    # Calculate normalized score if scoring is enabled
    avg_score = None
    if enable_scoring and scores and rubric:
        total_normalized = 0.0
        count = 0
        for criterion in rubric:
            name = criterion["name"]
            if name in scores:
                raw = float(scores[name])
                # Validate range
                if raw < criterion["min"] or raw > criterion["max"]:
                    ctx.log_message(
                        f"WARNING: score for '{name}' ({raw}) is outside "
                        f"rubric range [{criterion['min']}-{criterion['max']}]"
                    )
                normalized = (raw - criterion["min"]) / max(criterion["max"] - criterion["min"], 1)
                total_normalized += normalized
                count += 1
                ctx.log_metric(f"score_{name}", raw)
        avg_score = total_normalized / max(count, 1)
        ctx.log_metric("avg_normalized_score", avg_score)

        # Override approval if min_passing_score is set and score is below
        if min_passing_score > 0 and avg_score < min_passing_score:
            ctx.log_message(
                f"Score {avg_score:.3f} is below minimum {min_passing_score} — overriding to REJECTED"
            )
            approved = False

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
    if enable_scoring:
        review_notes["review_type"] = review_type
        review_notes["scores"] = scores
        review_notes["avg_normalized_score"] = avg_score
        review_notes["rubric"] = rubric
    if chosen_decision:
        review_notes["decision_label"] = chosen_decision
    if include_data_in_notes:
        review_notes["data_summary"] = data_summary

    notes_path = os.path.join(ctx.run_dir, "review_notes.json")
    with open(notes_path, "w", encoding="utf-8") as f:
        json.dump(review_notes, f, indent=2, default=str, ensure_ascii=False)

    if approved:
        ctx.save_output("approved", data)
        ctx.save_output("rejected", None)
        score_info = f" (score: {avg_score:.3f})" if avg_score is not None else ""
        ctx.log_message(f"GATE PASSED: data approved and forwarded downstream{score_info}")
    else:
        ctx.save_output("approved", None)
        ctx.save_output("rejected", data)
        score_info = f" (score: {avg_score:.3f})" if avg_score is not None else ""
        ctx.log_message(f"GATE BLOCKED: data was rejected{score_info}")

    ctx.save_output("review_notes", review_notes)
    ctx.save_artifact("review_request", request_path)
    ctx.save_artifact("review_notes", notes_path)
    ctx.log_metric("gate_approved", 1.0 if approved else 0.0)
    ctx.log_message("Human Review Gate complete.")
