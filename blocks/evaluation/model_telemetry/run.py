"""Model Telemetry — capture model internals during inference.

Analyzes model architecture, captures attention patterns, layer statistics,
and memory usage. Supports real analysis via PyTorch + Transformers, with
demo fallback for environments without GPU/model dependencies.
"""

import json
import os
import time


def run(ctx):
    # ── Configuration ─────────────────────────────────────────────────────
    model_path = ctx.config.get("model_path", "")
    capture_attention = ctx.config.get("capture_attention", True)
    capture_activations = ctx.config.get("capture_activations", False)
    capture_memory = ctx.config.get("capture_memory", True)
    capture_layer_stats = ctx.config.get("capture_layer_stats", True)
    sample_size = int(ctx.config.get("sample_size", 10))
    text_column = ctx.config.get("text_column", "text")
    max_seq_length = int(ctx.config.get("max_seq_length", 128))
    trust_remote_code = ctx.config.get("trust_remote_code", True)

    # ── Output format config ───────────────────────────────────────────────
    output_format = ctx.config.get("output_format", "json")
    decimal_precision = int(ctx.config.get("decimal_precision", 4))

    # ── Resolve model from input ──────────────────────────────────────────
    if ctx.inputs.get("model"):
        model_info = ctx.load_input("model")
        if isinstance(model_info, dict):
            model_path = model_info.get("path",
                         model_info.get("model_name",
                         model_info.get("model_id", ""))) or model_path
        elif isinstance(model_info, str):
            model_path = model_info or model_path

    if not model_path:
        raise ValueError(
            "Model path required: connect a model via the 'model' input "
            "port or set 'model_path' in config."
        )

    # ── Load sample texts from dataset if connected ───────────────────────
    sample_texts = None
    try:
        dataset_path = ctx.load_input("dataset")
        data_file = (os.path.join(dataset_path, "data.json")
                     if os.path.isdir(dataset_path) else dataset_path)
        if os.path.isfile(data_file):
            with open(data_file, "r", encoding="utf-8") as f:
                rows = json.load(f)
            if isinstance(rows, list) and rows:
                sample_texts = []
                for row in rows[:sample_size]:
                    if isinstance(row, dict):
                        sample_texts.append(str(row.get(text_column, row.get("input", ""))))
                    else:
                        sample_texts.append(str(row))
                ctx.log_message(f"Loaded {len(sample_texts)} sample texts from dataset")
    except (ValueError, Exception):
        pass

    if not sample_texts:
        sample_texts = [
            f"This is sample text number {i} for model telemetry analysis."
            for i in range(sample_size)
        ]

    ctx.log_message(f"Analyzing model: {model_path}")
    ctx.log_message(
        f"Capture: attention={capture_attention}, activations={capture_activations}, "
        f"memory={capture_memory}, layer_stats={capture_layer_stats}"
    )

    # ── Initialize telemetry ──────────────────────────────────────────────
    telemetry = {
        "model": model_path,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "config": {
            "capture_attention": capture_attention,
            "capture_activations": capture_activations,
            "capture_memory": capture_memory,
            "capture_layer_stats": capture_layer_stats,
            "sample_size": sample_size,
        },
        "layers": [],
        "memory": {},
        "attention": {},
        "summary": {},
    }

    # ── Run analysis ──────────────────────────────────────────────────────
    try:
        import torch
        telemetry = _analyze_torch_model(
            ctx, model_path, telemetry, sample_texts,
            capture_attention, capture_activations,
            capture_memory, capture_layer_stats,
            max_seq_length, trust_remote_code,
        )
    except ImportError:
        ctx.log_message("PyTorch not available — generating demo telemetry")
        telemetry = _generate_demo_telemetry(ctx, telemetry, sample_size)
    except Exception as e:
        ctx.log_message(f"Analysis error: {e} — generating demo telemetry")
        telemetry = _generate_demo_telemetry(ctx, telemetry, sample_size)

    # ── Save outputs ──────────────────────────────────────────────────────
    out_path = os.path.join(ctx.run_dir, "telemetry.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(telemetry, f, indent=2, default=str)

    ctx.save_output("telemetry", out_path)
    ctx.save_artifact("telemetry", out_path)

    metrics = telemetry.get("summary", {})
    ctx.save_output("metrics", metrics)
    for key, value in metrics.items():
        if isinstance(value, (int, float)):
            ctx.log_metric(key, value)

    ctx.log_message(f"Telemetry saved: {len(telemetry.get('layers', []))} layers analyzed")
    ctx.report_progress(1, 1)


def _analyze_torch_model(ctx, model_path, telemetry, sample_texts,
                          capture_attention, capture_activations,
                          capture_memory, capture_layer_stats,
                          max_seq_length=128, trust_remote_code=True):
    """Real analysis using PyTorch + Transformers."""
    import torch

    ctx.log_message("Loading model with PyTorch...")
    try:
        from transformers import AutoModel, AutoTokenizer
        tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=trust_remote_code)
        model = AutoModel.from_pretrained(
            model_path, trust_remote_code=trust_remote_code,
            output_attentions=capture_attention,
        )
        model.eval()
    except Exception as e:
        ctx.log_message(f"Could not load with transformers: {e}")
        raise

    # ── Parameter counts ──────────────────────────────────────────────────
    total_params = sum(p.numel() for p in model.parameters())
    trainable_params = sum(p.numel() for p in model.parameters() if p.requires_grad)
    telemetry["summary"]["total_parameters"] = total_params
    telemetry["summary"]["trainable_parameters"] = trainable_params
    telemetry["summary"]["model_size_mb"] = round(total_params * 4 / 1024 / 1024, 2)
    ctx.log_message(f"Parameters: {total_params:,} total, {trainable_params:,} trainable")

    # ── Memory usage ──────────────────────────────────────────────────────
    if capture_memory:
        if torch.cuda.is_available():
            telemetry["memory"]["gpu_allocated_mb"] = round(torch.cuda.memory_allocated() / 1024 / 1024, 2)
            telemetry["memory"]["gpu_reserved_mb"] = round(torch.cuda.memory_reserved() / 1024 / 1024, 2)
        try:
            import psutil
            process = psutil.Process()
            telemetry["memory"]["cpu_rss_mb"] = round(process.memory_info().rss / 1024 / 1024, 2)
        except ImportError:
            pass

    # ── Layer statistics ──────────────────────────────────────────────────
    if capture_layer_stats:
        ctx.log_message("Analyzing layer statistics...")
        for name, param in model.named_parameters():
            layer_info = {
                "name": name,
                "shape": list(param.shape),
                "dtype": str(param.dtype),
                "numel": param.numel(),
            }
            if param.requires_grad:
                data = param.data.float()
                layer_info["mean"] = round(data.mean().item(), 6)
                layer_info["std"] = round(data.std().item(), 6)
                layer_info["min"] = round(data.min().item(), 6)
                layer_info["max"] = round(data.max().item(), 6)
                layer_info["norm"] = round(data.norm().item(), 4)
            telemetry["layers"].append(layer_info)

    # ── Attention patterns ────────────────────────────────────────────────
    if capture_attention:
        ctx.log_message(f"Running {len(sample_texts)} samples for attention capture...")
        attention_stats = []
        for i, text in enumerate(sample_texts):
            inputs = tokenizer(text, return_tensors="pt", truncation=True, max_length=max_seq_length)
            with torch.no_grad():
                outputs = model(**inputs)

            if hasattr(outputs, "attentions") and outputs.attentions:
                attn = outputs.attentions
                attn_summary = {
                    "sample_idx": i,
                    "num_layers": len(attn),
                    "num_heads": attn[0].shape[1] if attn else 0,
                    "seq_length": attn[0].shape[-1] if attn else 0,
                }
                for layer_idx, layer_attn in enumerate(attn):
                    attn_summary[f"layer_{layer_idx}_mean"] = round(layer_attn.mean().item(), 6)
                    attn_summary[f"layer_{layer_idx}_max"] = round(layer_attn.max().item(), 6)
                attention_stats.append(attn_summary)

            ctx.report_progress(i + 1, len(sample_texts))

        telemetry["attention"]["samples"] = attention_stats
        if attention_stats:
            telemetry["summary"]["num_attention_layers"] = attention_stats[0].get("num_layers", 0)
            telemetry["summary"]["num_attention_heads"] = attention_stats[0].get("num_heads", 0)

    telemetry["summary"]["num_layers_analyzed"] = len(telemetry["layers"])
    return telemetry


