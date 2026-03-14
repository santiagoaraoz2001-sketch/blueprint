"""HuggingFace Model Loader — load a pre-trained model from HuggingFace Hub."""

import json
import os
import urllib.request
import urllib.error


def run(ctx):
    model_id = ctx.config.get("model_id", "").strip()
    revision = ctx.config.get("revision", "main").strip()
    quantization = ctx.config.get("quantization", "none").lower().strip()
    trust_remote_code = ctx.config.get("trust_remote_code", False)
    device_map = ctx.config.get("device_map", "auto")
    cache_dir = ctx.config.get("cache_dir", "").strip()
    torch_dtype = ctx.config.get("torch_dtype", "auto")

    if not model_id:
        raise ValueError(
            "model_id is required (e.g. 'meta-llama/Llama-2-7b-hf')"
        )

    ctx.log_message(f"Loading HuggingFace model: {model_id}")
    ctx.log_message(f"  Revision: {revision}")
    if quantization != "none":
        ctx.log_message(f"  Quantization: {quantization}")
    ctx.report_progress(0, 3)

    # ── Step 1: Validate model via HuggingFace API ──
    model_info = {
        "source": "huggingface",
        "model_id": model_id,
        "model_name": model_id,
        "revision": revision,
        "quantization": quantization if quantization != "none" else None,
        "trust_remote_code": trust_remote_code,
        "device_map": device_map,
        "torch_dtype": torch_dtype,
        "cache_dir": cache_dir or None,
        "hub_url": f"https://huggingface.co/{model_id}",
        "validated": False,
    }

    api_url = f"https://huggingface.co/api/models/{model_id}"
    if revision and revision != "main":
        api_url += f"?revision={revision}"

    try:
        req = urllib.request.Request(
            api_url,
            headers={"User-Agent": "Blueprint-HFModelLoader/1.0"},
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=15) as response:
            if response.status == 200:
                body = response.read().decode("utf-8")
                api_data = json.loads(body)
                model_info["validated"] = True
                model_info["model_type"] = api_data.get("pipeline_tag", "unknown")
                model_info["library"] = api_data.get("library_name", "unknown")
                model_info["downloads"] = api_data.get("downloads", 0)
                model_info["likes"] = api_data.get("likes", 0)
                model_info["tags"] = api_data.get("tags", [])[:20]
                model_info["last_modified"] = api_data.get("lastModified")
                ctx.log_message(
                    f"Model validated: {model_id} "
                    f"(type={model_info['model_type']}, library={model_info['library']}, "
                    f"downloads={model_info['downloads']:,})"
                )
    except urllib.error.HTTPError as e:
        if e.code == 404:
            ctx.log_message(
                f"WARNING: Model '{model_id}' not found (404). "
                f"It may be private or the ID may be incorrect."
            )
        else:
            ctx.log_message(
                f"WARNING: HuggingFace API returned HTTP {e.code}. "
                f"Model not validated but will proceed."
            )
    except (urllib.error.URLError, Exception) as e:
        ctx.log_message(
            f"Could not reach HuggingFace API ({e}). Proceeding without validation."
        )

    ctx.report_progress(1, 3)

    # ── Step 2: Attempt actual model loading ──
    try:
        from transformers import AutoModelForCausalLM, AutoTokenizer

        ctx.log_message("Loading model with transformers...")
        load_kwargs = {
            "pretrained_model_name_or_path": model_id,
            "revision": revision,
            "trust_remote_code": trust_remote_code,
            "device_map": device_map,
        }

        if cache_dir:
            load_kwargs["cache_dir"] = cache_dir

        if torch_dtype != "auto":
            import torch
            dtype_map = {
                "float16": torch.float16,
                "bfloat16": torch.bfloat16,
                "float32": torch.float32,
            }
            load_kwargs["torch_dtype"] = dtype_map.get(torch_dtype, "auto")
        else:
            load_kwargs["torch_dtype"] = "auto"

        if quantization == "4bit":
            try:
                from transformers import BitsAndBytesConfig
                load_kwargs["quantization_config"] = BitsAndBytesConfig(
                    load_in_4bit=True,
                    bnb_4bit_compute_dtype="float16",
                )
                ctx.log_message("Applying 4-bit quantization via bitsandbytes")
            except ImportError as e:
                from backend.block_sdk.exceptions import BlockDependencyError
                missing = str(e).split("'")[-2] if "'" in str(e) else str(e)
                raise BlockDependencyError(
                    missing,
                    f"Required library not installed: {e}",
                    install_hint="pip install bitsandbytes transformers",
                )
        elif quantization == "8bit":
            try:
                from transformers import BitsAndBytesConfig
                load_kwargs["quantization_config"] = BitsAndBytesConfig(
                    load_in_8bit=True,
                )
                ctx.log_message("Applying 8-bit quantization via bitsandbytes")
            except ImportError as e:
                from backend.block_sdk.exceptions import BlockDependencyError
                missing = str(e).split("'")[-2] if "'" in str(e) else str(e)
                raise BlockDependencyError(
                    missing,
                    f"Required library not installed: {e}",
                    install_hint="pip install bitsandbytes transformers",
                )

        ctx.report_progress(2, 3)

        model = AutoModelForCausalLM.from_pretrained(**load_kwargs)
        tokenizer = AutoTokenizer.from_pretrained(
            model_id,
            revision=revision,
            trust_remote_code=trust_remote_code,
            cache_dir=cache_dir or None,
        )

        model_path = os.path.join(ctx.run_dir, "model")
        os.makedirs(model_path, exist_ok=True)
        model.save_pretrained(model_path)
        tokenizer.save_pretrained(model_path)

        model_info["path"] = model_path
        model_info["loaded"] = True
        ctx.log_message(f"Model loaded and saved to: {model_path}")

    except ImportError as e:
        from backend.block_sdk.exceptions import BlockDependencyError
        missing = str(e).split("'")[-2] if "'" in str(e) else str(e)
        raise BlockDependencyError(
            missing,
            f"Required library not installed: {e}",
            install_hint="pip install torch transformers",
        )
    except Exception as e:
        ctx.log_message(f"Could not load model: {e}. Emitting model config only.")
        model_info["loaded"] = False

    # ── Step 3: Save outputs ──
    ctx.report_progress(3, 3)

    model_info_path = os.path.join(ctx.run_dir, "model_info.json")
    with open(model_info_path, "w", encoding="utf-8") as f:
        json.dump(model_info, f, indent=2, default=str, ensure_ascii=False)

    ctx.save_output("model", model_info)
    ctx.save_artifact("model_info", model_info_path)
    ctx.log_metric("model_validated", 1.0 if model_info.get("validated") else 0.0)

    validated_str = "VALIDATED" if model_info.get("validated") else "NOT VALIDATED"
    ctx.log_message(
        f"HuggingFace Model Loader complete: {model_id} ({validated_str})"
    )
