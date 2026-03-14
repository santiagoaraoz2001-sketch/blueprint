"""Code Agent — generate code solutions and optionally execute them.

Uses connected LLM Inference block for all model calls via shared utilities.
"""

import json
import os
import platform
import subprocess
import tempfile
import time

try:
    import resource as _resource
except ImportError:
    _resource = None  # unavailable on Windows

from backend.block_sdk.exceptions import BlockTimeoutError
from blocks.inference._inference_utils import call_inference


LANG_EXTENSIONS = {
    "python": ".py",
    "javascript": ".js",
    "bash": ".sh",
    "typescript": ".ts",
}

LANG_RUNNERS = {
    "python": ["python3"],
    "javascript": ["node"],
    "bash": ["bash"],
    "typescript": ["npx", "ts-node"],
}


def run(ctx):
    # ── Config ──────────────────────────────────────────────────────────
    language = ctx.config.get("language", "python")
    execute = ctx.config.get("execute", False)
    timeout = int(ctx.config.get("timeout", 60))
    max_iterations = int(ctx.config.get("max_iterations", 1))
    system_prompt = ctx.config.get("system_prompt", "")

    if isinstance(execute, str):
        execute = execute.lower() in ("true", "1", "yes")

    # ── Load LLM config from connected block ─────────────────────────
    llm_config = None
    try:
        llm_config = ctx.load_input("llm")
    except (ValueError, Exception):
        pass

    if llm_config and isinstance(llm_config, dict):
        framework = llm_config.get("framework", "ollama")
        model_name = llm_config.get("model", "")
        inf_config = llm_config.get("config", {})
        inf_config["max_tokens"] = 2048
        inf_config["temperature"] = 0.1
    else:
        framework = ""
        model_name = ""
        inf_config = {}

    # ── Load task ───────────────────────────────────────────────────────
    task = ctx.config.get("task", "")
    try:
        data = ctx.load_input("input")
        if isinstance(data, str):
            task = task or (data if not os.path.isfile(data) else open(data).read())
        elif isinstance(data, dict):
            task = task or data.get("task", data.get("text", data.get("prompt", "")))
    except (ValueError, Exception):
        pass

    if not task:
        task = "Write a function that calculates the fibonacci sequence up to n terms."

    # ── Load context (optional) ───────────────────────────────────────
    context_text = ""
    try:
        ctx_data = ctx.load_input("context")
        if isinstance(ctx_data, str):
            context_text = ctx_data if not os.path.isfile(ctx_data) else open(ctx_data).read()
        elif isinstance(ctx_data, dict):
            context_text = ctx_data.get("text", ctx_data.get("content", json.dumps(ctx_data)))
    except (ValueError, Exception):
        pass

    ctx.log_message(f"Code Agent: generating {language} code")
    ctx.log_message(f"Task: {task[:100]}...")

    # ── Check if real inference is available ──────────────────────────
    use_real = bool(llm_config and model_name)
    if not use_real:
        ctx.log_message("Demo mode: no LLM connected or no model specified.")

    # ── Generate (with optional retry loop) ─────────────────────────────
    generated_code = ""
    execution_result = None
    execution_success = False
    iterations_used = 0
    error_context = ""

    for iteration in range(max_iterations):
        iterations_used = iteration + 1
        ctx.log_message(f"\n--- Iteration {iterations_used}/{max_iterations} ---")

        # Generate code
        if use_real:
            generated_code = _generate_code(
                framework, model_name, inf_config,
                task, language, error_context, system_prompt, context_text,
            )
        else:
            generated_code = _demo_code(task, language)

        ctx.log_message(f"Generated {len(generated_code)} chars of {language}")
        ctx.report_progress(iteration + 1, max_iterations * 2)

        # Execute if enabled
        if execute and language in LANG_RUNNERS:
            ctx.log_message("Executing generated code...")
            execution_result = _execute_code(generated_code, language, timeout)
            execution_success = execution_result.get("returncode", 1) == 0

            if execution_success:
                ctx.log_message(f"Execution succeeded. Output: {execution_result.get('stdout', '')[:200]}")
                break
            else:
                error_msg = execution_result.get("stderr", execution_result.get("error", ""))
                ctx.log_message(f"Execution failed: {error_msg[:200]}")
                if iteration < max_iterations - 1:
                    error_context = (
                        f"The previous code failed with this error:\n{error_msg}\n"
                        f"Please fix the code."
                    )
                    ctx.log_message("Retrying with error context...")
        else:
            break

        ctx.report_progress(iteration + 1, max_iterations)

    # ── Save outputs ────────────────────────────────────────────────────
    ext = LANG_EXTENSIONS.get(language, ".txt")
    out_dir = os.path.join(ctx.run_dir, "code")
    os.makedirs(out_dir, exist_ok=True)
    code_path = os.path.join(out_dir, f"solution{ext}")
    with open(code_path, "w") as f:
        f.write(generated_code)

    ctx.save_output("artifact", code_path)

    output_format = ctx.config.get("output_format", "raw")
    if output_format == "markdown":
        formatted = f"```{language}\n{generated_code}\n```"
        if execution_result and execution_result.get("stdout"):
            formatted += f"\n\n**Output:**\n```\n{execution_result['stdout']}\n```"
        fmt_path = os.path.join(out_dir, "response.md")
        with open(fmt_path, "w") as f:
            f.write(formatted)
        # Branch: output_format == "markdown"
        ctx.save_output("text", fmt_path)
    elif output_format == "json":
        formatted = json.dumps({
            "code": generated_code,
            "language": language,
            "execution_result": execution_result,
            "execution_success": execution_success if execute else None,
        }, indent=2)
        fmt_path = os.path.join(out_dir, "response.json")
        with open(fmt_path, "w") as f:
            f.write(formatted)
        # Branch: output_format == "json"
        ctx.save_output("text", fmt_path)
    else:
        # Branch: output_format == "raw" (default)
        ctx.save_output("text", code_path)

    result_record = {
        "code": generated_code,
        "language": language,
        "task": task,
        "execution": execution_result,
        "execution_success": execution_success if execute else None,
        "iterations_used": iterations_used,
        "demo_mode": not use_real,
    }
    ds_dir = os.path.join(ctx.run_dir, "dataset")
    os.makedirs(ds_dir, exist_ok=True)
    with open(os.path.join(ds_dir, "data.json"), "w") as f:
        json.dump([result_record], f, indent=2)
    ctx.save_output("dataset", ds_dir)

    metrics = {
        "code_length": len(generated_code),
        "language": language,
        "executed": execute,
        "execution_success": execution_success if execute else None,
        "iterations_used": iterations_used,
        "model": model_name or "demo",
        "framework": framework or "demo",
    }
    ctx.save_output("metrics", metrics)
    for k, v in metrics.items():
        if isinstance(v, (int, float)):
            ctx.log_metric(k, v)

    ctx.log_message(f"Code agent complete. Saved to {code_path}")
    ctx.report_progress(1, 1)


