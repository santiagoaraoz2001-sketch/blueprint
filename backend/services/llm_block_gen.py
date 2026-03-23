"""LLM-assisted block generation service.

Constructs prompts from the Block Author's Cookbook (docs/BLOCK_LLM_PROMPT.md),
calls a local LLM (Ollama or MLX), parses the response into block.yaml + run.py,
and validates the result.
"""

import ast
import json
import logging
import random
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import yaml

from ..config import OLLAMA_URL, MLX_URL, BUILTIN_BLOCKS_DIR

logger = logging.getLogger("blueprint.block_gen")

# Path to the prompt template created in A4
_PROMPT_TEMPLATE_PATH = Path(__file__).parent.parent.parent / "docs" / "BLOCK_LLM_PROMPT.md"

# Valid block categories
VALID_CATEGORIES = [
    "data", "inference", "training", "evaluation",
    "flow", "agents", "endpoints", "merge", "output",
]

# Keywords for auto-detecting category from description
_CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "data": ["data", "csv", "json", "load", "parse", "transform", "clean", "filter", "column", "row", "text", "normalize", "format", "convert", "split", "merge data"],
    "inference": ["inference", "llm", "chat", "generate", "predict", "completion", "prompt", "model", "embed"],
    "training": ["train", "finetune", "fine-tune", "lora", "qlora", "dpo", "rlhf", "loss", "optimizer", "epoch"],
    "evaluation": ["eval", "score", "metric", "benchmark", "accuracy", "bleu", "rouge", "compare", "assess"],
    "flow": ["loop", "branch", "condition", "if", "switch", "retry", "parallel", "gate", "control"],
    "agents": ["agent", "tool", "react", "chain", "orchestrat"],
    "endpoints": ["save", "export", "output", "write", "upload", "deploy", "serve", "api"],
    "merge": ["merge", "combine", "ensemble", "blend", "mix"],
    "output": ["display", "print", "log", "visuali", "chart", "plot", "report"],
}


def _detect_category(description: str) -> str:
    """Auto-detect block category from description using keyword matching."""
    desc_lower = description.lower()
    scores: dict[str, int] = {}
    for cat, keywords in _CATEGORY_KEYWORDS.items():
        scores[cat] = sum(1 for kw in keywords if kw in desc_lower)
    best = max(scores, key=lambda k: scores[k])
    return best if scores[best] > 0 else "data"


def _load_prompt_template() -> str:
    """Load the BLOCK_LLM_PROMPT.md template."""
    if not _PROMPT_TEMPLATE_PATH.exists():
        raise FileNotFoundError(f"Block prompt template not found at {_PROMPT_TEMPLATE_PATH}")
    return _PROMPT_TEMPLATE_PATH.read_text(encoding="utf-8")


def _select_example_blocks(category: str, count: int = 2) -> str:
    """Select example blocks from the blocks/ directory matching the category.

    Only considers blocks that have both block.yaml and run.py files.
    Falls back to the data category if the requested category has no valid blocks.
    """
    cat_dir = BUILTIN_BLOCKS_DIR / category
    if not cat_dir.exists() or not cat_dir.is_dir():
        cat_dir = BUILTIN_BLOCKS_DIR / "data"
    if not cat_dir.exists():
        return ""

    # Filter to blocks that have both required files before sampling
    valid_blocks = [
        d for d in sorted(cat_dir.iterdir())
        if d.is_dir()
        and not d.name.startswith((".", "_"))
        and (d / "block.yaml").exists()
        and (d / "run.py").exists()
    ]
    if not valid_blocks:
        return ""

    chosen = random.sample(valid_blocks, min(count, len(valid_blocks)))
    examples: list[str] = []

    for block_dir in chosen:
        try:
            yaml_content = (block_dir / "block.yaml").read_text(encoding="utf-8")
            run_content = (block_dir / "run.py").read_text(encoding="utf-8")
        except OSError:
            continue

        # Truncate very long run.py files
        if len(run_content) > 3000:
            run_content = run_content[:3000] + "\n# ... (truncated for brevity)\n"

        examples.append(
            f"\n### Additional Example: `blocks/{category}/{block_dir.name}/block.yaml`\n\n"
            f"```yaml\n{yaml_content}```\n\n"
            f"**`blocks/{category}/{block_dir.name}/run.py`:**\n\n"
            f"```python\n{run_content}```\n"
        )

    return "\n".join(examples)


