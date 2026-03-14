"""Manual Review — rich human review with scoring rubric and structured approval workflow."""

import json
import os
import time
from datetime import datetime, timezone


def _generate_data_summary(data):
    """Generate a human-readable summary of the data for review."""
    if isinstance(data, dict):
        return {"type": "dict", "keys": list(data.keys())[:50], "key_count": len(data)}
    elif isinstance(data, list):
        summary = {"type": "list", "length": len(data)}
        if data and isinstance(data[0], dict):
            summary["sample_keys"] = list(data[0].keys())
            summary["sample_record"] = {k: str(v)[:200] for k, v in list(data[0].items())[:10]}
        return summary
    elif isinstance(data, str):
        return {"type": "string", "length": len(data), "preview": data[:500]}
    return {"type": type(data).__name__, "preview": str(data)[:500]}


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
    review_criteria = ctx.config.get("review_criteria", "Check for accuracy and completeness")
    scoring_rubric = ctx.config.get("scoring_rubric", "overall: 1-5")
    require_score = ctx.config.get("require_score", True)
    min_passing_score = float(ctx.config.get("min_passing_score", 0.0))
    poll_interval_s = int(ctx.config.get("poll_interval_s", 5))
    auto_approve_after_s = int(ctx.config.get("auto_approve_after_s", 0))
    review_type = ctx.config.get("review_type", "approve_reject").lower().strip()
    priority = ctx.config.get("priority", "normal").lower().strip()
    auto_action = ctx.config.get("auto_action", "approve").lower().strip()
    decision_options = ctx.config.get("decision_options", "").strip()

    ctx.log_message("Manual Review block activated")
    ctx.report_progress(0, 4)

    # ---- Step 1: Load data ----
    ctx.report_progress(1, 4)
    raw_data = ctx.resolve_as_data("data")
    if not raw_data:
        raise ValueError("No data provided for review. Connect a 'data' input.")
    data = raw_data
    data_summary = _generate_data_summary(data)
    ctx.log_message(f"Data loaded: type={data_summary.get('type')}")

    # ---- Step 2: Create review request with rubric ----
    ctx.report_progress(2, 4)
    now = datetime.now(timezone.utc)
    review_id = f"manual_review_{now.strftime('%Y%m%d_%H%M%S')}"
    rubric = _parse_rubric(scoring_rubric)

    # Parse custom decision options (e.g., "safe, flagged, escalate, remove")
    custom_decisions = []
    if decision_options:
        custom_decisions = [d.strip() for d in decision_options.split(",") if d.strip()]

    review_request = {
        "review_id": review_id,
        "status": "pending",
        "created_at": now.isoformat(),
        "review_type": review_type,
        "priority": priority,
        "criteria": review_criteria,
        "rubric": rubric,
        "require_score": require_score,
        "min_passing_score": min_passing_score,
        "data_summary": data_summary,
    }
    if custom_decisions:
        review_request["decision_options"] = custom_decisions

    request_path = os.path.join(ctx.run_dir, "review_request.json")
    with open(request_path, "w", encoding="utf-8") as f:
        json.dump(review_request, f, indent=2, default=str, ensure_ascii=False)

    review_data_path = os.path.join(ctx.run_dir, "review_data.json")
    with open(review_data_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str, ensure_ascii=False)

    approval_path = os.path.join(ctx.run_dir, "review_decision.json")

    ctx.log_message(f"Review request created: {review_id}")
    ctx.log_message(f"Type: {review_type}, Priority: {priority.upper()}")
    ctx.log_message(f"Criteria: {review_criteria}")
    ctx.log_message(f"Rubric: {rubric}")
    ctx.log_message("")
    ctx.log_message("=" * 60)
    ctx.log_message("WAITING FOR MANUAL REVIEW")
    ctx.log_message("=" * 60)
    ctx.log_message(f"Data to review: {review_data_path}")
    ctx.log_message(f"To submit review, create: {approval_path}")
    ctx.log_message('Example: {"approved": true, "scores": {"accuracy": 4, "fluency": 5}, "notes": "Good quality"}')
    if custom_decisions:
        ctx.log_message(f"Custom decision options: {custom_decisions}")
    if auto_approve_after_s > 0:
        ctx.log_message(f"Timeout: {auto_approve_after_s}s → auto-{auto_action}")
    ctx.log_message("=" * 60)

    # ---- Step 3: Poll for review decision ----
    ctx.report_progress(3, 4)
    decision = None
    start_time = time.time()

    while decision is None:
        if os.path.isfile(approval_path):
            try:
                with open(approval_path, "r", encoding="utf-8") as f:
                    decision = json.load(f)
                ctx.log_message("Review decision received")
            except (json.JSONDecodeError, ValueError):
                ctx.log_message("WARNING: review_decision.json is malformed, waiting...")
                decision = None

        if decision is None:
            elapsed = time.time() - start_time
            if auto_approve_after_s > 0 and elapsed >= auto_approve_after_s:
                auto_approved = auto_action != "reject"
                decision = {
                    "approved": auto_approved,
                    "scores": {c["name"]: c["max"] for c in rubric} if auto_approved else {},
                    "notes": f"Auto-{auto_action}ed after {auto_approve_after_s}s timeout",
                }
                ctx.log_message(f"Auto-{auto_action}ed: timeout of {auto_approve_after_s}s reached")
                break
            time.sleep(poll_interval_s)

    # ---- Step 4: Process decision and route outputs ----
    ctx.report_progress(4, 4)

    approved = bool(decision.get("approved", False))
    scores = decision.get("scores", {})
    notes = decision.get("notes", "")
    reviewer = decision.get("reviewer", "unknown")
    chosen_decision = decision.get("decision", "")

    # If custom decision_options are configured and reviewer used them
    if custom_decisions and chosen_decision:
        ctx.log_message(f"Custom decision: {chosen_decision}")
        ctx.log_metric("decision_label", chosen_decision)

    # In scoring_only mode, approval is determined entirely by the score vs min_passing_score
    if review_type == "scoring_only":
        approved = True  # default to pass; will be overridden below if score is too low

    # Validate scores against rubric
    for criterion in rubric:
        name = criterion["name"]
        if name in scores:
            score = float(scores[name])
            if score < criterion["min"] or score > criterion["max"]:
                ctx.log_message(
                    f"WARNING: score for '{name}' ({score}) is outside "
                    f"rubric range [{criterion['min']}-{criterion['max']}]"
                )

    # Calculate normalized score (0-1 range)
    if scores and rubric:
        total_normalized = 0.0
        count = 0
        for criterion in rubric:
            name = criterion["name"]
            if name in scores:
                raw = float(scores[name])
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
    else:
        avg_score = None

    decision_time = datetime.now(timezone.utc)
    review_notes = {
        "review_id": review_id,
        "approved": approved,
        "review_type": review_type,
        "priority": priority,
        "scores": scores,
        "avg_normalized_score": avg_score,
        "notes": notes,
        "reviewer": reviewer,
        "criteria": review_criteria,
        "rubric": rubric,
        "created_at": now.isoformat(),
        "decided_at": decision_time.isoformat(),
    }
    if chosen_decision:
        review_notes["decision_label"] = chosen_decision

    notes_path = os.path.join(ctx.run_dir, "review_notes.json")
    with open(notes_path, "w", encoding="utf-8") as f:
        json.dump(review_notes, f, indent=2, default=str, ensure_ascii=False)

    if approved:
        # Branch: data approved
        ctx.save_output("approved", data)
        # Branch: data approved
        ctx.save_output("rejected", None)
        ctx.log_message(f"APPROVED: data forwarded downstream (score: {avg_score})")
    else:
        # Branch: data rejected
        ctx.save_output("approved", None)
        # Branch: data rejected
        ctx.save_output("rejected", data)
        ctx.log_message(f"REJECTED: data routed to rejection path (score: {avg_score})")

    ctx.save_output("notes", review_notes)
    ctx.save_artifact("review_request", request_path)
    ctx.save_artifact("review_notes", notes_path)
    ctx.log_metric("approved", 1.0 if approved else 0.0)
    ctx.log_message("Manual Review complete.")