# ── Helpers ─────────────────────────────────────────────────────────────


def _generate_code(framework, model_name, inf_config, task, language, error_context, system_prompt="", context_text=""):
    """Generate code using the connected LLM."""
    if system_prompt:
        prompt = f"{system_prompt}\n\n"
    else:
        prompt = (
            f"Write {language} code to solve this task. "
            f"Return ONLY the code, no explanations or markdown fences.\n\n"
        )
    if context_text:
        prompt += f"Context/Reference:\n{context_text}\n\n"
    prompt += f"Task: {task}\n"
    if error_context:
        prompt += f"\n{error_context}\n"
    prompt += "\nCode:"

    try:
        response, _ = call_inference(
            framework, model_name, prompt, config=inf_config,
        )
        return _strip_markdown_fences(response)
    except Exception as e:
        return f"# Error generating code: {e}"


def _strip_markdown_fences(code):
    """Remove markdown code fences from LLM output."""
    lines = code.strip().split("\n")
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines)


def _demo_code(task, language):
    """Generate demo code for common tasks."""
    task_lower = task.lower()

    if language == "python":
        if "fibonacci" in task_lower:
            return (
                'def fibonacci(n):\n'
                '    """Calculate fibonacci sequence up to n terms."""\n'
                '    if n <= 0:\n'
                '        return []\n'
                '    if n == 1:\n'
                '        return [0]\n'
                '    fib = [0, 1]\n'
                '    for i in range(2, n):\n'
                '        fib.append(fib[i-1] + fib[i-2])\n'
                '    return fib\n'
                '\n'
                'result = fibonacci(10)\n'
                'print(f"Fibonacci(10): {result}")\n'
            )
        if "sort" in task_lower:
            return (
                'def merge_sort(arr):\n'
                '    """Sort using merge sort."""\n'
                '    if len(arr) <= 1:\n'
                '        return arr\n'
                '    mid = len(arr) // 2\n'
                '    left = merge_sort(arr[:mid])\n'
                '    right = merge_sort(arr[mid:])\n'
                '    result, i, j = [], 0, 0\n'
                '    while i < len(left) and j < len(right):\n'
                '        if left[i] <= right[j]:\n'
                '            result.append(left[i]); i += 1\n'
                '        else:\n'
                '            result.append(right[j]); j += 1\n'
                '    result.extend(left[i:])\n'
                '    result.extend(right[j:])\n'
                '    return result\n'
                '\n'
                'arr = [38, 27, 43, 3, 9, 82, 10]\n'
                'print(f"Sorted: {merge_sort(arr)}")\n'
            )
        return (
            f'# Solution for: {task}\n'
            f'\n'
            f'def solve():\n'
            f'    result = "Solution placeholder"\n'
            f'    print(f"Result: {{result}}")\n'
            f'    return result\n'
            f'\n'
            f'if __name__ == "__main__":\n'
            f'    solve()\n'
        )

    if language == "javascript":
        return (
            f'// Solution for: {task}\n'
            f'\n'
            f'function solve() {{\n'
            f'  const result = "Solution placeholder";\n'
            f'  console.log(`Result: ${{result}}`);\n'
            f'  return result;\n'
            f'}}\n'
            f'\n'
            f'solve();\n'
        )

    if language == "bash":
        return (
            f'#!/bin/bash\n'
            f'# Solution for: {task}\n'
            f'\n'
            f'echo "Running solution..."\n'
            f'result="Solution placeholder"\n'
            f'echo "Result: $result"\n'
        )

    return f"// Solution for: {task}\n// Language: {language}\n"