def _build_prompt(description: str, category: str, name: str | None) -> str:
    """Build the full LLM prompt from template + user description + examples."""
    template = _load_prompt_template()

    # Replace the placeholder with user description
    user_section = f"**Description:** {description}\n"
    if name:
        user_section += f"**Name:** {name}\n"
    user_section += f"**Category:** {category}\n"

    prompt = template.replace(
        "[USER: DESCRIBE YOUR BLOCK REQUIREMENTS HERE]",
        user_section,
    )

    # Add extra examples from the matching category
    extra_examples = _select_example_blocks(category)
    if extra_examples:
        prompt += f"\n\n## Additional Reference Examples\n{extra_examples}"

    prompt += (
        "\n\n## Output Format\n\n"
        "Return EXACTLY two fenced code blocks:\n"
        "1. A ```yaml block containing the complete block.yaml\n"
        "2. A ```python block containing the complete run.py\n\n"
        "Do not include any other text or explanation outside these two code blocks."
    )

    return prompt


# Patterns for preferring code-capable models (checked against lowercased model names)
_CODE_MODEL_PATTERNS = ["code", "deepseek", "qwen2.5-coder", "codellama", "starcoder"]


def _pick_best_model(models: list[str]) -> str:
    """Pick the best available model for code generation.

    Prefers models with code-related names; otherwise picks the first available.
    """
    if not models:
        return ""

    # Prefer code-capable models
    for model_name in models:
        name_lower = model_name.lower()
        if any(p in name_lower for p in _CODE_MODEL_PATTERNS):
            return model_name

    # Fall back to the first available model
    return models[0]


def _call_ollama(prompt: str) -> str | None:
    """Call Ollama for non-streaming generation. Returns response text or None."""
    # Discover available models first
    try:
        tags_req = urllib.request.Request(f"{OLLAMA_URL}/api/tags", method="GET")
        with urllib.request.urlopen(tags_req, timeout=5) as resp:
            body = json.loads(resp.read().decode())
            models = [m.get("name", "") for m in body.get("models", []) if m.get("name")]
    except Exception:
        logger.debug("Ollama not reachable for model discovery")
        return None

    if not models:
        logger.warning("Ollama running but no models available")
        return None

    model = _pick_best_model(models)
    logger.info("Using Ollama model: %s", model)

    # Build and send the chat request
    payload = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": "You are a code generator. Generate only the requested code blocks with no additional commentary."},
            {"role": "user", "content": prompt},
        ],
        "stream": False,
        "options": {"temperature": 0.3, "num_predict": 4096},
    }).encode("utf-8")

    try:
        req = urllib.request.Request(
            f"{OLLAMA_URL}/api/chat",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=300) as resp:
            result = json.loads(resp.read().decode("utf-8", errors="ignore"))
            return result.get("message", {}).get("content", "")

    except urllib.error.URLError as e:
        logger.debug("Ollama chat request failed: %s", e)
        return None
    except Exception as e:
        logger.warning("Ollama call failed: %s", e)
        return None


def _call_mlx(prompt: str) -> str | None:
    """Call MLX server for non-streaming generation. Returns response text or None."""
    try:
        payload = json.dumps({
            "messages": [
                {"role": "system", "content": "You are a code generator. Generate only the requested code blocks with no additional commentary."},
                {"role": "user", "content": prompt},
            ],
            "stream": False,
            "temperature": 0.3,
            "max_tokens": 4096,
        }).encode("utf-8")

        req = urllib.request.Request(
            f"{MLX_URL}/v1/chat/completions",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=300) as resp:
            result = json.loads(resp.read().decode("utf-8", errors="ignore"))
            choices = result.get("choices", [])
            if choices:
                return choices[0].get("message", {}).get("content", "")
            return None

    except urllib.error.URLError as e:
        logger.debug("MLX server not reachable: %s", e)
        return None
    except Exception as e:
        logger.warning("MLX call failed: %s", e)
        return None


def _parse_llm_response(response: str) -> tuple[str, str]:
    """Extract block.yaml and run.py from LLM response fenced code blocks.

    Returns (yaml_content, python_content). Raises ValueError on parse failure.
    """
    # Extract YAML block
    yaml_match = re.search(r"```ya?ml\s*\n(.*?)```", response, re.DOTALL)
    if not yaml_match:
        raise ValueError("Could not find ```yaml code block in LLM response")
    yaml_content = yaml_match.group(1).strip()

    # Extract Python block
    py_match = re.search(r"```python\s*\n(.*?)```", response, re.DOTALL)
    if not py_match:
        raise ValueError("Could not find ```python code block in LLM response")
    py_content = py_match.group(1).strip()

    return yaml_content, py_content


