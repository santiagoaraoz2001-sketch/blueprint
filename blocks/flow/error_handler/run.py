"""Error Handler — wrap script execution with retry logic, error catching, and fallback behavior."""

import json
import os
import re
import signal
import traceback
import time


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


def run(ctx):
    max_retries = int(ctx.config.get("max_retries", 0))
    retry_delay = float(ctx.config.get("retry_delay", 1.0))
    exponential_backoff = ctx.config.get("exponential_backoff", False)
    on_error = ctx.config.get("on_error", "fallback")
    fallback_value = ctx.config.get("fallback_value", "{}").strip()
    script = ctx.config.get("script", "").strip()
    timeout_s = int(ctx.config.get("timeout_s", 0))
    error_pattern = ctx.config.get("error_pattern", "").strip()

    ctx.log_message(f"Error Handler: max_retries={max_retries}, delay={retry_delay}s, on_error={on_error}"
                    + (f", timeout={timeout_s}s" if timeout_s > 0 else "")
                    + (f", error_pattern='{error_pattern}'" if error_pattern else ""))

    # Load input
    raw_input = None
    try:
        raw_input = ctx.load_input("input")
    except (ValueError, Exception):
        pass
    input_data = _resolve_input(raw_input)

    # If a script is provided, execute it with retry logic
    if script:
        last_error = None
        total_attempts = max_retries + 1

        # Compile error_pattern regex if provided
        error_re = re.compile(error_pattern) if error_pattern else None

        def _timeout_handler(signum, frame):
            raise TimeoutError(f"Script execution timed out after {timeout_s}s")

        for attempt in range(total_attempts):
            try:
                if attempt > 0:
                    delay = retry_delay * (2 ** (attempt - 1)) if exponential_backoff else retry_delay
                    ctx.log_message(f"Retrying in {delay:.1f}s (attempt {attempt + 1}/{total_attempts})...")
                    time.sleep(delay)
                else:
                    ctx.log_message(f"Attempt {attempt + 1}/{total_attempts}...")

                exec_globals = {
                    "ctx": ctx,
                    "input_data": input_data,
                    "json": json,
                    "os": os,
                    "result": None,
                }

                # Set timeout if configured (Unix only)
                if timeout_s > 0 and hasattr(signal, "SIGALRM"):
                    old_handler = signal.signal(signal.SIGALRM, _timeout_handler)
                    signal.alarm(timeout_s)
                try:
                    exec(compile(script, "<error_handler_script>", "exec"), exec_globals)
                finally:
                    if timeout_s > 0 and hasattr(signal, "SIGALRM"):
                        signal.alarm(0)
                        signal.signal(signal.SIGALRM, old_handler)

                result = exec_globals.get("result", input_data)
                ctx.log_message(f"Script succeeded on attempt {attempt + 1}")
                # Branch: script succeeded
                ctx.save_output("output", result)
                # Branch: script succeeded
                ctx.save_output("error", None)
                ctx.log_metric("attempts", attempt + 1)
                ctx.log_metric("success", 1)
                ctx.report_progress(1, 1)
                return

            except Exception as e:
                last_error = e
                ctx.log_message(f"Attempt {attempt + 1} failed: {e}")

                # If error_pattern is set, only retry if error matches pattern
                if error_re and not error_re.search(str(e)):
                    ctx.log_message(f"Error does not match pattern '{error_pattern}' — stopping retries")
                    break

        # All retries exhausted
        error_info = {
            "error": str(last_error),
            "error_type": type(last_error).__name__,
            "traceback": traceback.format_exc(),
            "attempts": total_attempts,
        }

        # Write error report artifact
        error_path = os.path.join(ctx.run_dir, "error_report.json")
        with open(error_path, "w", encoding="utf-8") as f:
            json.dump(error_info, f, indent=2, default=str)

        ctx.log_message(f"All {total_attempts} attempts failed: {last_error}")
        ctx.log_metric("success", 0)
        ctx.log_metric("attempts", total_attempts)

        if on_error == "raise":
            # Branch: all retries failed — raise error
            ctx.save_output("output", None)
            # Branch: all retries failed — raise error
            ctx.save_output("error", error_info)
            ctx.save_artifact("error_report", error_path)
            raise RuntimeError(f"Error Handler: all {total_attempts} retries exhausted: {last_error}")
        elif on_error == "fallback":
            if fallback_value:
                try:
                    fallback = json.loads(fallback_value)
                except json.JSONDecodeError:
                    fallback = fallback_value
            else:
                fallback = None
            ctx.log_message("Using fallback value as output.")
            # Branch: all retries failed — use fallback
            ctx.save_output("output", fallback)
        else:  # "log"
            ctx.log_message("Error logged. Passing input through as output.")
            # Branch: all retries failed — log and continue
            ctx.save_output("output", input_data)

        # Branch: all retries failed — shared by fallback and log paths (raise path already saved error above)
        ctx.save_output("error", error_info)
        ctx.save_artifact("error_report", error_path)

    else:
        # No script — pass-through mode
        ctx.log_message("No script provided. Passing input through as output.")
        # Branch: no script provided — pass through
        ctx.save_output("output", input_data)
        # Branch: no script provided — pass through
        ctx.save_output("error", None)
        ctx.log_metric("success", 1)
        ctx.log_metric("attempts", 0)

    ctx.report_progress(1, 1)