def _make_preexec(memory_limit_mb):
    """Return a preexec_fn that sets memory limits on Unix systems."""
    if _resource is None or memory_limit_mb <= 0:
        return None

    def _set_limits():
        limit_bytes = memory_limit_mb * 1024 * 1024
        try:
            _resource.setrlimit(_resource.RLIMIT_AS, (limit_bytes, limit_bytes))
        except (ValueError, OSError):
            pass  # best-effort

    return _set_limits


def _execute_code(code, language, timeout, memory_limit_mb=512):
    """Execute generated code in a subprocess with timeout and memory limits."""
    runner = LANG_RUNNERS.get(language)
    if not runner:
        return {"error": f"No runner for {language}", "returncode": 1}

    ext = LANG_EXTENSIONS.get(language, ".txt")
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=ext, delete=False,
        ) as tmp:
            tmp.write(code)
            tmp_path = tmp.name

        result = subprocess.run(
            runner + [tmp_path],
            capture_output=True,
            text=True,
            timeout=timeout,
            preexec_fn=_make_preexec(memory_limit_mb),
        )
        return {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode,
        }
    except subprocess.TimeoutExpired:
        raise BlockTimeoutError(timeout, f"Code execution timed out after {timeout}s")
    except FileNotFoundError:
        return {"error": f"Runtime not found: {runner[0]}", "returncode": 1}
    except BlockTimeoutError:
        raise
    except Exception as e:
        return {"error": str(e), "returncode": 1}
    finally:
        try:
            os.unlink(tmp_path)
        except (OSError, UnboundLocalError):
            pass