def _validate_block(yaml_content: str, py_content: str) -> dict[str, Any]:
    """Validate generated block.yaml and run.py.

    Returns validation dict with yaml_valid, py_syntax_valid, has_run_function,
    outputs_match, errors, warnings.
    """
    errors: list[str] = []
    warnings: list[str] = []
    yaml_valid = False
    py_syntax_valid = False
    has_run_function = False
    outputs_match = False

    # 1. Validate YAML
    parsed_yaml: dict = {}
    try:
        parsed_yaml = yaml.safe_load(yaml_content) or {}
        yaml_valid = True
    except yaml.YAMLError as e:
        errors.append(f"YAML parse error: {e}")

    if yaml_valid:
        required_fields = ["name", "type", "category", "description", "version", "inputs", "outputs"]
        for field in required_fields:
            if field not in parsed_yaml:
                errors.append(f"Missing required field in block.yaml: '{field}'")
                yaml_valid = False

        # Validate category
        cat = parsed_yaml.get("category", "")
        if cat and cat not in VALID_CATEGORIES:
            warnings.append(f"Category '{cat}' not in standard list: {VALID_CATEGORIES}")

    # 2. Validate Python syntax
    tree = None
    try:
        tree = ast.parse(py_content)
        py_syntax_valid = True
    except SyntaxError as e:
        errors.append(f"Python syntax error at line {e.lineno}: {e.msg}")

    # 3. Check for run() function
    if tree:
        run_func = next(
            (node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == "run"),
            None,
        )
        if run_func:
            has_run_function = True
            # Check signature
            total_args = len(run_func.args.posonlyargs) + len(run_func.args.args)
            if total_args == 0:
                errors.append("`run()` must accept at least one argument (ctx)")
            elif total_args > 2:
                warnings.append(f"`run()` has {total_args} args — expected 1 (ctx)")
        else:
            errors.append("Missing required `run(ctx)` function in run.py")

    # 4. Check outputs match
    if yaml_valid and tree:
        declared_outputs = {o["id"] for o in parsed_yaml.get("outputs", []) if isinstance(o, dict) and "id" in o}

        # Find ctx.save_output("port_id", ...) calls in the AST
        saved_outputs: set[str] = set()
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "save_output"
                    and node.args
                    and isinstance(node.args[0], ast.Constant)
                    and isinstance(node.args[0].value, str)):
                saved_outputs.add(node.args[0].value)

        if declared_outputs and declared_outputs == saved_outputs:
            outputs_match = True
        elif declared_outputs and not saved_outputs:
            warnings.append(f"Declared outputs {declared_outputs} but no ctx.save_output() calls found")
        elif declared_outputs != saved_outputs:
            missing = declared_outputs - saved_outputs
            extra = saved_outputs - declared_outputs
            if missing:
                warnings.append(f"Declared outputs not saved: {missing}")
            if extra:
                warnings.append(f"save_output() called for undeclared ports: {extra}")
            # Partial match is still acceptable
            outputs_match = len(missing) == 0

    return {
        "yaml_valid": yaml_valid,
        "py_syntax_valid": py_syntax_valid,
        "has_run_function": has_run_function,
        "outputs_match": outputs_match,
        "errors": errors,
        "warnings": warnings,
    }


MAX_DESCRIPTION_LENGTH = 2000


def generate_block(description: str, category: str | None = None, name: str | None = None) -> dict[str, Any]:
    """Generate a block from a natural language description using a local LLM.

    Args:
        description: Natural language description of the desired block.
        category: Optional block category. Auto-detected if omitted.
        name: Optional human-readable name for the block.

    Returns:
        Dict with block_yaml, run_py, block_type, validation, and error fields.
    """
    description = description.strip()
    if not description:
        return {"error": "Description is required"}
    if len(description) > MAX_DESCRIPTION_LENGTH:
        return {"error": f"Description too long ({len(description)} chars). Maximum is {MAX_DESCRIPTION_LENGTH}."}

    # Auto-detect category if not provided
    if not category or category not in VALID_CATEGORIES:
        category = _detect_category(description)

    # Build prompt
    try:
        prompt = _build_prompt(description, category, name)
    except FileNotFoundError as e:
        return {"error": str(e)}

    # Try LLM backends
    response = _call_ollama(prompt)
    if response is None:
        response = _call_mlx(prompt)
    if response is None:
        return {
            "error": "No LLM backend available. Start Ollama to use Block Generator.\n\n"
                     "Install: https://ollama.com\n"
                     "Then run: ollama pull <model> && ollama serve"
        }

    # Parse response
    try:
        yaml_content, py_content = _parse_llm_response(response)
    except ValueError as e:
        return {
            "error": f"Failed to parse LLM response: {e}",
            "raw_response": response,
        }

    # Extract block_type from YAML
    try:
        parsed = yaml.safe_load(yaml_content) or {}
        block_type = parsed.get("type", "")
    except yaml.YAMLError:
        block_type = ""

    if not block_type and name:
        block_type = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")

    # Validate
    validation = _validate_block(yaml_content, py_content)

    return {
        "block_yaml": yaml_content,
        "run_py": py_content,
        "block_type": block_type,
        "category": category,
        "validation": validation,
    }
