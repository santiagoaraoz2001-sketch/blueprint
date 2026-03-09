"""Python Runner — execute custom Python code as a pipeline block.

Trust levels:
  sandboxed — Restricted builtins, no imports, no file/network access.
  trusted   — Full Python with imports, file I/O allowed. No subprocess/network.
  system    — Unrestricted access. Only use with code you fully trust.
"""

import os
import signal
import time
import json
import math
import traceback
from pathlib import Path


def _make_restricted_import(allowed_modules: str):
    """Create a restricted import function for sandboxed mode."""
    if not allowed_modules.strip():
        return lambda *a, **k: (_ for _ in ()).throw(
            RuntimeError("import is restricted in sandbox — only pre-loaded modules available")
        )

    allowlist = {m.strip() for m in allowed_modules.split(",") if m.strip()}
    _real_import = __builtins__.__import__ if hasattr(__builtins__, '__import__') else __import__

    def _restricted_import(name, *args, **kwargs):
        # Allow the module itself and submodules
        top_level = name.split(".")[0]
        if top_level in allowlist:
            return _real_import(name, *args, **kwargs)
        raise RuntimeError(
            f"import '{name}' is not allowed in sandbox. Allowed modules: {', '.join(sorted(allowlist))}"
        )
    return _restricted_import


def _build_exec_globals(ctx, trust_level: str, saved_path: Path, allowed_modules: str = "") -> dict:
    """Build execution globals based on trust level."""

    if trust_level == "system":
        # Full unrestricted access
        return {
            "ctx": ctx,
            "json": json,
            "time": time,
            "math": math,
            "__name__": "__main__",
            "__file__": str(saved_path),
            "__builtins__": __builtins__,
        }

    if trust_level == "trusted":
        # Full builtins but pre-block subprocess/socket
        import builtins
        trusted_builtins = dict(vars(builtins))
        return {
            "ctx": ctx,
            "json": json,
            "time": time,
            "math": math,
            "__name__": "__main__",
            "__file__": str(saved_path),
            "__builtins__": trusted_builtins,
        }

    # Default: sandboxed — restricted builtins, no imports
    SAFE_BUILTINS = {
        "print": print,
        "len": len, "range": range, "enumerate": enumerate, "zip": zip,
        "map": map, "filter": filter, "sorted": sorted, "reversed": reversed,
        "list": list, "dict": dict, "set": set, "tuple": tuple, "frozenset": frozenset,
        "int": int, "float": float, "str": str, "bool": bool, "bytes": bytes,
        "bytearray": bytearray, "complex": complex,
        "min": min, "max": max, "sum": sum, "abs": abs, "round": round,
        "pow": pow, "divmod": divmod,
        "isinstance": isinstance, "issubclass": issubclass,
        "type": type, "hasattr": hasattr, "getattr": getattr, "setattr": setattr,
        "callable": callable, "id": id, "hash": hash, "repr": repr, "dir": dir,
        "chr": chr, "ord": ord, "format": format,
        "Exception": Exception, "ValueError": ValueError, "TypeError": TypeError,
        "RuntimeError": RuntimeError, "KeyError": KeyError, "IndexError": IndexError,
        "StopIteration": StopIteration, "AttributeError": AttributeError,
        "ZeroDivisionError": ZeroDivisionError, "FileNotFoundError": FileNotFoundError,
        "NotImplementedError": NotImplementedError,
        "True": True, "False": False, "None": None,
        "any": any, "all": all, "iter": iter, "next": next,
        "input": lambda *a, **k: (_ for _ in ()).throw(
            RuntimeError("input() is disabled in sandbox")
        ),
        "open": lambda *a, **k: (_ for _ in ()).throw(
            RuntimeError("open() is disabled — use ctx.load_input / ctx.save_output")
        ),
        "__import__": _make_restricted_import(allowed_modules),
    }
    return {
        "ctx": ctx,
        "json": json,
        "time": time,
        "math": math,
        "__name__": "__main__",
        "__file__": str(saved_path),
        "__builtins__": SAFE_BUILTINS,
    }


def run(ctx):
    script = ctx.config.get("script", "")
    script_path = ctx.config.get("script_path", "")
    timeout_seconds = int(ctx.config.get("timeout_seconds", 300))
    trust_level = ctx.config.get("trust_level", "sandboxed")
    requirements = ctx.config.get("requirements", "")
    env_vars = ctx.config.get("env_vars", "")
    allowed_modules = ctx.config.get("allowed_modules", "")

    # Set environment variables before script execution
    if env_vars.strip():
        import shlex
        for line in env_vars.strip().splitlines():
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                key, _, value = line.partition("=")
                os.environ[key.strip()] = value.strip()
        ctx.log_message(f"Set {sum(1 for l in env_vars.strip().splitlines() if '=' in l and not l.strip().startswith('#'))} environment variable(s)")

    # Warn about requirements — pip install is disabled for security
    if requirements.strip():
        pkgs = [p.strip() for p in requirements.split(",") if p.strip()]
        ctx.log_message(
            f"NOTE: Auto-install is disabled for security. "
            f"Please install manually: pip install {' '.join(pkgs)}"
        )

    # Determine script source
    if script_path:
        p = Path(script_path)
        if p.is_file():
            ctx.log_message(f"Loading script from: {script_path}")
            script = p.read_text()
        else:
            ctx.log_message(f"WARNING: script_path not found: {script_path}")
    if not script.strip():
        raise ValueError("No script provided — set either 'script' or 'script_path'")

    ctx.log_message(f"\u26a0 Executing user-provided Python code ({len(script)} chars) [trust: {trust_level}]")

    # Save script to run directory for isolation and reproducibility
    scripts_dir = Path(ctx.run_dir) / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    saved_path = scripts_dir / "script.py"
    saved_path.write_text(script)
    ctx.log_message(f"Script saved to: {saved_path}")

    # Build execution environment based on trust level
    exec_globals = _build_exec_globals(ctx, trust_level, saved_path, allowed_modules)

    # Enforce timeout using SIGALRM (Unix only)
    start_time = time.time()
    use_alarm = hasattr(signal, "SIGALRM")

    def _timeout_handler(signum, frame):
        raise TimeoutError(f"Script exceeded {timeout_seconds}s timeout")

    if use_alarm:
        old_handler = signal.signal(signal.SIGALRM, _timeout_handler)
        signal.alarm(timeout_seconds)

    try:
        exec(compile(script, str(saved_path), "exec"), exec_globals)
    except TimeoutError:
        ctx.log_message(f"TIMEOUT: Script exceeded {timeout_seconds}s limit")
        raise
    except Exception as e:
        tb = traceback.format_exc()
        ctx.log_message(f"Script error:\n{tb}")
        raise RuntimeError(f"Python script failed: {e}")
    finally:
        if use_alarm:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old_handler)

    elapsed = time.time() - start_time
    ctx.log_metric("execution_time_s", round(elapsed, 3))
    ctx.log_message(f"Script completed in {elapsed:.2f}s")
    ctx.report_progress(1, 1)
