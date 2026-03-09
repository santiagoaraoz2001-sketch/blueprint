"""Tool Registry — register callable tools that agents can use."""

import json
import os
import time


def run(ctx):
    tools_config_str = ctx.config.get("tools", "[]")
    include_defaults = ctx.config.get("include_defaults", True)
    output_format = ctx.config.get("output_format", "openai")

    # Coerce include_defaults from various representations
    if isinstance(include_defaults, str):
        include_defaults = include_defaults.lower() in ("true", "1", "yes")

    ctx.log_message("Tool Registry: building tool catalog")

    # ── Parse custom tools from config ──────────────────────────────────
    custom_tools = []
    if isinstance(tools_config_str, str) and tools_config_str.strip():
        try:
            parsed = json.loads(tools_config_str)
            if isinstance(parsed, dict):
                custom_tools = [parsed]
            elif isinstance(parsed, list):
                custom_tools = parsed
        except json.JSONDecodeError:
            ctx.log_message("Warning: could not parse tools JSON config. Skipping custom tools.")

    # ── Load external definitions from input port ───────────────────────
    try:
        ext_data = ctx.load_input("definitions")
        if isinstance(ext_data, dict):
            if "tools" in ext_data:
                custom_tools.extend(ext_data["tools"])
            else:
                custom_tools.append(ext_data)
        elif isinstance(ext_data, list):
            custom_tools.extend(ext_data)
        elif isinstance(ext_data, str):
            if os.path.isfile(ext_data):
                with open(ext_data, "r") as f:
                    loaded = json.load(f)
                if isinstance(loaded, list):
                    custom_tools.extend(loaded)
                elif isinstance(loaded, dict) and "tools" in loaded:
                    custom_tools.extend(loaded["tools"])
            else:
                try:
                    parsed = json.loads(ext_data)
                    if isinstance(parsed, list):
                        custom_tools.extend(parsed)
                except json.JSONDecodeError:
                    pass
    except (ValueError, Exception):
        pass

    # ── Built-in tool definitions ───────────────────────────────────────
    default_tools = [
        {
            "name": "calculator",
            "description": "Perform mathematical calculations. Supports basic arithmetic and common functions.",
            "parameters": {
                "expression": {
                    "type": "string",
                    "description": "Mathematical expression to evaluate",
                },
            },
        },
        {
            "name": "web_search",
            "description": "Search the web for information. Returns relevant snippets.",
            "parameters": {
                "query": {"type": "string", "description": "Search query"},
                "num_results": {
                    "type": "integer",
                    "description": "Number of results to return",
                    "default": 5,
                },
            },
        },
        {
            "name": "text_length",
            "description": "Count characters, words, and lines in text.",
            "parameters": {
                "text": {"type": "string", "description": "Text to analyze"},
            },
        },
        {
            "name": "json_parser",
            "description": "Parse JSON string and extract specific fields.",
            "parameters": {
                "json_string": {"type": "string", "description": "JSON string to parse"},
                "field": {
                    "type": "string",
                    "description": "Dot-notated field path to extract",
                    "default": "",
                },
            },
        },
        {
            "name": "datetime_tool",
            "description": "Get current date/time or format timestamps.",
            "parameters": {
                "format": {
                    "type": "string",
                    "description": "strftime format string",
                    "default": "%Y-%m-%d %H:%M:%S",
                },
            },
        },
        {
            "name": "string_transform",
            "description": "Transform text: uppercase, lowercase, reverse, title case, word count.",
            "parameters": {
                "text": {"type": "string", "description": "Input text"},
                "operation": {
                    "type": "string",
                    "description": "Operation: upper, lower, reverse, title, word_count",
                },
            },
        },
    ]

    # ── Combine tools ───────────────────────────────────────────────────
    all_tools = []
    if include_defaults:
        all_tools.extend(default_tools)
    all_tools.extend(custom_tools)

    # Deduplicate by name (last definition wins)
    seen = {}
    for tool in all_tools:
        name = tool.get("name", f"unnamed_{len(seen)}")
        tool["name"] = name
        seen[name] = tool
    all_tools = list(seen.values())

    # ── Generate function-calling schemas ───────────────────────────────
    function_schemas = []
    for tool in all_tools:
        params = tool.get("parameters", {})
        required_params = [
            k for k, v in params.items() if "default" not in v
        ]

        if output_format == "openai":
            schema = {
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool.get("description", ""),
                    "parameters": {
                        "type": "object",
                        "properties": params,
                        "required": required_params,
                    },
                },
            }
        elif output_format == "anthropic":
            schema = {
                "name": tool["name"],
                "description": tool.get("description", ""),
                "input_schema": {
                    "type": "object",
                    "properties": params,
                    "required": required_params,
                },
            }
        else:  # generic
            schema = {
                "name": tool["name"],
                "description": tool.get("description", ""),
                "parameters": params,
                "required": required_params,
            }
        function_schemas.append(schema)

    ctx.log_message(f"Registered {len(all_tools)} tools (format={output_format}):")
    for tool in all_tools:
        ctx.log_message(f"  - {tool['name']}: {tool.get('description', '')[:60]}")

    # ── Build registry output ───────────────────────────────────────────
    registry = {
        "tools": all_tools,
        "function_schemas": function_schemas,
        "count": len(all_tools),
        "format": output_format,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }

    # Save to disk
    out_dir = os.path.join(ctx.run_dir, "registry")
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "tools.json"), "w") as f:
        json.dump(registry, f, indent=2)

    ctx.save_output("tools", registry)

    metrics = {
        "num_tools": len(all_tools),
        "num_default": len(default_tools) if include_defaults else 0,
        "num_custom": len(custom_tools),
        "output_format": output_format,
    }
    ctx.save_output("metrics", metrics)
    ctx.log_metric("num_tools", len(all_tools))

    ctx.log_message(f"Tool registry ready: {len(all_tools)} tools")
    ctx.report_progress(1, 1)
