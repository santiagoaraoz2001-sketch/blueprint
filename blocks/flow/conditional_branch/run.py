"""Conditional Branch — evaluate a condition on input and route to true_branch or false_branch."""

import ast
import json
import os
import re


def _load_data(ctx, port_name):
    """Load and resolve input data from a port, handling file/directory paths."""
    try:
        raw = ctx.load_input(port_name)
    except (ValueError, Exception):
        return None

    if isinstance(raw, str) and os.path.isdir(raw):
        data_file = os.path.join(raw, "data.json")
        if os.path.isfile(data_file):
            with open(data_file, "r") as f:
                return json.load(f)
        return None
    elif isinstance(raw, str) and os.path.isfile(raw):
        with open(raw, "r") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return f.read()
    return raw


def _safe_eval(expression, variables):
    """Evaluate a simple Python expression safely using AST parsing.

    Allows only comparisons, boolean ops, arithmetic, and variable lookups.
    No function calls, attribute access, or imports.
    """
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError:
        return None

    # Walk AST and reject anything dangerous
    for node in ast.walk(tree):
        if isinstance(node, (ast.Call, ast.Attribute, ast.Import, ast.ImportFrom)):
            return None
        if isinstance(node, ast.Name) and node.id.startswith("_"):
            return None

    try:
        code = compile(tree, "<condition>", "eval")
        return eval(code, {"__builtins__": {}}, variables)
    except Exception:
        return None


def _extract_field(data, field):
    """Extract a field value from input data, supporting dot notation for nested access.

    Examples:
        'accuracy'              -> data['accuracy']
        'model.metrics.f1'      -> data['model']['metrics']['f1']
        'results.0.score'       -> data['results'][0]['score']
    """
    if not field:
        return data

    parts = field.split(".")
    current = data
    for part in parts:
        if isinstance(current, dict):
            if part in current:
                current = current[part]
            else:
                return data  # field not found — fall back to root
        elif isinstance(current, list):
            try:
                idx = int(part)
                current = current[idx]
            except (ValueError, IndexError):
                if current and isinstance(current[0], dict):
                    return current[0].get(part)
                return data
        else:
            return data
    return current


def _evaluate_operator(test_value, operator, value):
    """Apply a comparison operator and return (bool, description)."""
    try:
        if operator == "equals":
            return str(test_value) == str(value), f"{test_value!r} == {value!r}"
        elif operator == "not_equals":
            return str(test_value) != str(value), f"{test_value!r} != {value!r}"
        elif operator == "greater_than":
            return float(test_value) > float(value), f"{test_value} > {value}"
        elif operator == "less_than":
            return float(test_value) < float(value), f"{test_value} < {value}"
        elif operator == "greater_equal":
            return float(test_value) >= float(value), f"{test_value} >= {value}"
        elif operator == "less_equal":
            return float(test_value) <= float(value), f"{test_value} <= {value}"
        elif operator == "contains":
            return str(value) in str(test_value), f"{value!r} in {test_value!r}"
        elif operator == "not_contains":
            return str(value) not in str(test_value), f"{value!r} not in {test_value!r}"
        elif operator == "is_empty":
            result = test_value is None or str(test_value).strip() == ""
            return result, f"is_empty({test_value!r})"
        elif operator == "is_not_empty":
            result = test_value is not None and str(test_value).strip() != ""
            return result, f"is_not_empty({test_value!r})"
        elif operator == "matches_regex":
            result = bool(re.search(value, str(test_value)))
            return result, f"regex({value!r}, {test_value!r})"
        elif operator == "is_true":
            return bool(test_value), f"is_true({test_value!r})"
        elif operator == "is_false":
            return not bool(test_value), f"is_false({test_value!r})"
        elif operator == "row_count_gt":
            count = len(test_value) if isinstance(test_value, (list, dict, str)) else 0
            return count > float(value), f"row_count({count}) > {value}"
        elif operator == "row_count_lt":
            count = len(test_value) if isinstance(test_value, (list, dict, str)) else 0
            return count < float(value), f"row_count({count}) < {value}"
        elif operator == "row_count_eq":
            count = len(test_value) if isinstance(test_value, (list, dict, str)) else 0
            return count == int(value), f"row_count({count}) == {value}"
        elif operator == "type_is":
            type_map = {"list": list, "dict": dict, "str": str, "int": int, "float": float, "bool": bool, "none": type(None)}
            expected = type_map.get(value.lower().strip())
            result = isinstance(test_value, expected) if expected else False
            return result, f"type_is({type(test_value).__name__}, {value})"
        else:
            return False, f"unknown operator: {operator}"
    except (ValueError, TypeError) as e:
        return False, f"error: {e}"


def run(ctx):
    field = ctx.config.get("field", "")
    operator = ctx.config.get("operator", "equals")
    value = ctx.config.get("value", "")
    condition = ctx.config.get("condition", "")
    use_condition_data = ctx.config.get("use_condition_data", False)

    # Load main input data
    input_data = _load_data(ctx, "input")
    if input_data is None:
        raise ValueError(
            "Required input 'input' not connected or produced no data. "
            "Connect data to the 'Input Data' port."
        )

    # Determine what to evaluate: main input or external condition data
    if use_condition_data:
        eval_data = _load_data(ctx, "condition_data")
        if eval_data is None:
            ctx.log_message("Warning: 'Use External Condition Data' is on but no condition_data connected. Falling back to main input.")
            eval_data = input_data
    else:
        eval_data = input_data

    # Custom expression takes priority
    tested_value = None
    if condition.strip() and not field:
        safe_vars = {}
        if isinstance(eval_data, dict):
            safe_vars = {k: v for k, v in eval_data.items() if isinstance(v, (int, float, str, bool, type(None)))}

        result = _safe_eval(condition, safe_vars)
        if result is None:
            ctx.log_message(f"Expression '{condition}' could not be evaluated safely. Defaulting to False.")
            condition_met = False
            eval_desc = f"expression failed: {condition}"
        else:
            condition_met = bool(result)
            eval_desc = f"expression: {condition} => {condition_met}"
        ctx.log_message(f"Custom condition: {eval_desc}")
    else:
        # Field + operator evaluation
        test_value = _extract_field(eval_data, field)
        tested_value = test_value
        condition_met, eval_desc = _evaluate_operator(test_value, operator, value)
        ctx.log_message(f"Condition: {field or '(root)'} {operator} {value!r} => {eval_desc} => {condition_met}")

    # Route data
    if condition_met:
        ctx.log_message("Routing to: TRUE branch")
        ctx.save_output("true_branch", input_data)
        ctx.save_output("false_branch", None)
    else:
        ctx.log_message("Routing to: FALSE branch")
        ctx.save_output("true_branch", None)
        ctx.save_output("false_branch", input_data)

    result_info = {
        "condition_met": condition_met,
        "branch": "true_branch" if condition_met else "false_branch",
        "evaluation": eval_desc,
    }
    # Include the tested value for observability (helps debugging)
    try:
        json.dumps(tested_value)  # only include if JSON-serializable
        result_info["tested_value"] = tested_value
    except (TypeError, ValueError):
        result_info["tested_value"] = str(tested_value)
    ctx.save_output("result", result_info)
    ctx.log_metric("condition_met", 1 if condition_met else 0)
    ctx.report_progress(1, 1)
