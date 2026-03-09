"""Response Parser — parse and extract structured data from LLM responses.

Workflows:
  1. JSON extraction: LLM response -> extract JSON object -> structured data
  2. Regex extraction: response -> regex pattern -> matched groups
  3. Key-value parsing: response with "Key: Value" lines -> dict
  4. Markdown parsing: response -> extract headers, code blocks, lists
  5. CSV parsing: tabular response -> structured records
  6. Pipeline glue: connect LLM output -> parser -> downstream block
"""

import json
import os
import re


def run(ctx):
    fmt = ctx.config.get("format", "json")
    extraction_pattern = ctx.config.get("extraction_pattern", "")
    strict = ctx.config.get("strict", False)
    if isinstance(strict, str):
        strict = strict.lower() in ("true", "1", "yes")
    field_names = ctx.config.get("field_names", "")
    kv_separator = ctx.config.get("kv_separator", ":")
    csv_delimiter = ctx.config.get("csv_delimiter", ",")

    ctx.report_progress(0, 3)

    # Load raw response
    text = ""
    if ctx.inputs.get("text"):
        data = ctx.load_input("text")
        if isinstance(data, str):
            if os.path.isfile(data):
                with open(data, "r", encoding="utf-8", errors="ignore") as f:
                    text = f.read()
            else:
                text = data
        elif isinstance(data, dict):
            text = json.dumps(data)

    if not text:
        raise ValueError("No input text to parse")

    ctx.log_message(f"Parsing response: format={fmt}, {len(text)} chars")
    ctx.report_progress(1, 3)

    parsed_text = text
    extracted_data = {}
    extracted_records = []

    if fmt == "json":
        # Try direct parse
        try:
            parsed = json.loads(text)
            parsed_text = json.dumps(parsed, indent=2)
            extracted_data = parsed if isinstance(parsed, dict) else {"data": parsed}
            if isinstance(parsed, list):
                extracted_records = parsed
            else:
                extracted_records = [parsed]
        except json.JSONDecodeError:
            # Try to find JSON in markdown code blocks
            code_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', text)
            if code_match:
                try:
                    parsed = json.loads(code_match.group(1))
                    parsed_text = json.dumps(parsed, indent=2)
                    extracted_data = parsed if isinstance(parsed, dict) else {"data": parsed}
                    if isinstance(parsed, list):
                        extracted_records = parsed
                    else:
                        extracted_records = [parsed]
                except json.JSONDecodeError:
                    pass

            if not extracted_data:
                # Try to find any JSON object
                json_match = re.search(r'\{[\s\S]*\}', text)
                if json_match:
                    try:
                        parsed = json.loads(json_match.group())
                        parsed_text = json.dumps(parsed, indent=2)
                        extracted_data = parsed if isinstance(parsed, dict) else {"data": parsed}
                        extracted_records = [parsed]
                    except json.JSONDecodeError:
                        if strict:
                            raise ValueError("Failed to parse JSON from response")

    elif fmt == "regex" and extraction_pattern:
        matches = re.findall(extraction_pattern, text)
        if matches:
            extracted_data = {"matches": matches, "count": len(matches)}
            parsed_text = "\n".join(str(m) for m in matches)
            extracted_records = [{"match": m, "index": i} for i, m in enumerate(matches)]
        elif strict:
            raise ValueError(f"Pattern not found: {extraction_pattern}")

    elif fmt == "key_value":
        for line in text.split("\n"):
            if kv_separator in line:
                key, _, value = line.partition(kv_separator)
                key = key.strip()
                value = value.strip()
                if key:
                    extracted_data[key] = value
        if extracted_data:
            parsed_text = json.dumps(extracted_data, indent=2)
            extracted_records = [extracted_data]

    elif fmt == "markdown":
        headers = re.findall(r'^#+\s+(.+)$', text, re.MULTILINE)
        code_blocks = re.findall(r'```(\w*)\n([\s\S]*?)```', text)
        lists = re.findall(r'^[\s]*[-*]\s+(.+)$', text, re.MULTILINE)
        extracted_data = {
            "headers": headers,
            "code_blocks": [{"language": lang, "code": code} for lang, code in code_blocks],
            "list_items": lists,
        }
        extracted_records = [{"type": "header", "content": h} for h in headers]
        extracted_records += [{"type": "code", "language": lang, "content": code} for lang, code in code_blocks]

    elif fmt == "csv":
        lines = [line.strip() for line in text.strip().split("\n") if line.strip()]
        if lines:
            # Use provided field names or first line as header
            if field_names:
                headers_list = [f.strip() for f in field_names.split(csv_delimiter)]
                data_lines = lines
            else:
                headers_list = [h.strip() for h in lines[0].split(csv_delimiter)]
                data_lines = lines[1:]

            for line in data_lines:
                values = [v.strip() for v in line.split(csv_delimiter)]
                row = {}
                for j, header in enumerate(headers_list):
                    row[header] = values[j] if j < len(values) else ""
                extracted_records.append(row)

            extracted_data = {"headers": headers_list, "row_count": len(extracted_records)}
            parsed_text = json.dumps(extracted_records, indent=2)

    elif fmt == "xml":
        # Simple XML tag extraction
        tags = re.findall(r'<(\w+)>(.*?)</\1>', text, re.DOTALL)
        extracted_data = {tag: value.strip() for tag, value in tags}
        if extracted_data:
            parsed_text = json.dumps(extracted_data, indent=2)
            extracted_records = [extracted_data]

    ctx.report_progress(2, 3)

    # Save parsed output
    out_path = os.path.join(ctx.run_dir, "parsed.txt")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(parsed_text)
    ctx.save_output("text", out_path)

    # Save extracted data
    if extracted_data:
        data_path = os.path.join(ctx.run_dir, "extracted.json")
        with open(data_path, "w", encoding="utf-8") as f:
            json.dump(extracted_data, f, indent=2)
        ctx.save_output("data", data_path)

    # Save extracted records
    if extracted_records:
        records_dir = os.path.join(ctx.run_dir, "dataset")
        os.makedirs(records_dir, exist_ok=True)
        with open(os.path.join(records_dir, "data.json"), "w", encoding="utf-8") as f:
            json.dump(extracted_records, f, indent=2)
        ctx.save_output("dataset", records_dir)

    ctx.log_message(f"Parsed {fmt}: {len(extracted_data)} fields, {len(extracted_records)} records")
    ctx.report_progress(3, 3)