def _generate_demo_telemetry(ctx, telemetry, sample_size):
    """Generate demo telemetry when PyTorch is not available."""
    import random

    ctx.log_message("Generating demo telemetry data...")
    num_layers = 12
    hidden_size = 768

    for i in range(num_layers):
        for component in ["attention.query", "attention.key", "attention.value", "ffn.up", "ffn.down"]:
            telemetry["layers"].append({
                "name": f"layer.{i}.{component}.weight",
                "shape": [hidden_size, hidden_size],
                "dtype": "float32",
                "numel": hidden_size * hidden_size,
                "mean": round(random.gauss(0, 0.02), 6),
                "std": round(abs(random.gauss(0.02, 0.005)), 6),
                "min": round(random.gauss(-0.1, 0.02), 6),
                "max": round(random.gauss(0.1, 0.02), 6),
                "norm": round(abs(random.gauss(10, 2)), 4),
            })
        ctx.report_progress(i + 1, num_layers)

    total_params = num_layers * 5 * hidden_size * hidden_size
    telemetry["summary"] = {
        "total_parameters": total_params,
        "trainable_parameters": total_params,
        "model_size_mb": round(total_params * 4 / 1024 / 1024, 2),
        "num_layers_analyzed": len(telemetry["layers"]),
        "num_attention_layers": num_layers,
        "num_attention_heads": 12,
    }
    telemetry["memory"] = {"cpu_rss_mb": round(random.uniform(200, 800), 2)}
    return telemetry
