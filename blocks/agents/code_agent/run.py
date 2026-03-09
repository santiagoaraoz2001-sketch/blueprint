"""Code Agent — generate code solutions and optionally execute them."""

import json
import os
import subprocess
import tempfile
import time


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
    timeout = int(ctx.config.get("timeout", 30))
    max_iterations = int(ctx.config.get("max_iterations", 1))
    provider = ctx.config.get("provider", "ollama")
    endpoint = ctx.config.get("endpoint", "http://localhost:11434")

    system_prompt = ctx.config.get("system_prompt", "")

    if isinstance(execute, str):
        execute = execute.lower() in ("true", "1", "yes")

    # ── Load model info ─────────────────────────────────────────────────
    model_name = ctx.config.get("model_name", "")
    try:
        model_info = ctx.load_input("model")
        if isinstance(model_info, dict):
            model_name = model_name or model_info.get(
                "model_name", model_info.get("model_id", "")
            )
            provider = model_info.get("source", provider)
            endpoint = model_info.get("endpoint", endpoint)
    except (ValueError, Exception):
        pass

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

    # ── Check model availability ────────────────────────────────────────
    use_real = _check_provider(provider, model_name, endpoint)
    if not use_real:
        ctx.log_message("Demo mode: generating sample code.")

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
                provider, endpoint, model_name, task, language, error_context,
                system_prompt, context_text,
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

    # Always save raw code as artifact
    ctx.save_output("artifact", code_path)

    # Apply output format for text output
    output_format = ctx.config.get("output_format", "raw")
    if output_format == "markdown":
        formatted = f"```{language}\n{generated_code}\n```"
        if execution_result and execution_result.get("stdout"):
            formatted += f"\n\n**Output:**\n```\n{execution_result['stdout']}\n```"
        fmt_path = os.path.join(out_dir, "response.md")
        with open(fmt_path, "w") as f:
            f.write(formatted)
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
        ctx.save_output("text", fmt_path)
    else:
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
        "provider": provider,
    }
    ctx.save_output("metrics", metrics)
    for k, v in metrics.items():
        if isinstance(v, (int, float)):
            ctx.log_metric(k, v)

    ctx.log_message(f"Code agent complete. Saved to {code_path}")
    ctx.report_progress(1, 1)


# ── Helpers ─────────────────────────────────────────────────────────────


def _check_provider(provider, model_name, endpoint):
    if not model_name:
        return False
    if provider == "ollama":
        try:
            import urllib.request
            with urllib.request.urlopen(f"{endpoint.rstrip('/')}/api/tags", timeout=5):
                return True
        except Exception:
            return False
    if provider == "openai":
        return bool(os.environ.get("OPENAI_API_KEY"))
    if provider == "anthropic":
        return bool(os.environ.get("ANTHROPIC_API_KEY"))
    return False


def _generate_code(provider, endpoint, model_name, task, language, error_context, system_prompt="", context_text=""):
    """Generate code using an LLM."""
    import urllib.request

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

    if provider == "ollama":
        url = f"{endpoint.rstrip('/')}/api/generate"
        payload = json.dumps({
            "model": model_name,
            "prompt": prompt,
            "options": {"temperature": 0.1, "num_predict": 2048},
            "stream": False,
        }).encode()
        req = urllib.request.Request(
            url, data=payload, headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                code = json.loads(resp.read().decode()).get("response", "")
                return _strip_markdown_fences(code)
        except Exception as e:
            return f"# Error generating code: {e}"

    if provider == "openai":
        url = "https://api.openai.com/v1/chat/completions"
        payload = json.dumps({
            "model": model_name,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
            "max_tokens": 2048,
        }).encode()
        req = urllib.request.Request(url, data=payload, headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}",
        })
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read().decode())
                code = data["choices"][0]["message"]["content"]
                return _strip_markdown_fences(code)
        except Exception as e:
            return f"# Error generating code: {e}"

    if provider == "anthropic":
        url = "https://api.anthropic.com/v1/messages"
        payload = json.dumps({
            "model": model_name,
            "max_tokens": 2048,
            "messages": [{"role": "user", "content": prompt}],
        }).encode()
        req = urllib.request.Request(url, data=payload, headers={
            "Content-Type": "application/json",
            "x-api-key": os.environ["ANTHROPIC_API_KEY"],
            "anthropic-version": "2023-06-01",
        })
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read().decode())
                code = data["content"][0]["text"]
                return _strip_markdown_fences(code)
        except Exception as e:
            return f"# Error generating code: {e}"

    return f"# Unsupported provider: {provider}"


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


def _execute_code(code, language, timeout):
    """Execute generated code in a subprocess."""
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
        )
        return {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"error": "timeout", "timeout": timeout, "returncode": 1}
    except FileNotFoundError:
        return {
            "error": f"Runtime not found: {runner[0]}",
            "returncode": 1,
        }
    except Exception as e:
        return {"error": str(e), "returncode": 1}
    finally:
        try:
            os.unlink(tmp_path)
        except (OSError, UnboundLocalError):
            pass
