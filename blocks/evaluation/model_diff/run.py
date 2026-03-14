"""Model Diff — compare two models on the same prompt.

Loads two models, runs the same prompt through both, and compares:
  - Top-K token probabilities at each generated position
  - KL divergence between output distributions
  - Cosine similarity of hidden states (optional layer-by-layer)

Supports transformers (PyTorch), MLX, and Ollama models.
For Ollama models, only token-level text comparison is available (no logits).
"""

import json
import math
import os


def run(ctx):
    # -- Configuration ---------------------------------------------------------
    prompt = ctx.config.get("prompt", "The capital of France is")
    max_tokens = int(ctx.config.get("max_tokens", 50))
    top_k = int(ctx.config.get("top_k", 5))
    compare_layers = ctx.config.get("compare_layers", False)
    if isinstance(compare_layers, str):
        compare_layers = compare_layers.lower() in ("true", "1", "yes")
    model_a_override = ctx.config.get("model_a_name", "")
    model_b_override = ctx.config.get("model_b_name", "")
    output_format = ctx.config.get("output_format", "json")
    decimal_precision = int(ctx.config.get("decimal_precision", 4))

    if not prompt or not prompt.strip():
        raise ValueError("Test prompt cannot be empty")

    # -- Resolve model info ----------------------------------------------------
    model_a_info = _resolve_model(ctx, "model_a", model_a_override, "gpt2")
    model_b_info = _resolve_model(ctx, "model_b", model_b_override, "gpt2")

    model_a_name = model_a_info["name"]
    model_b_name = model_b_info["name"]
    ctx.log_message(f"Model A: {model_a_name}")
    ctx.log_message(f"Model B: {model_b_name}")
    ctx.log_message(f"Prompt: {prompt[:80]}{'...' if len(prompt) > 80 else ''}")

    # -- Determine comparison strategy -----------------------------------------
    a_is_local = model_a_info["framework"] in ("pytorch", "mlx")
    b_is_local = model_b_info["framework"] in ("pytorch", "mlx")

    if a_is_local and b_is_local:
        ctx.log_message("Using local model comparison (full logits + hidden states)")
        report = _compare_local_models(
            ctx, model_a_info, model_b_info, prompt, max_tokens, top_k,
            compare_layers, decimal_precision,
        )
    else:
        ctx.log_message("One or both models are remote — using text-based comparison")
        report = _compare_via_inference(
            ctx, model_a_info, model_b_info, prompt, max_tokens, top_k,
            decimal_precision,
        )

    # -- Build final report ----------------------------------------------------
    report["prompt"] = prompt
    report["model_a"] = model_a_name
    report["model_b"] = model_b_name

    overall_kl = report.get("overall_kl_divergence", 0.0)
    agreement = report.get("top1_agreement_rate", 1.0)
    cosine_sim = report.get("cosine_similarity_mean", 0.0)

    # -- Emit metrics ----------------------------------------------------------
    metrics = {
        "kl_divergence": round(overall_kl, decimal_precision),
        "cosine_similarity": round(cosine_sim, decimal_precision),
        "top1_agreement_rate": round(agreement, decimal_precision),
        "num_positions": len(report.get("tokens", [])),
    }
    for k, v in metrics.items():
        ctx.log_metric(k, v)

    ctx.log_message(f"\nResults:")
    ctx.log_message(f"  KL divergence:      {overall_kl:.{decimal_precision}f}")
    ctx.log_message(f"  Top-1 agreement:    {agreement:.1%}")
    ctx.log_message(f"  Cosine similarity:  {cosine_sim:.{decimal_precision}f}")

    # -- Save outputs ----------------------------------------------------------
    out_dir = os.path.join(ctx.run_dir, "dataset")
    os.makedirs(out_dir, exist_ok=True)

    # Round all floats in report
    _round_report(report, decimal_precision)

    # Save token comparisons as dataset
    token_rows = []
    for tok in report.get("tokens", []):
        a_top5 = tok.get("model_a_top5", [])
        b_top5 = tok.get("model_b_top5", [])
        row = {
            "position": tok["position"],
            "model_a_top1": a_top5[0][0] if a_top5 else "",
            "model_a_top1_prob": a_top5[0][1] if a_top5 else 0,
            "model_b_top1": b_top5[0][0] if b_top5 else "",
            "model_b_top1_prob": b_top5[0][1] if b_top5 else 0,
            "kl_div": tok.get("kl_div", 0),
            "top1_match": tok.get("top1_match", False),
        }
        token_rows.append(row)

    if output_format == "csv" and token_rows:
        import csv as _csv
        with open(os.path.join(out_dir, "data.csv"), "w", newline="", encoding="utf-8") as f:
            w = _csv.DictWriter(f, fieldnames=token_rows[0].keys())
            w.writeheader()
            w.writerows(token_rows)
    else:
        with open(os.path.join(out_dir, "data.json"), "w", encoding="utf-8") as f:
            json.dump(token_rows, f, indent=2)

    ctx.save_output("dataset", out_dir)

    # Save full diff report as artifact
    report_path = os.path.join(ctx.run_dir, "diff_report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    ctx.save_artifact("diff_report", report_path)
    ctx.save_output("diff_report", report_path)

    ctx.save_output("metrics", metrics)
    ctx.report_progress(1, 1)


# ── Model resolution ─────────────────────────────────────────────────────


def _resolve_model(ctx, port_id, name_override, fallback):
    """Resolve model info from input port or config override."""
    info = {"name": fallback, "framework": "pytorch", "endpoint": "http://localhost:11434"}

    try:
        model_data = ctx.load_input(port_id)
        if isinstance(model_data, dict):
            info["name"] = model_data.get("model_name", model_data.get("model_id", fallback))
            info["endpoint"] = model_data.get("endpoint", model_data.get("base_url", info["endpoint"]))
            source = model_data.get("source", model_data.get("backend", ""))
            if source == "ollama":
                info["framework"] = "ollama"
            elif source == "mlx":
                info["framework"] = "mlx"
            else:
                info["framework"] = "pytorch"
        elif isinstance(model_data, str):
            info["name"] = model_data
    except (ValueError, Exception):
        pass

    if name_override:
        info["name"] = name_override

    # Auto-detect framework for short names (no slash = likely Ollama)
    if "/" not in info["name"] and info["name"] != "gpt2" and info["framework"] == "pytorch":
        try:
            import urllib.request
            req = urllib.request.Request(
                f"{info['endpoint'].rstrip('/')}/api/tags",
                headers={"Accept": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=2) as resp:
                data = json.loads(resp.read().decode())
                available = [m["name"] for m in data.get("models", [])]
                if info["name"] in available or any(info["name"] in m for m in available):
                    info["framework"] = "ollama"
        except Exception:
            pass

    return info


# ── Local model comparison (full logits) ─────────────────────────────────


def _compare_local_models(ctx, model_a_info, model_b_info, prompt, max_tokens,
                          top_k, compare_layers, precision):
    """Compare two local models with full logit and hidden-state access."""
    try:
        from transformers import AutoModelForCausalLM, AutoTokenizer
        import torch
        import torch.nn.functional as F
    except ImportError as e:
        from backend.block_sdk.exceptions import BlockDependencyError
        missing = str(e).split("'")[-2] if "'" in str(e) else str(e)
        raise BlockDependencyError(
            missing,
            f"Required library not installed: {e}",
            install_hint="pip install torch transformers",
        )

    model_a = None
    model_b = None

    try:
        # -- Load models -----------------------------------------------------------
        ctx.log_message("Loading Model A...")
        ctx.report_progress(0, 6)
        try:
            tokenizer_a = AutoTokenizer.from_pretrained(
                model_a_info["name"], trust_remote_code=True,
            )
            model_a = AutoModelForCausalLM.from_pretrained(
                model_a_info["name"], trust_remote_code=True,
                torch_dtype=torch.float16, device_map="auto",
            )
            model_a.eval()
        except Exception as e:
            raise RuntimeError(f"Failed to load Model A ({model_a_info['name']}): {e}")

        ctx.log_message("Loading Model B...")
        ctx.report_progress(1, 6)
        try:
            tokenizer_b = AutoTokenizer.from_pretrained(
                model_b_info["name"], trust_remote_code=True,
            )
            model_b = AutoModelForCausalLM.from_pretrained(
                model_b_info["name"], trust_remote_code=True,
                torch_dtype=torch.float16, device_map="auto",
            )
            model_b.eval()
        except Exception as e:
            raise RuntimeError(f"Failed to load Model B ({model_b_info['name']}): {e}")

        same_tokenizer = (model_a_info["name"] == model_b_info["name"])

        # -- Generate with Model A -------------------------------------------------
        ctx.log_message("Running inference on Model A...")
        ctx.report_progress(2, 6)
        inputs_a = tokenizer_a(prompt, return_tensors="pt").to(model_a.device)

        with torch.no_grad():
            outputs_a = model_a.generate(
                **inputs_a, max_new_tokens=max_tokens,
                do_sample=False, return_dict_in_generate=True,
                output_scores=True, output_hidden_states=compare_layers,
            )

        # -- Generate with Model B -------------------------------------------------
        ctx.log_message("Running inference on Model B...")
        ctx.report_progress(3, 6)
        inputs_b = tokenizer_b(prompt, return_tensors="pt").to(model_b.device)

        with torch.no_grad():
            outputs_b = model_b.generate(
                **inputs_b, max_new_tokens=max_tokens,
                do_sample=False, return_dict_in_generate=True,
                output_scores=True, output_hidden_states=compare_layers,
            )

        # -- Compute token-level differences ---------------------------------------
        ctx.log_message("Computing token probability differences...")
        ctx.report_progress(4, 6)
        scores_a = outputs_a.scores  # tuple of (1, vocab_size) tensors
        scores_b = outputs_b.scores

        if not scores_a or not scores_b:
            ctx.log_message("Warning: one or both models generated no tokens")
            return {
                "tokens": [],
                "overall_kl_divergence": 0.0,
                "top1_agreement_rate": 1.0,
                "cosine_similarity_mean": 1.0 if same_tokenizer else 0.0,
            }

        num_positions = min(len(scores_a), len(scores_b))
        vocab_a = scores_a[0].shape[-1]
        vocab_b = scores_b[0].shape[-1]
        same_vocab = (vocab_a == vocab_b)

        tokens = []
        kl_divs = []
        top1_matches = 0

        for pos in range(num_positions):
            probs_a = F.softmax(scores_a[pos][0].float(), dim=-1)
            probs_b = F.softmax(scores_b[pos][0].float(), dim=-1)

            # Top-K for each model
            actual_k_a = min(top_k, probs_a.shape[0])
            actual_k_b = min(top_k, probs_b.shape[0])
            topk_a = torch.topk(probs_a, actual_k_a)
            topk_b = torch.topk(probs_b, actual_k_b)

            top5_a = [
                [tokenizer_a.decode([idx.item()]).strip(), round(prob.item(), precision)]
                for idx, prob in zip(topk_a.indices, topk_a.values)
            ]
            top5_b = [
                [tokenizer_b.decode([idx.item()]).strip(), round(prob.item(), precision)]
                for idx, prob in zip(topk_b.indices, topk_b.values)
            ]

            # KL divergence: KL(A || B)
            if same_vocab:
                # Same vocab size — direct KL divergence
                log_probs_b = torch.log(probs_b.clamp(min=1e-10))
                kl = F.kl_div(log_probs_b, probs_a, reduction="sum").item()
            else:
                # Different vocab sizes — compute KL over shared token space
                # Use the smaller vocab, pad the larger to match
                min_vocab = min(vocab_a, vocab_b)
                pa = probs_a[:min_vocab]
                pb = probs_b[:min_vocab]
                # Renormalize over the shared portion
                pa = pa / pa.sum().clamp(min=1e-10)
                pb = pb / pb.sum().clamp(min=1e-10)
                log_pb = torch.log(pb.clamp(min=1e-10))
                kl = F.kl_div(log_pb, pa, reduction="sum").item()

            kl = max(0.0, kl)  # numerical stability
            kl_divs.append(kl)

            # Compare top-1 by decoded text (handles different tokenizers)
            top1_text_a = top5_a[0][0] if top5_a else ""
            top1_text_b = top5_b[0][0] if top5_b else ""
            if same_tokenizer:
                top1_match = (topk_a.indices[0].item() == topk_b.indices[0].item())
            else:
                top1_match = (top1_text_a.lower() == top1_text_b.lower())

            if top1_match:
                top1_matches += 1

            tokens.append({
                "position": pos,
                "model_a_top5": top5_a,
                "model_b_top5": top5_b,
                "kl_div": round(kl, precision),
                "top1_match": top1_match,
            })

        # -- Cosine similarity of hidden states ------------------------------------
        ctx.log_message("Computing hidden-state similarity...")
        ctx.report_progress(5, 6)
        cosine_sim_mean = 0.0
        layer_similarities = []

        if compare_layers and hasattr(outputs_a, "hidden_states") and outputs_a.hidden_states \
                and hasattr(outputs_b, "hidden_states") and outputs_b.hidden_states:
            # hidden_states is tuple of (num_steps,) each containing tuple of layer tensors
            hs_a = outputs_a.hidden_states[0]  # first step = prompt encoding
            hs_b = outputs_b.hidden_states[0]

            num_layers = min(len(hs_a), len(hs_b))
            sims = []
            for layer_idx in range(num_layers):
                vec_a = hs_a[layer_idx][0, -1, :].float()  # last token of prompt
                vec_b = hs_b[layer_idx][0, -1, :].float()

                # Handle different hidden dimensions between models
                min_dim = min(vec_a.shape[0], vec_b.shape[0])
                if min_dim == 0:
                    continue
                cos = F.cosine_similarity(
                    vec_a[:min_dim].unsqueeze(0),
                    vec_b[:min_dim].unsqueeze(0),
                ).item()
                sims.append(round(cos, precision))
                layer_similarities.append({
                    "layer": layer_idx,
                    "cosine_similarity": round(cos, precision),
                })

            cosine_sim_mean = sum(sims) / len(sims) if sims else 0.0
        else:
            # Fallback: cosine similarity of output probability distributions
            if num_positions > 0:
                sims = []
                for pos in range(num_positions):
                    pa = F.softmax(scores_a[pos][0].float(), dim=-1)
                    pb = F.softmax(scores_b[pos][0].float(), dim=-1)
                    min_dim = min(pa.shape[0], pb.shape[0])
                    if min_dim == 0:
                        continue
                    cos = F.cosine_similarity(
                        pa[:min_dim].unsqueeze(0),
                        pb[:min_dim].unsqueeze(0),
                    ).item()
                    sims.append(cos)
                cosine_sim_mean = sum(sims) / len(sims) if sims else 0.0

        overall_kl = sum(kl_divs) / len(kl_divs) if kl_divs else 0.0
        agreement_rate = top1_matches / num_positions if num_positions > 0 else 1.0

        report = {
            "tokens": tokens,
            "overall_kl_divergence": round(overall_kl, precision),
            "top1_agreement_rate": round(agreement_rate, precision),
            "cosine_similarity_mean": round(cosine_sim_mean, precision),
            "comparison_mode": "logits",
            "vocab_size_a": vocab_a,
            "vocab_size_b": vocab_b,
        }
        if layer_similarities:
            report["layer_similarities"] = layer_similarities

        return report

    finally:
        # Free GPU/MPS memory regardless of success or failure
        del model_a, model_b
        try:
            import torch as _torch
            if _torch.cuda.is_available():
                _torch.cuda.empty_cache()
            elif hasattr(_torch, "mps") and hasattr(_torch.mps, "empty_cache"):
                _torch.mps.empty_cache()
        except Exception:
            pass
        import gc
        gc.collect()


# ── Remote/mixed comparison via inference API ────────────────────────────


def _compare_via_inference(ctx, model_a_info, model_b_info, prompt, max_tokens,
                           top_k, precision):
    """Compare models using inference API (Ollama or mixed). Text-level comparison."""
    from blocks.inference._inference_utils import call_inference

    ctx.report_progress(0, 4)
    ctx.log_message("Generating response from Model A...")
    try:
        resp_a, meta_a = call_inference(
            model_a_info["framework"], model_a_info["name"], prompt, "",
            {"max_tokens": max_tokens, "temperature": 0.0,
             "endpoint": model_a_info["endpoint"]},
            log_fn=ctx.log_message,
        )
    except Exception as e:
        raise RuntimeError(f"Model A inference failed ({model_a_info['name']}): {e}")

    ctx.report_progress(1, 4)
    ctx.log_message("Generating response from Model B...")
    try:
        resp_b, meta_b = call_inference(
            model_b_info["framework"], model_b_info["name"], prompt, "",
            {"max_tokens": max_tokens, "temperature": 0.0,
             "endpoint": model_b_info["endpoint"]},
            log_fn=ctx.log_message,
        )
    except Exception as e:
        raise RuntimeError(f"Model B inference failed ({model_b_info['name']}): {e}")

    ctx.report_progress(2, 4)
    ctx.log_message("Computing text-level differences...")

    # Tokenize responses at word level for comparison
    words_a = resp_a.split() if resp_a else []
    words_b = resp_b.split() if resp_b else []
    num_positions = max(len(words_a), len(words_b))

    if num_positions == 0:
        ctx.log_message("Warning: both models returned empty responses")
        ctx.report_progress(3, 4)
        return {
            "tokens": [],
            "overall_kl_divergence": 0.0,
            "top1_agreement_rate": 1.0,
            "cosine_similarity_mean": 1.0,
            "comparison_mode": "text_based",
            "model_a_response": "",
            "model_b_response": "",
        }

    tokens = []
    matches = 0
    for pos in range(num_positions):
        word_a = words_a[pos] if pos < len(words_a) else ""
        word_b = words_b[pos] if pos < len(words_b) else ""
        is_match = (word_a.lower() == word_b.lower()) and word_a != ""
        if is_match:
            matches += 1

        tokens.append({
            "position": pos,
            "model_a_top5": [[word_a, 1.0]] if word_a else [],
            "model_b_top5": [[word_b, 1.0]] if word_b else [],
            "kl_div": 0.0 if is_match else 1.0,
            "top1_match": is_match,
        })

    agreement_rate = matches / num_positions if num_positions > 0 else 1.0

    # Approximate divergence from word-level Jaccard similarity
    set_a = set(w.lower() for w in words_a) if words_a else set()
    set_b = set(w.lower() for w in words_b) if words_b else set()
    overlap = len(set_a & set_b)
    union = len(set_a | set_b)
    jaccard = overlap / union if union > 0 else 1.0
    approx_kl = -math.log(max(jaccard, 1e-10))

    ctx.report_progress(3, 4)

    return {
        "tokens": tokens,
        "overall_kl_divergence": round(approx_kl, precision),
        "top1_agreement_rate": round(agreement_rate, precision),
        "cosine_similarity_mean": round(jaccard, precision),
        "comparison_mode": "text_based",
        "model_a_response": resp_a[:500] if resp_a else "",
        "model_b_response": resp_b[:500] if resp_b else "",
    }


# ── Helpers ──────────────────────────────────────────────────────────────


def _round_report(report, precision):
    """Recursively round all floats in the report dict."""
    if isinstance(report, dict):
        for k, v in report.items():
            if isinstance(v, float):
                report[k] = round(v, precision)
            elif isinstance(v, (dict, list)):
                _round_report(v, precision)
    elif isinstance(report, list):
        for i, item in enumerate(report):
            if isinstance(item, float):
                report[i] = round(item, precision)
            elif isinstance(item, (dict, list)):
                _round_report(item, precision)
